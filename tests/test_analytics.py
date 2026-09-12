import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from engine.ledger import Ledger
from engine.analytics import METRICS
from tests.test_ledger import line


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.ledger=Ledger(Path(self.temp.name)/'ledger.sqlite3')

    def tearDown(self):
        self.ledger.close();self.temp.cleanup()

    def add(self, ident, n=100, project='/work/A', model='model-A', time='2026-09-09T08:00:00Z', native=True):
        content=line('session_meta',dict(id='task-'+ident,cwd=project,git={'branch':'feature/test'}),time)
        content+=line('turn_context',dict(model=model),time)
        counts=dict(input_tokens=n,cached_input_tokens=n//2,output_tokens=20,reasoning_output_tokens=10)
        if native:content+=line('token_usage_record',dict(response_id=ident,usage=counts),time)
        else:content+=line('event_msg',dict(type='token_count',info=dict(total_token_usage=counts)),time)
        self.ledger.import_data(ident+'.jsonl',content.decode(),'')

    def test_every_chart_and_group_reconciles_for_every_metric(self):
        for i in range(9):self.add(str(i),n=i*100,project=f'/work/{i}',time=f'2026-09-0{1+i}T08:00:00Z')
        for metric in METRICS:
            data=self.ledger.analytics(dict(by='project',metric=metric,**{'from':'2026-09-01','to':'2026-09-10'}))
            total=data['summary'][metric]
            self.assertEqual(sum(r[metric] for r in data['chart_groups']),total)
            self.assertEqual(sum(r[metric] for r in data['timeline']),total)
            self.assertEqual(sum(r['value'] for r in data['heatmap']),total)
            self.assertEqual(sum(r[metric] for r in data['groups']),total)
            self.assertEqual(len(data['chart_groups']),6)
            self.assertTrue(data['chart_groups'][-1]['other'])
            if total:self.assertAlmostEqual(sum(r['share'] for r in data['groups']),1)
            else:self.assertTrue(all(r['share'] is None for r in data['groups']))
        s=data['summary']
        self.assertEqual(s['cached_input_tokens']+s['uncached_input_tokens']+s['output_tokens'],s['total_tokens'])

    def test_facets_are_exact_and_match_ledger_export(self):
        self.add('a',project='/work/A');self.add('ab',project='/work/AB');self.add('m',model='model-B')
        params={'facets':json.dumps({'project':'/work/A','model':'model-A'})}
        data=self.ledger.analytics(params)
        self.assertEqual(data['summary']['total_tokens'],120)
        self.assertEqual(self.ledger.query(params)['summary']['records'],1)
        exported=list(csv.DictReader(io.StringIO(self.ledger.export(params))))
        self.assertEqual(len(exported),1)
        self.assertEqual(exported[0]['response_id'],'a')

    def test_declared_attribution_and_missing_identity_filters(self):
        self.add('a');self.add('b',n=300)
        record=self.ledger.query({'q':'task-a'})['events'][0]
        self.ledger.attribute(dict(id=record['id'],project='Release',principal='Alice',purpose='Ship',reason='Test'))
        params={'facets':json.dumps({'person':'Alice','purpose':'Ship','project':'Release'})}
        result=self.ledger.analytics(params)
        self.assertEqual(result['summary']['records'],1)
        self.assertEqual(result['summary']['undeclared_tokens'],0)
        all_data=self.ledger.analytics({})
        self.assertEqual(all_data['summary']['undeclared_tokens'],320)
        self.assertEqual(self.ledger.analytics({'facets':json.dumps({'person':'Unknown'})})['summary']['records'],1)

    def test_previous_equal_interval_and_zero_baseline(self):
        self.add('before',n=100,time='2026-09-08T08:00:00Z')
        self.add('inside',n=220,time='2026-09-09T08:00:00Z')
        self.add('outside',n=1000,time='2026-09-10T00:00:00Z')
        params={'from':'2026-09-09','to':'2026-09-10'}
        c=self.ledger.analytics(params)['comparison']
        self.assertEqual(c['value'],120);self.assertEqual(c['current'],240)
        self.assertEqual(c['change_percent'],100)
        self.assertEqual(c['start'],'2026-09-08T00:00:00.000Z')
        c=self.ledger.analytics({'from':'2026-09-08','to':'2026-09-09'})['comparison']
        self.assertIsNone(c['change_percent']);self.assertEqual(c['records'],0)

    def test_legacy_excluded_from_size_percentiles_and_no_double_counting(self):
        self.add('native',n=100);self.add('legacy',n=9000,native=False)
        data=self.ledger.analytics({})
        self.assertEqual(data['summary']['total_tokens'],9140)
        self.assertEqual(data['summary']['response_records'],1)
        self.assertEqual(data['summary']['p95_response_tokens'],120)
        self.assertEqual(sum(r['records'] for r in data['distribution']),1)
        with self.ledger.db:self.ledger.db.execute("UPDATE events SET excluded=1 WHERE granularity='snapshot delta'")
        self.assertEqual(self.ledger.analytics({})['summary']['total_tokens'],120)

    def test_response_size_bounds_and_hour_filters(self):
        self.add('small',n=979);self.add('boundary',n=980);self.add('large',n=1100,time='2026-09-09T09:00:00Z')
        self.assertEqual(self.ledger.analytics({'tokens_min':'0','tokens_max':'1000'})['summary']['records'],1)
        self.assertEqual(self.ledger.analytics({'tokens_min':'1000'})['summary']['records'],2)
        params={'facets':json.dumps({'weekday':'3','hour':'08'})}
        self.assertEqual(self.ledger.analytics(params)['summary']['records'],2)
        self.assertEqual(self.ledger.query(params)['summary']['records'],2)

    def test_top_other_and_sorting_are_independent_of_pagination(self):
        for i in range(55):self.add(str(i),n=i,project=f'project-{i:02}')
        data=self.ledger.analytics({'by':'project','offset':'50','sort_by':'input_tokens','direction':'asc'})
        self.assertEqual([r['input_tokens'] for r in data['groups']],list(range(50,55)))
        self.assertEqual(data['total_groups'],55)
        self.assertEqual(sum(r['total_tokens'] for r in data['chart_groups']),data['summary']['total_tokens'])
        self.assertEqual(data['ranking'][0]['input_tokens'],54)
        self.assertEqual(data['top_records'][0]['input_tokens'],54)

    def test_period_fill_and_long_range_are_bounded(self):
        self.add('first',time='2020-01-01T08:00:00Z');self.add('last',time='2026-09-09T08:00:00Z')
        result=self.ledger.analytics({'from':'2020-01-01','to':'2026-09-10'})
        self.assertLessEqual(len(result['timeline']),90)
        self.assertEqual(sum(r['total_tokens'] for r in result['timeline']),240)
        result=self.ledger.analytics({'from':'2026-09-07','to':'2026-09-10'})
        self.assertEqual([r['total_tokens'] for r in result['timeline']],[0,0,120])

    def test_partial_periods_normalize_timezone_and_keep_drill_boundaries(self):
        self.add('before',time='2026-09-08T21:59:59Z')
        self.add('first',time='2026-09-08T22:15:00Z')
        self.add('last',time='2026-09-09T03:00:00Z')
        data=self.ledger.analytics({'from':'2026-09-09T00:05:00+02:00','to':'2026-09-09T04:00:00Z'})
        self.assertEqual(data['summary']['records'],2)
        self.assertEqual(data['timeline'][0]['start'],'2026-09-08T22:05:00.000Z')
        self.assertEqual(data['timeline'][-1]['end'],'2026-09-09T04:00:00.000Z')
        self.assertEqual(sum(r['total_tokens'] for r in data['timeline']),240)
        for bucket in data['timeline']:
            subset=self.ledger.query({'from':bucket['start'],'to':bucket['end']})
            self.assertEqual(subset['summary']['total_tokens'],bucket['total_tokens'])

    def test_model_timeline_reconciles_each_interval_and_drill_for_all_metrics(self):
        self.add('a',n=100,model='Model A',time='2026-09-07T08:00:00Z')
        self.add('b',n=300,model='Model B',time='2026-09-07T08:00:00Z')
        self.add('c',n=1000,model='Model A',time='2026-09-09T08:00:00Z')
        self.add('outside',n=9000,model='Other project',project='/work/B')
        for metric in METRICS:
            params={'from':'2026-09-07','to':'2026-09-10','metric':metric,'facets':json.dumps({'project':'/work/A'})}
            data=self.ledger.analytics(params)
            self.assertEqual({m['model'] for m in data['timeline_models']},{'Model A','Model B'})
            self.assertEqual(sum(m['total'] for m in data['timeline_models']),data['summary'][metric])
            for i,bucket in enumerate(data['timeline']):
                self.assertEqual(sum(m['values'][i] for m in data['timeline_models']),bucket[metric])
                for model in data['timeline_models']:
                    focused=self.ledger.analytics({**params,'from':bucket['start'],'to':bucket['end'],
                        'facets':json.dumps({'project':'/work/A','model':model['model']})})
                    self.assertEqual(focused['summary'][metric],model['values'][i])

    def test_model_timeline_includes_every_model_and_unknown(self):
        for i in range(13):self.add(str(i),model='Unknown' if i==0 else f'model-{i}')
        data=self.ledger.analytics({})
        self.assertEqual(len(data['timeline_models']),13)
        self.assertIn('Unknown',[m['model'] for m in data['timeline_models']])
        self.assertEqual(sum(m['total'] for m in data['timeline_models']),1560)

    def test_even_median_and_weighted_cache_share(self):
        self.add('a',n=100);self.add('b',n=1000)
        data=self.ledger.analytics({})
        self.assertEqual(data['summary']['median_response_tokens'],570)
        self.assertEqual(data['summary']['p95_response_tokens'],1020)
        self.assertEqual(data['summary']['mean_response_tokens'],570)
        self.assertEqual(data['summary']['cache_share'],.5)

    def test_empty_data_and_zero_metric_are_not_false_percentages(self):
        data=self.ledger.analytics({})
        self.assertIsNone(data['summary']['cache_share']);self.assertEqual(data['timeline'],[])
        self.add('a',n=0)
        data=self.ledger.analytics({'metric':'cached_input_tokens'})
        self.assertEqual(data['summary']['cached_input_tokens'],0)
        self.assertIsNone(data['groups'][0]['share'])

    def test_invalid_filters_do_not_become_sql(self):
        for params in ({'metric':'SUM(secret)'},{'by':'e.id; DROP TABLE events'},
                       {'facets':'[]'},{'facets':json.dumps({'project':[]})},
                       {'facets':json.dumps({'bad':'x'})},{'from':'2026-09-10','to':'2026-09-09'}):
            with self.assertRaises(ValueError):self.ledger.analytics(params)
        self.assertEqual(self.ledger.query({})['summary']['records'],0)


if __name__=='__main__':unittest.main()
