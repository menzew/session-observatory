import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.ledger import Ledger
from tests.test_ledger import line, log, provider


def quota(percent=49, **overrides):
    return dict(plan_type='pro', limit_id='codex', primary=dict(
        used_percent=percent, window_minutes=10080, resets_at=1789444300), secondary=None, **overrides)


def reading(value=None, timestamp='2026-09-09T08:00:00Z'):
    return line('event_msg', dict(type='token_count', info=None, rate_limits=value or quota()), timestamp)


class LimitsSortingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = Ledger(self.root / 'test.sqlite3')

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def ingest(self, content, name='test.jsonl'):
        return self.ledger.import_data(name, content.decode(), '')

    def test_limits_without_usage_are_idempotent_and_exported(self):
        payload = reading(quota(secret='must-not-store'))
        self.assertEqual(self.ingest(payload)['new_limit_snapshots'], 1)
        self.assertEqual(self.ingest(payload)['new_limit_snapshots'], 0)
        self.assertEqual(self.ledger.query({})['summary']['total_tokens'], 0)
        latest = self.ledger.limits({'plan':'pro'})['latest']
        self.assertEqual(latest['windows']['primary']['used_percent'], 49)
        self.assertEqual(latest['windows']['primary']['window_minutes'], 10080)
        self.assertIsNone(latest['windows']['secondary'])
        self.assertEqual(latest['windows']['primary']['resets_at'], '2026-09-15T03:51:40.000Z')
        self.assertNotIn('must-not-store', json.dumps(self.ledger.evidence_export()))
        self.assertEqual(len(self.ledger.evidence_export()['tables']['limit_snapshots']), 1)

    def test_invalid_quota_does_not_drop_valid_metering(self):
        for percent in (-1, 101, float('nan'), float('inf'), True, '49'):
            limits=[]
            records, _, issues = self.ledger.parse_codex(io.BytesIO(log()+reading(quota(percent))), 'file', limit_records=limits)
            self.assertEqual(len(records), 1)
            self.assertEqual(limits, [])
            self.assertTrue(any('invalid quota' in i for i in issues))

    def test_unknown_window_fields_are_unknown_not_zero(self):
        self.ingest(reading({'plan_type':'pro', 'primary':{}}))
        window = self.ledger.limits({})['latest']['windows']['primary']
        self.assertEqual(window, {'used_percent':None, 'window_minutes':None, 'resets_at':None})

    def test_two_windows_keep_independent_durations_and_expired_resets(self):
        self.ingest(reading({'plan_type':'pro','primary':{'used_percent':49.5,'window_minutes':300,'resets_at':1788897600},
                            'secondary':{'used_percent':0,'window_minutes':10080,'resets_at':1789444300}}))
        row=self.ledger.limits({})['latest']
        self.assertEqual(row['windows']['primary']['used_percent'],49.5)
        self.assertEqual(row['windows']['primary']['window_minutes'],300)
        self.assertLess(row['windows']['primary']['resets_at'],row['timestamp'])
        self.assertEqual(row['windows']['secondary']['used_percent'],0)
        self.assertEqual(row['windows']['secondary']['window_minutes'],10080)

    def test_limit_pagination_sorts_before_page_and_retains_latest(self):
        self.ingest(b''.join(reading(quota(n),f'2026-09-09T08:{n:02d}:00Z') for n in range(55)))
        first=self.ledger.limits({'sort_by':'primary','direction':'asc'})
        last=self.ledger.limits({'sort_by':'primary','direction':'asc','offset':'50'})
        self.assertEqual([r['windows']['primary']['used_percent'] for r in last['snapshots']],list(range(50,55)))
        self.assertEqual(first['latest']['windows']['primary']['used_percent'],54)
        self.assertEqual(first['total'],55)

    def test_context_requires_prior_time_line_source_and_task(self):
        content = line('session_meta', {'id':'task-1'}) + reading()
        content += line('token_usage_record', {'thread_id':'task-1','response_id':'r','usage':{'input_tokens':10,'output_tokens':5}}, '2026-09-09T08:01:00Z')
        content += reading(quota(90), '2026-09-09T08:02:00Z')
        # A later physical line with an older timestamp must not leak backwards.
        content += reading(quota(70), '2026-09-09T08:00:30Z')
        self.ingest(content)
        self.ingest(line('session_meta', {'id':'task-1'})+reading(quota(99)), 'other.jsonl')
        event = self.ledger.query({})['events'][0]
        context = self.ledger.detail(event['id'])['limit_context']
        self.assertEqual(len(context), 1)
        self.assertEqual(context[0]['windows']['primary']['used_percent'], 49)
        self.assertEqual(context[0]['line'], 2)
        self.assertTrue(context[0]['source'].endswith('/test.jsonl'))
        self.ledger.db.execute("UPDATE limit_snapshots SET thread_id='another-task'")
        self.assertEqual(self.ledger.detail(event['id'])['limit_context'], [])

    def test_later_snapshot_is_not_assigned_to_earlier_response(self):
        content = line('session_meta', {'id':'task-1'})
        content += line('token_usage_record', {'thread_id':'task-1','response_id':'r','usage':{'input_tokens':10,'output_tokens':5}}, '2026-09-09T07:00:00Z')
        self.ingest(content+reading())
        self.assertEqual(self.ledger.detail(self.ledger.query({})['events'][0]['id'])['limit_context'], [])

    def test_limits_sort_filter_and_latest_are_independent(self):
        self.ingest(reading(quota(2),'2026-09-08T08:00:00Z')+reading(quota(50))+reading({'plan_type':'plus','primary':None},'2026-09-09T09:00:00Z'))
        asc=self.ledger.limits({'sort_by':'primary','direction':'asc'})
        desc=self.ledger.limits({'sort_by':'primary','direction':'desc'})
        self.assertEqual([r['windows']['primary']['used_percent'] if r['windows']['primary'] else None for r in asc['snapshots']], [2,50,None])
        self.assertEqual([r['windows']['primary']['used_percent'] if r['windows']['primary'] else None for r in desc['snapshots']], [50,2,None])
        self.assertEqual(asc['latest']['plan'], 'plus')
        self.assertEqual(self.ledger.limits({'plan':'pro','from':'2026-09-09','to':'2026-09-10'})['total'], 1)
        self.assertEqual(self.ledger.limits({'q':'no-such-source'})['total'], 0)

    def test_backfill_unchanged_files_and_then_use_cache(self):
        home=self.root/'codex';folder=home/'sessions';folder.mkdir(parents=True)
        (folder/'data.jsonl').write_bytes(log()+reading())
        self.ledger.save_source(dict(label='Fixture',path=str(home),kind='codex_home',origin='local',enabled=True,reason='Test'))
        self.ledger.scan()
        before=self.ledger.query({})['summary']
        # Simulate pre-feature file caches and existing usage, with no limit data.
        with self.ledger.db:
            self.ledger.db.execute('DELETE FROM limit_files')
            self.ledger.db.execute('DELETE FROM limit_snapshots')
        with patch.object(self.ledger,'persist_events',side_effect=lambda rows:self.assertEqual(rows,[])):
            self.ledger.scan()
        self.assertIsNone(self.ledger.progress['error'])
        self.assertEqual(self.ledger.limits({})['total'],1)
        self.assertEqual(before,self.ledger.query({})['summary'])
        with patch.object(self.ledger,'parse_codex',side_effect=AssertionError('Cache should avoid parsing')):
            self.ledger.scan()
        self.assertIsNone(self.ledger.progress['error'])

    def test_global_numeric_sort_pages_and_csv_preserve_totals(self):
        for n in range(1,62): self.ingest(log(response=f'r-{n}',n=n,snapshot=False),f'{n}.jsonl')
        asc=self.ledger.query({'sort_by':'input_tokens','direction':'asc'})
        desc=self.ledger.query({'sort_by':'input_tokens','direction':'desc'})
        tail=self.ledger.query({'sort_by':'input_tokens','direction':'asc','offset':'50'})
        self.assertEqual([r['input_tokens'] for r in asc['events']],list(range(1,51)))
        self.assertEqual([r['input_tokens'] for r in tail['events']],list(range(51,62)))
        self.assertEqual(desc['events'][0]['input_tokens'],61)
        self.assertEqual(asc['summary'],desc['summary'])
        rows=list(csv.DictReader(io.StringIO(self.ledger.export({'sort_by':'input_tokens','direction':'desc'}))))
        self.assertEqual([int(r['input_tokens']) for r in rows],list(range(61,0,-1)))

    def test_text_sort_uses_declared_owner_case_insensitive_unknown_last(self):
        for n,owner in enumerate(['Zed','alice','']):
            self.ingest(log(response=f'r-{n}',snapshot=False),f'{n}.jsonl')
            event=self.ledger.query({'q':f'r-{n}'})['events'][0]
            if owner:self.ledger.attribute(dict(id=event['id'],principal=owner,reason='Test'))
        for direction,expected in [('asc',['alice','Zed','']),('desc',['Zed','alice',''])]:
            rows=self.ledger.query({'sort_by':'actor','direction':direction})['events']
            self.assertEqual([r['effective_actor'] for r in rows],expected)

    def test_breakdown_sorts_aggregated_values(self):
        for n in (2,10,3):
            self.ingest(log(response=f'r-{n}',n=n,thread=f't-{n}',snapshot=False))
        rows=self.ledger.breakdown({'by':'task','sort_by':'total_tokens','direction':'asc'})['groups']
        self.assertEqual([r['total_tokens'] for r in rows],[22,23,30])

    def test_provider_sorts_exact_decimal_values_and_grouped_units(self):
        for i,amount in enumerate(['2.0000000000000000001','2.0000000000000000000','10']):
            obj=provider();obj['data'][0]['results']=[dict(object='organization.costs.result',line_item=str(i),amount=dict(value=amount,currency='usd'))]
            self.ledger.import_data('cost.json',json.dumps(obj),'API')
        self.ledger.import_data('usage.json',json.dumps(provider()),'API')
        rows=self.ledger.provider({'sort_by':'values','direction':'asc'})['buckets']
        self.assertEqual([r['values'].get('amount') for r in rows],['2.0000000000000000000','2.0000000000000000001','10',None])

    def test_sort_columns_and_direction_are_allowlisted(self):
        for method in (self.ledger.query,self.ledger.breakdown,self.ledger.limits,self.ledger.provider):
            with self.assertRaises(ValueError):method({'sort_by':'timestamp; DROP TABLE events'})
            with self.assertRaises(ValueError):method({'direction':'asc; DROP TABLE events','sort_by':'total_tokens' if method==self.ledger.query else 'values' if method==self.ledger.provider else 'primary' if method==self.ledger.limits else 'records'})
        self.assertEqual(self.ledger.query({})['summary']['records'],0)


if __name__=='__main__': unittest.main()
