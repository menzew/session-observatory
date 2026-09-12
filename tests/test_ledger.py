import io
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
from pathlib import Path

from engine.ledger import Ledger, dump, now, usage, bounded_lines
from collector.server import make_server, loopback_authority


def counts(n=100):
    return dict(input_tokens=n, cached_input_tokens=n//2, output_tokens=20,
                reasoning_output_tokens=10, total_tokens=n+20)


def line(kind, payload, timestamp=None):
    return (json.dumps(dict(type=kind, timestamp=timestamp or now(), payload=payload))+'\n').encode()


def log(response='resp-1', n=100, thread='task-1', parent=None, snapshot=True):
    meta = dict(id=thread, cwd='/work/project', originator='codex_cli', model_provider='openai',
                session_id='meta-session', git=dict(branch='main', commit_hash='abc123'))
    if parent: meta['parent_thread_id'] = parent
    data = line('session_meta', meta) + line('turn_context', dict(model='test-model', turn_id='turn-1'))
    if response:
        data += line('token_usage_record', dict(response_id=response, thread_id=thread,
                     root_turn_id='root-turn', session_id='execution-session', usage=counts(n)))
    if snapshot:
        data += line('event_msg', dict(type='token_count', info=dict(total_token_usage=counts(n))))
    return data


def provider(n=100, **dims):
    return dict(data=[dict(start_time=1788825600, end_time=1788912000,
        results=[dict(object='organization.usage.completions.result', input_tokens=n,
                      input_cached_tokens=50, output_tokens=20, num_model_requests=1, **dims)])], has_more=False)


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.temp.name)/'ledger.sqlite3')

    def tearDown(self):
        self.ledger.close(); self.temp.cleanup()

    def ingest(self, data=None, source='source.jsonl'):
        records, mode, issues = self.ledger.parse_codex(io.BytesIO(data or log()), source)
        with self.ledger.db: self.ledger.persist_events(records)
        return records, mode, issues

    def total(self): return self.ledger.query({})['summary']['total_tokens']

    def test_native_and_snapshot_are_not_added(self):
        rows, mode, issues = self.ingest()
        self.assertEqual((len(rows), mode, self.total()), (1, 'response', 120))
        details = self.ledger.detail(rows[0][0]['id'])['event']['details']
        self.assertEqual(details['execution_session_id'], 'execution-session')
        self.assertEqual(details['root_turn_id'], 'root-turn')

    def test_copy_is_one_response_with_two_observations(self):
        data = log()
        rows, _, _ = self.ingest(data)
        self.ingest(data, 'copy.jsonl')
        detail = self.ledger.detail(rows[0][0]['id'])
        self.assertEqual(self.total(), 120)
        self.assertEqual(len(detail['observations']), 2)

    def test_conflict_preserves_original_and_alternative(self):
        rows, _, _ = self.ingest()
        self.ingest(log(n=200), 'conflict.jsonl')
        self.assertEqual(self.total(), 120)
        detail = self.ledger.detail(rows[0][0]['id'])
        self.assertEqual(len(detail['conflicts']), 1)
        self.assertEqual(json.loads(detail['conflicts'][0]['evidence'])['total_tokens'], 220)
        self.assertEqual(self.ledger.state()['alerts'][0]['severity'], 'high')

    def test_legacy_copied_file_is_not_added(self):
        data = log(response=None)
        self.ingest(data)
        self.ingest(data, 'copy.jsonl')
        self.assertEqual(self.total(), 120)

    def test_legacy_child_is_excluded(self):
        _, _, issues = self.ingest(log(response=None, parent='parent-task'))
        self.assertEqual(self.total(), 0)
        self.assertEqual(self.ledger.state()['excluded'], 1)
        self.assertTrue(issues)

    def test_native_supersedes_legacy_in_other_source_in_either_order(self):
        self.ingest(log(response=None))
        self.ingest(log(), 'new.jsonl')
        self.ingest(log(response=None), 'another-copy.jsonl')
        self.assertEqual(self.total(), 120)

    def test_invalid_native_does_not_hide_behind_valid_snapshot(self):
        data = line('token_usage_record', {'usage': {'input_tokens': -1}}) + line('event_msg', {'type':'token_count','info':{'total_token_usage':counts()}})
        rows, mode, issues = self.ingest(data)
        self.assertEqual(rows, []); self.assertEqual(mode, 'response'); self.assertTrue(issues)

    def test_incomplete_tail_is_not_counted(self):
        data = log(snapshot=False).rstrip(b'\n')
        rows, _, issues = self.ingest(data)
        self.assertEqual(rows, []); self.assertIn('incomplete', issues[-1])

    def test_legacy_decreasing_counter_does_not_create_negative_usage(self):
        data = log(response=None) + line('event_msg', dict(type='token_count',info=dict(total_token_usage=counts(50))))
        _, _, issues = self.ingest(data)
        self.assertEqual(self.total(), 120); self.assertIn('decreased', issues[-1])

    def test_untrusted_content_is_not_retained(self):
        data = log() + line('response_item', {'type':'message','content':'PRIVATE_PROMPT_SENTINEL'})
        self.ingest(data)
        self.assertNotIn('PRIVATE_PROMPT_SENTINEL', dump(self.ledger.evidence_export()))

    def test_import_does_not_invent_device_or_actor(self):
        result = self.ledger.import_data('remote.jsonl', log().decode(), '')
        event = self.ledger.query({})['events'][0]
        self.assertEqual(result['new_records'], 1)
        self.assertEqual((event['actor'], event['device'], event['account_ref']), ('','',''))

    def test_task_attribution_preserves_counts_and_records_every_change(self):
        rows, _, _ = self.ingest()
        self.ingest(log(response='resp-2'))
        self.ingest(log(response='resp-3', thread='other-task'))
        result = self.ledger.attribute(dict(id=rows[0][0]['id'], apply_scope='task', project='Release', principal='Alice', purpose='Ship release', reason='Mapped to ticket 42'))
        self.assertEqual(result['changed_records'], 2)
        self.assertEqual(self.total(), 360)
        self.assertEqual(self.ledger.query({'project':'Release'})['summary']['total_tokens'], 240)
        self.assertEqual(self.ledger.integrity()['entries'], 2)
        self.assertTrue(self.ledger.integrity()['valid'])
        self.ledger.db.execute("UPDATE audit SET reason='altered' WHERE seq=1")
        self.assertFalse(self.ledger.integrity()['valid'])

    def test_reason_is_required_and_no_partial_attribution(self):
        rows, _, _ = self.ingest()
        with self.assertRaises(ValueError): self.ledger.attribute(dict(id=rows[0][0]['id'], purpose='Why'))
        self.assertEqual(self.ledger.integrity()['entries'], 0)

    def test_budget_escalation_reopens_acknowledged_warning(self):
        self.ingest(log(n=60))  # 80 total
        self.ledger.budget(dict(project='/work/project', tokens=100, period='day'))
        self.ledger.db.execute("UPDATE alerts SET status='acknowledged'")
        self.ingest(log(response='resp-2', n=1))
        self.ledger.evaluate_budgets()
        alert = self.ledger.state()['alerts'][0]
        self.assertEqual((alert['severity'], alert['status']), ('high','open'))
        self.assertEqual(alert['title'], 'Project token budget reached')

    def test_future_usage_is_not_charged_to_current_budget(self):
        self.ingest(log().replace(now()[:10].encode(), b'2099-01-01'))
        self.ledger.budget(dict(project='/work/project',tokens=1,period='day'))
        self.assertEqual(self.ledger.state()['alerts'], [])

    def test_provider_buckets_are_separate_and_idempotent_with_revisions(self):
        self.ingest()
        page = provider(project_id='proj-1')
        self.ledger.import_data('usage.json', dump(page), 'API org')
        self.ledger.import_data('renamed.json', dump(page), 'API org')
        self.assertEqual(self.ledger.provider()['total'], 1)
        page['data'][0]['results'][0]['input_tokens'] = 200
        self.ledger.import_data('revised.json', dump(page), 'API org')
        self.assertEqual(self.ledger.provider()['buckets'][0]['values']['total_tokens'], 220)
        self.ledger.import_data('alternative.json', dump(provider(model='test-model')), 'API org')
        self.assertEqual(self.ledger.provider()['total'], 2)
        self.assertEqual(self.total(), 120)
        self.assertEqual(self.ledger.integrity()['entries'], 3)

    def test_bad_provider_row_rolls_back_whole_import(self):
        page = provider()
        page['data'][0]['results'].append({'object':'unsupported'})
        with self.assertRaises(ValueError): self.ledger.import_data('usage.json', dump(page), 'API org')
        self.assertEqual(self.ledger.provider()['total'], 0)
        self.assertEqual(self.ledger.integrity()['entries'], 0)

    def test_bad_request_count_is_rejected(self):
        page = provider(); page['data'][0]['results'][0]['num_model_requests'] = -1
        with self.assertRaises(ValueError): self.ledger.import_data('usage.json', dump(page), 'API org')

    def test_costs_preserve_decimal_and_currency(self):
        page = provider(); page['data'][0]['results'] = [dict(object='organization.costs.result',amount=dict(value='0.00000000123',currency='usd'),project_id='p')]
        self.ledger.import_data('costs.json', dump(page), 'API org')
        self.assertEqual(self.ledger.provider()['buckets'][0]['values'], dict(amount='1.23E-9',currency='usd'))
        self.assertEqual(self.total(), 0)

    def test_duplicate_activity_and_atomic_conflict(self):
        event = dict(id='ev1',timestamp=now(),action='login.success',actor='Alice',device='laptop',ip_address='192.0.2.1')
        page = dict(schema='observatory.activity.v1',events=[event])
        self.ledger.import_data('activity.json',dump(page),'workspace')
        self.ledger.import_data('activity.json',dump(page),'workspace')
        page['events'] = [{**event,'id':'ev2'},{**event,'actor':'Bob'}]
        with self.assertRaises(ValueError): self.ledger.import_data('activity.json',dump(page),'workspace')
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM activity').fetchone()[0],1)

    def test_csv_neutralizes_formula_and_filters(self):
        rows, _, _ = self.ingest()
        self.ledger.attribute(dict(id=rows[0][0]['id'],project='=HYPERLINK("evil")',reason='Test'))
        export = self.ledger.export({'project':'=HYPERLINK("evil")'})
        self.assertIn("'=HYPERLINK", export)
        self.assertEqual(len(self.ledger.export({'from':'2099-01-01'}).splitlines()), 1)

    def test_scanner_is_idempotent_and_reads_only_session_folders(self):
        root=Path(self.temp.name)/'codex'; folder=root/'sessions'; folder.mkdir(parents=True)
        (root/'auth.json').write_text('PRIVATE_CREDENTIAL_SENTINEL')
        path=folder/'rollout.jsonl'; path.write_bytes(log())
        self.ledger.save_source(dict(label='Local fixture',path=str(root),kind='codex_home',origin='local',enabled=True,reason='Fixture setup'))
        self.ledger.scan(); self.ledger.scan()
        self.assertEqual(self.total(),120); self.assertEqual(self.ledger.state()['files'],1)
        self.assertNotIn('PRIVATE_CREDENTIAL_SENTINEL', dump(self.ledger.evidence_export()))

    def test_token_subsets_and_boolean_counts_rejected(self):
        for data in [dict(input_tokens=True),dict(input_tokens=1,cached_input_tokens=2),dict(output_tokens=1,reasoning_output_tokens=2),dict(input_tokens=1,total_tokens=4)]:
            with self.assertRaises(ValueError): usage(data)

    def test_activity_policy_matches_device_and_ipv4_ipv6_networks(self):
        self.ledger.activity_policy(dict(scope='workspace',devices=['laptop'],networks=['192.0.2.0/24','2001:db8::/32'],reason='Declared inventory'))
        events=[dict(id='good',timestamp=now(),action='login.success',device='laptop',ip_address='192.0.2.5'),
                dict(id='good6',timestamp=now(),action='login.success',device='laptop',ip_address='2001:db8::5'),
                dict(id='bad',timestamp=now(),action='session.used',device='unknown',ip_address='198.51.100.1'),
                dict(id='missing',timestamp=now(),action='session.used')]
        page=dump(dict(schema='observatory.activity.v1',events=events))
        self.ledger.import_data('activity.json',page,'workspace')
        alerts=self.ledger.state()['alerts']
        self.assertEqual(len(alerts),2)
        self.assertEqual(sorted(a['severity'] for a in alerts),['high','warning'])
        self.ledger.import_data('copy.json',page,'workspace')
        self.assertEqual(len(self.ledger.state()['alerts']),2)

    def test_policy_checks_history_without_crossing_account_scopes(self):
        page=dump(dict(schema='observatory.activity.v1',events=[dict(id='event',timestamp=now(),action='session.used',device='unknown')]))
        self.ledger.import_data('activity.json',page,'workspace')
        self.ledger.activity_policy(dict(scope='another',devices=['laptop'],reason='Inventory'))
        self.assertEqual(self.ledger.state()['alerts'],[])
        self.ledger.activity_policy(dict(scope='workspace',devices=['laptop'],reason='Inventory'))
        self.assertEqual(len(self.ledger.state()['alerts']),1)
        with self.assertRaises(ValueError): self.ledger.activity_policy(dict(scope='workspace',networks=['not-an-ip'],reason='Bad network'))
        self.assertEqual(len(self.ledger.state()['activity_policies']),2)

    def test_breakdown_partitions_and_filters_usage(self):
        rows,_,_=self.ingest()
        self.ingest(log(response='resp2',thread='task-2'))
        self.ledger.attribute(dict(id=rows[0][0]['id'],principal='Alice',purpose='Release',reason='Ticket 42'))
        for by in ('project','person','purpose','task','model','application','device','day'):
            result=self.ledger.breakdown({'by':by})
            self.assertEqual(sum(r['total_tokens'] for r in result['groups']),240)
        self.assertEqual(self.ledger.breakdown({'by':'person','q':'Alice'})['groups'][0]['total_tokens'],120)
        self.assertEqual(self.ledger.query({'granularity':'snapshot delta'})['summary']['records'],0)
        with self.assertRaises(ValueError): self.ledger.breakdown({'by':'untrusted sql'})

    def test_cost_numeric_decimal_does_not_lose_precision(self):
        content='{"data":[{"start_time":1,"end_time":2,"results":[{"object":"organization.costs.result","amount":{"value":0.1234567890123456789012345,"currency":"usd"}}]}]}'
        self.ledger.import_data('costs.json',content,'API')
        self.assertEqual(self.ledger.provider()['buckets'][0]['values']['amount'],'0.1234567890123456789012345')

    def test_large_ignored_line_does_not_shift_evidence_line_numbers(self):
        data=b'x'*(16*1024*1024+100)+b'\n'+log(snapshot=False)
        rows,_,issues=self.ledger.parse_codex(bounded_lines(io.BytesIO(data)),'large.jsonl')
        self.assertEqual(rows[0][1][2],4)
        self.assertIn('exceeds 16 MB',issues[0])

    def source(self, path, **changes):
        return self.ledger.save_source(dict(label='Fixture source',path=str(path),kind='codex_home',origin='external',enabled=True,reason='Include fixture',**changes))

    def test_sources_persist_edits_and_removal_preserves_evidence(self):
        folder=Path(self.temp.name)/'source'/'sessions';folder.mkdir(parents=True)
        (folder/'rollout.jsonl').write_bytes(log())
        source=self.source(folder.parent)
        self.ledger.scan();self.assertEqual(self.total(),120)
        event=self.ledger.query({})['events'][0]
        self.assertEqual((event['actor'],event['device']),('',''))
        self.ledger.save_source({**source,'label':'Windows Work','reason':'Clarify source label'})
        db_path=self.ledger.db_path;self.ledger.close()
        self.ledger=Ledger(db_path,roots=['/different/startup/default'])
        sources=self.ledger.configured_sources()
        self.assertEqual(len(sources),1);self.assertEqual(sources[0]['label'],'Windows Work')
        self.ledger.remove_source({'id':source['id']})
        self.ledger.scan();self.assertEqual(self.total(),120)
        self.assertEqual(self.ledger.configured_sources(),[])
        self.assertTrue(self.ledger.integrity()['valid'])
        self.assertEqual(self.ledger.integrity()['entries'],3)

    def test_disable_then_enable_collects_new_files_without_double_counting(self):
        folder=Path(self.temp.name)/'source'/'sessions';folder.mkdir(parents=True)
        (folder/'first.jsonl').write_bytes(log())
        source=self.source(folder.parent);self.ledger.scan()
        source=self.ledger.save_source({**source,'enabled':False,'reason':'Pause fixture'})
        (folder/'second.jsonl').write_bytes(log(response='second-response'))
        self.ledger.scan();self.assertEqual(self.total(),120)
        self.assertEqual(self.ledger.configured_sources()[0]['status'],'disabled')
        self.ledger.save_source({**source,'enabled':True,'reason':'Resume fixture'})
        self.ledger.scan();self.ledger.scan();self.assertEqual(self.total(),240)

    def test_multiple_homes_and_direct_session_folders(self):
        root=Path(self.temp.name)/'one';(root/'sessions').mkdir(parents=True);(root/'archived_sessions').mkdir()
        (root/'sessions'/'one.jsonl').write_bytes(log())
        (root/'archived_sessions'/'two.jsonl').write_bytes(log(response='second'))
        self.source(root)
        direct=Path(self.temp.name)/'copied';direct.mkdir()
        (direct/'copy.jsonl').write_bytes(log())
        self.ledger.save_source(dict(label='Copied sessions',path=str(direct),kind='session_folder',origin='external',enabled=True,reason='Include copy'))
        self.ledger.scan();self.assertEqual(self.total(),240)
        self.assertEqual(len(self.ledger.configured_sources()),2)
        self.assertEqual(self.ledger.state()['files'],3)

    def test_windows_unavailable_path_and_explicit_server_mapping(self):
        folder=Path(self.temp.name)/'mounted'/'sessions';folder.mkdir(parents=True)
        (folder/'rollout.jsonl').write_bytes(log())
        source=self.source(r'C:\Users\alex\.codex')
        with patch('engine.ledger.Path.is_dir',return_value=False):
            self.ledger.scan()
            self.assertEqual(self.ledger.configured_sources()[0]['status'],'unavailable')
        self.assertEqual(self.total(),0)
        source=self.ledger.save_source({**source,'access_path':str(folder.parent),'reason':'Mounted Windows copy'})
        self.ledger.scan();self.assertEqual(self.total(),120)
        self.assertEqual(self.ledger.configured_sources()[0]['resolved_path'],str(folder.parent))
        self.assertEqual(self.ledger.configured_sources()[0]['status'],'ready')

    def test_windows_mount_resolution_and_unc_are_explicit(self):
        data={'path':r'C:\Users\alex\.codex','access_path':''}
        with patch('engine.ledger.Path.is_dir',return_value=True):
            resolved,message=self.ledger.resolve_source_path(data)
        self.assertEqual(str(resolved),'/mnt/c/Users/alex/.codex');self.assertEqual(message,'')
        resolved,message=self.ledger.resolve_source_path({'path':r'\\windows-pc\share\codex','access_path':''})
        self.assertIsNone(resolved);self.assertIn('not accessible',message)

    def test_invalid_and_duplicate_sources_are_rejected_atomically(self):
        for path in ['', 'relative/folder','C:relative','https://example.com/logs','/tmp/bad\x00folder',r'\\.\pipe\example']:
            with self.subTest(path=path),self.assertRaises(ValueError):self.source(path)
        source=self.source('/tmp/observatory-source-test')
        with self.assertRaises(ValueError):self.source('/tmp/observatory-source-test')
        with self.assertRaises(ValueError):self.ledger.save_source({**source,'kind':'read-any-file','reason':'Invalid kind'})
        self.assertEqual(len(self.ledger.configured_sources()),1)
        self.assertEqual(self.ledger.integrity()['entries'],1)

    def test_removed_source_during_scan_cannot_commit_records(self):
        folder=Path(self.temp.name)/'source'/'sessions';folder.mkdir(parents=True)
        (folder/'rollout.jsonl').write_bytes(log())
        source=self.source(folder.parent)
        parse=self.ledger.parse_codex
        def remove_during_parse(*args,**kwargs):
            result=parse(*args,**kwargs)
            self.ledger.remove_source({'id':source['id']})
            return result
        with patch.object(self.ledger,'parse_codex',side_effect=remove_during_parse):self.ledger.scan()
        self.assertEqual(self.total(),0)

    def test_unsupported_history_is_visible_without_inventing_usage(self):
        folder=Path(self.temp.name)/'history';folder.mkdir()
        (folder/'chat.jsonl').write_bytes(line('message',{'content':'DO_NOT_STORE_PROMPT'}))
        self.ledger.save_source(dict(label='History',path=str(folder),kind='session_folder',origin='external',enabled=True,reason='Check supported evidence'))
        self.ledger.scan()
        self.assertEqual(self.total(),0)
        self.assertEqual(self.ledger.configured_sources()[0]['status'],'notices')
        self.assertNotIn('DO_NOT_STORE_PROMPT',dump(self.ledger.evidence_export()))

    def test_default_migration_reuses_existing_file_cache(self):
        folder=Path(self.temp.name)/'source'/'sessions';folder.mkdir(parents=True)
        (folder/'rollout.jsonl').write_bytes(log())
        self.source(folder.parent);self.ledger.scan()
        with self.ledger.db:
            self.ledger.db.execute('DELETE FROM sources')
            self.ledger.db.execute("DELETE FROM settings WHERE key='sources_initialized'")
        db_path=self.ledger.db_path;self.ledger.close();self.ledger=Ledger(db_path,roots=[folder.parent])
        with patch.object(self.ledger,'parse_codex',side_effect=AssertionError('Should reuse cache')):self.ledger.scan()
        self.assertIsNone(self.ledger.progress['error']);self.assertEqual(self.total(),120)

    def test_explicit_startup_override_replaces_saved_sources(self):
        self.source('/tmp/saved-source')
        db_path=self.ledger.db_path;self.ledger.close();self.ledger=Ledger(db_path,roots=[],override_sources=True)
        self.assertEqual(self.ledger.configured_sources(),[])
        self.assertTrue(self.ledger.integrity()['valid'])


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger=Ledger(':memory:'); cls.server=make_server(cls.ledger,0)
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.worker.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.worker.join();cls.ledger.close()

    def request(self,path,headers=None,data=None):
        req=urllib.request.Request(self.base+path,headers=headers or {},data=json.dumps(data).encode() if data is not None else None)
        try: response = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e: response = e
        self.addCleanup(response.close)
        return response

    def test_forwarded_local_port_supports_reads_and_authenticated_mutations(self):
        headers = {'Host':'localhost:56863', 'Origin':'http://localhost:56863'}
        self.assertEqual(self.request('/',headers).status,200)
        state = json.load(self.request('/api/state',headers))
        mutation = {**headers,'Content-Type':'application/json','X-Observatory-Token':state['csrf']}
        self.assertEqual(self.request('/api/budget',mutation,dict(project='forwarded-fixture',tokens=100,period='day')).status,200)
        self.assertEqual(self.request('/api/budget',{**headers,'Content-Type':'application/json'},{}).status,403)

    def test_forwarding_does_not_allow_other_origins_or_host_spoofing(self):
        for origin in ['http://localhost:56864','http://127.0.0.1:56863','https://localhost:56863','http://evil.example','null','', 'http://localhost:56863/']:
            with self.subTest(origin=origin):
                self.assertEqual(self.request('/api/state',{'Host':'localhost:56863','Origin':origin}).status,403)
        for host in ['evil.example:56863','localhost.evil.example:56863','0.0.0.0:56863','127.0.0.2:56863','localhost:0','localhost:65536','localhost:56863@evil.example']:
            with self.subTest(host=host):
                self.assertEqual(self.request('/api/state',{'Host':host,'X-Forwarded-Host':'localhost:56863'}).status,403)

    def test_loopback_authority_is_strict(self):
        self.assertEqual(loopback_authority('localhost'),('localhost',80))
        self.assertEqual(loopback_authority('[::1]:56863'),('[::1]',56863))
        for value in ['localhost/path','localhost?query','localhost#fragment','user@localhost','localhost:１２３','localhost:56863, evil.example',' localhost:56863','localhost:56863\n']:
            with self.subTest(value=value): self.assertIsNone(loopback_authority(value))

    def test_loopback_origin_and_host_validation(self):
        for headers in [{'Origin':'https://evil.example'},{'Host':'evil.example'},{'Sec-Fetch-Site':'cross-site'}]:
            self.assertEqual(self.request('/api/state',headers).status,403)
        self.assertEqual(self.request('/api/state').status,200)

    def test_mutation_requires_token(self):
        self.assertEqual(self.request('/api/budget',{'Content-Type':'application/json'},{}).status,403)
        token=json.load(self.request('/api/state'))['csrf']
        self.assertEqual(self.request('/api/budget',{'Content-Type':'application/json','X-Observatory-Token':token},dict(project='p',tokens=100,period='day')).status,200)

    def test_no_arbitrary_file_access_and_no_cache(self):
        self.assertEqual(self.request('/../ledger.py').status,404)
        self.assertEqual(self.request('/%2e%2e/ledger.py').status,404)
        r=self.request('/')
        self.assertEqual(r.status,200); self.assertEqual(r.headers['Cache-Control'],'no-store')
        self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])

    def test_evidence_download_contains_audit(self):
        response=self.request('/api/evidence-export')
        self.assertEqual(response.status,200)
        self.assertIn('attachment',response.headers['Content-Disposition'])
        self.assertIn('audit',json.load(response)['tables'])


if __name__ == '__main__': unittest.main()
