import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from costs import COMPONENTS, estimate, scenario_config
from ledger import Ledger
from test_ledger import line


class CostTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.ledger=Ledger(Path(self.temp.name)/'ledger.sqlite3')
        self.row=dict(provider='openai',model='gpt-5.6-sol',granularity='response',input_tokens=1000,
                      cached_input_tokens=600,cache_write_input_tokens=100,output_tokens=100,
                      reasoning_output_tokens=70,total_tokens=1100)

    def tearDown(self):
        self.ledger.close();self.temp.cleanup()

    def price(self,row=None,**config):
        return estimate(row or self.row,scenario_config(config))

    def add(self,ident,project='/cost/A',model='gpt-5.6-sol',n=1000,native=True):
        content=line('session_meta',dict(id='task-'+ident,cwd=project,model_provider='openai'))
        content+=line('turn_context',dict(model=model))
        counts=dict(input_tokens=n,cached_input_tokens=n//2,cache_write_input_tokens=0,output_tokens=100,reasoning_output_tokens=70)
        if native:content+=line('token_usage_record',dict(response_id=ident,usage=counts))
        else:content+=line('event_msg',dict(type='token_count',info=dict(total_token_usage=counts)))
        self.ledger.import_data(ident+'.jsonl',content.decode(),'')

    def report(self,scenario=None,**filters):
        return self.ledger.cost_analysis(dict(filters=filters,scenario=scenario or {}))

    def test_partition_and_reasoning_not_added_twice(self):
        p,reason=self.price()
        self.assertIsNone(reason)
        self.assertEqual([p[k] for k in COMPONENTS],list(map(D,['.0012','.00024','.0005','.002'])))
        self.assertEqual(p['total'],D('.00394'))
        self.assertEqual(self.price(volume='2')[0]['total'],D('.00788'))
        self.assertEqual(self.price(output_percent='50')[0]['total'],D('.00294'))

    def test_context_boundary_scaling_and_repetition(self):
        row={**self.row,'input_tokens':272000,'cached_input_tokens':0,'cache_write_input_tokens':0}
        self.assertFalse(self.price(row)[0]['long'])
        self.assertFalse(self.price(row,volume='2')[0]['long'])
        row['input_tokens']+=1
        p,_=self.price(row)
        self.assertTrue(p['long']);self.assertEqual(p['total'],D('2.179008'))
        self.assertFalse(self.price(row,input_percent='50')[0]['long'])
        p,_=self.price(context='long')
        self.assertEqual(p['total'],D('.00688'))

    def test_tiers_and_custom_decimal_precision(self):
        for tier,factor in [('standard','1'),('batch','.5'),('flex','.5'),('fast','2')]:
            self.assertEqual(self.price(tier=tier)[0]['total'],D('.00394')*D(factor))
        custom=dict(input='0.00000001',cached='0',write='0',output='0')
        p,_=self.price(target='custom',tier='fast',context='long',custom=custom)
        self.assertEqual(p['total'],D('.000000000003'))
        self.assertFalse(p['long'])
        self.assertEqual(self.price(target='custom')[0]['total'],0)

    def test_cache_scenarios_keep_partition(self):
        p,_=self.price(cache='none')
        self.assertEqual(p['total'],D('.006'))
        p,_=self.price(cache='percent',cache_percent='80')
        self.assertEqual(p['total'],D('.00317'))
        p,_=self.price(cache='percent',cache_percent='100')
        self.assertEqual(p['total'],D('.0024'))
        self.assertEqual(self.price(input_percent='0')[0]['total'],D('.002'))
        self.assertEqual(self.price({**self.row,'cached_input_tokens':950})[1],'overlapping_cache')

    def test_unknown_models_and_request_evidence(self):
        for row in [{**self.row,'model':'gpt-5.6-sol-guessed'}, {**self.row,'provider':'unverified'}]:
            self.assertEqual(self.price(row)[1],'unknown_model')
            self.assertIsNotNone(self.price(row,target='gpt-5.6-terra')[0])
        self.assertEqual(self.price({**self.row,'model':'gpt-5.6'})[0]['total'],D('.00394'))
        legacy={**self.row,'granularity':'snapshot delta'}
        self.assertEqual(self.price(legacy)[1],'legacy_context')
        self.assertIsNotNone(self.price(legacy,context='short')[0])
        for row in [{**self.row,'input_tokens':1050000},{**self.row,'output_tokens':128001}]:
            self.assertEqual(self.price(row)[1],'request_limit')
            self.assertIsNotNone(self.price(row,context='short')[0])

    def test_partial_coverage_does_not_create_false_savings(self):
        self.add('known');self.add('unknown',model='unknown',n=9000)
        data=self.report(dict(target='gpt-5.6-terra'))
        self.assertEqual(data['baseline']['priced_records'],1)
        self.assertEqual(data['scenario']['priced_records'],2)
        c=data['comparison']
        self.assertEqual(c['records'],1);self.assertEqual(c['tokens'],1100)
        self.assertEqual(D(c['baseline']),D('.0042'))
        self.assertEqual(D(c['scenario']),D('.0023'))
        self.assertEqual(D(c['change']),D('-.0019'))
        self.assertEqual(data['baseline']['reasons'],{'unknown_model':1})
        unknown=self.report(dict(target='gpt-5.6-terra'),facets=json.dumps({'model':'unknown'}))
        self.assertIsNone(unknown['baseline']['total']);self.assertIsNone(unknown['comparison']['change'])

    def test_group_components_filters_exports_and_read_only(self):
        for i in range(6):self.add(str(i),project=f'/cost/{i}',n=(i+1)*1000)
        before=self.ledger.integrity();changes=self.ledger.db.total_changes
        data=self.report(dict(volume='2',cache='none'))
        self.assertEqual(sum(D(g['scenario']) for g in data['groups']),D(data['scenario']['total']))
        self.assertEqual(sum(D(v) for v in data['scenario']['components'].values()),D(data['scenario']['total']))
        self.assertEqual(sum(D(g['baseline']) for g in data['groups']),D(data['baseline']['total']))
        self.assertEqual(sum(g['tokens'] for g in data['groups']),data['tokens'])
        for g in data['groups']:self.assertEqual(sum(D(g[k]) for k in COMPONENTS),D(g['scenario']))
        self.assertTrue(all(alt['priced_records']==6 for alt in data['alternatives']))
        self.assertEqual(before,self.ledger.integrity());self.assertEqual(changes,self.ledger.db.total_changes)
        filters={'facets':json.dumps({'project':'/cost/1'}),'by':'task'}
        focused=self.report(**filters)
        self.assertEqual(focused['records'],1)
        self.assertEqual(focused['tokens'],self.ledger.query(filters)['summary']['total_tokens'])
        self.assertEqual(focused['groups'][0]['dimension'],'task-1')
        self.assertEqual(focused['catalog']['currency'],'USD')

    def test_sort_all_groups_and_unpriced_last(self):
        for i in range(55):self.add(str(i),project=f'/cost/{i:02}',n=i*100)
        self.add('unknown',project='/cost/unknown',model='unknown')
        data=self.report(sort_by='scenario',direction='asc',offset='50')
        self.assertEqual(len(data['groups']),56)
        self.assertEqual(data['groups'][0]['dimension'],'/cost/00')
        self.assertIsNone(data['groups'][-1]['scenario'])
        data=self.report(sort_by='scenario',direction='desc')
        self.assertEqual(data['groups'][0]['dimension'],'/cost/54')
        self.assertIsNone(data['groups'][-1]['scenario'])
        self.assertEqual(data['ranking'][0]['dimension'],'/cost/54')

    def test_empty_excluded_and_legacy(self):
        data=self.report();self.assertIsNone(data['baseline']['total']);self.assertIsNone(data['comparison']['percent'])
        self.add('legacy',native=False)
        self.assertEqual(self.report()['scenario']['reasons'],{'legacy_context':1})
        self.assertEqual(self.report(dict(context='short'))['scenario']['priced_records'],1)
        with self.ledger.db:self.ledger.db.execute('UPDATE events SET excluded=1')
        self.assertEqual(self.report()['records'],0)

    def test_invalid_config_and_filters(self):
        for value in ['NaN','Infinity','-1','1001','1e9999','0.000000001',True,[],{}]:
            with self.assertRaises(ValueError,msg=str(value)):scenario_config({'volume':value})
        for params in [{'target':'guessed'},{'cache_percent':'101'},{'custom':[]},{'custom':{'input':'-1'}}]:
            with self.assertRaises(ValueError):scenario_config(params)
        for filters in [{'by':'DROP TABLE events'},{'sort_by':'bad'},{'direction':'bad'},{'from':'2026-09-10','to':'2026-09-09'},{'facets':'[]'}]:
            with self.assertRaises(ValueError):self.report(**filters)


if __name__=='__main__':unittest.main()
