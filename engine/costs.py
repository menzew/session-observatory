"""Offline API price scenarios. Decimal arithmetic; no invoices or API calls."""
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
import json

from engine.analytics import DIMENSIONS

D = Decimal
COMPONENTS = ('input', 'cached', 'write', 'output')
PRICE_DATE = '2026-09-09'
PRICE_URL = 'https://developers.openai.com/api/docs/pricing'
CATALOG = {
    'gpt-6-astra': {'input':'10','cached':'1','write':'12.5','output':'50'},
    'gpt-5.6-sol': {'input':'4','cached':'0.4','write':'5','output':'20'},
    'gpt-5.6-terra': {'input':'2','cached':'0.2','write':'2.5','output':'12'},
    'gpt-5.6-luna': {'input':'0.2','cached':'0.02','write':'0.25','output':'1.2'},
}
TIERS = {'standard':D(1),'batch':D('.5'),'flex':D('.5'),'fast':D(2)}
DEFAULTS = dict(target='recorded',tier='standard',volume='1',input_percent='100',output_percent='100',
                cache='observed',cache_percent='80',context='auto',custom={k:'0' for k in COMPONENTS})
REASONS = {'unknown_model':'No verified rate for the recorded model/provider',
           'legacy_context':'Legacy delta: individual request size is unknown',
           'request_limit':'Modeled request exceeds the preset context or output limit',
           'overlapping_cache':'Cache reads plus writes exceed input; partition is ambiguous'}


def number(value, low, high):
    if isinstance(value,bool) or not isinstance(value,(str,int,float)) or len(str(value))>40:
        raise ValueError('Scenario values must be bounded decimal numbers.')
    try: result=D(str(value))
    except InvalidOperation: raise ValueError('Enter a valid scenario number.')
    if not result.is_finite() or not D(low)<=result<=D(high) or result.as_tuple().exponent < -8:
        raise ValueError('Scenario number is outside its supported range or precision.')
    return result


def scenario_config(raw):
    if not isinstance(raw,dict): raise ValueError('A scenario object is required.')
    config={**DEFAULTS,**raw}
    if config['target'] not in (*CATALOG,'recorded','custom') or config['tier'] not in TIERS or config['cache'] not in ('observed','none','percent') or config['context'] not in ('auto','short','long'):
        raise ValueError('Unknown scenario option.')
    for key,low,high in [('volume','0','1000'),('input_percent','0','1000'),('output_percent','0','1000'),('cache_percent','0','100')]:
        config[key]=number(config[key],low,high)
    if not isinstance(config['custom'],dict):raise ValueError('Custom prices must be an object.')
    config['custom']={key:number(config['custom'].get(key,'0'),'0','100000') for key in COMPONENTS}
    return {key:config[key] for key in DEFAULTS}


def estimate(row, config):
    """Price a hypothetical repeat of one source record; subsets never add tokens."""
    target=config['target']
    if target=='recorded':
        if row['provider']!='openai':return None,'unknown_model'
        target='gpt-5.6-sol' if row['model']=='gpt-5.6' else row['model']
    if target not in CATALOG and target!='custom':return None,'unknown_model'
    if config['context']=='auto' and row['granularity']!='response':return None,'legacy_context'
    inp=D(row['input_tokens']);cached=D(row['cached_input_tokens']);write=D(row['cache_write_input_tokens'])
    if cached+write>inp:return None,'overlapping_cache'
    factor=config['input_percent']/100
    inp,cached,write=inp*factor,cached*factor,write*factor
    output=D(row['output_tokens'])*config['output_percent']/100
    if target!='custom' and config['context']=='auto' and (inp+output>1050000 or output>128000):return None,'request_limit'
    if config['cache']=='none':cached=write=D(0)
    elif config['cache']=='percent':
        write_share=write/(inp-cached) if inp>cached else D(0)
        cached=inp*config['cache_percent']/100
        write=(inp-cached)*write_share
    amounts={'input':inp-cached-write,'cached':cached,'write':write,'output':output}
    rates=config['custom'] if target=='custom' else {k:D(v) for k,v in CATALOG[target].items()}
    long=config['context']=='long' or (config['context']=='auto' and inp>272000)
    # Custom rates are flat, user-declared rates; no provider-specific uplift.
    multiplier=TIERS[config['tier']] if target!='custom' else D(1)
    costs={k:amounts[k]*rates[k]*multiplier*config['volume']/1000000*
           (D('1.5') if k=='output' else D(2)) if long and target!='custom' else
           amounts[k]*rates[k]*multiplier*config['volume']/1000000 for k in COMPONENTS}
    return dict(costs,total=sum(costs.values()),long=bool(long and target!='custom')),None


def accumulator():
    return dict(total=D(0),components={k:D(0) for k in COMPONENTS},priced_records=0,priced_tokens=0,long_records=0,reasons=Counter())


def accumulate(acc,row,priced,reason):
    if priced is None:acc['reasons'][reason]+=1;return
    acc['total']+=priced['total'];acc['priced_records']+=1;acc['priced_tokens']+=row['total_tokens'];acc['long_records']+=priced['long']
    for k in COMPONENTS:acc['components'][k]+=priced[k]


def encode(value):
    if isinstance(value,D):return format(value,'f')
    if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
    if isinstance(value,list):return [encode(v) for v in value]
    return value


class CostAnalysis:
    @staticmethod
    def cost_catalog():
        return dict(prices=CATALOG,checked_at=PRICE_DATE,source=PRICE_URL,currency='USD',unit='per million text tokens',
                    defaults=DEFAULTS,reason_labels=REASONS)

    def cost_analysis(self, data):
        with localcontext() as context:
            context.prec=50
            return self._cost_analysis(data)

    def _cost_analysis(self,data):
        from engine.ledger import now,stamp
        params=data.get('filters',{})
        if not isinstance(params,dict) or any(not isinstance(v,str) for v in params.values()):raise ValueError('Invalid cost filters.')
        params=dict(params);params.setdefault('to',now())
        by=params.get('by','project')
        if by not in DIMENSIONS:raise ValueError('Unknown cost grouping.')
        if params.get('from'):
            def normalized(v):return stamp(v+'T00:00:00Z' if len(v)==10 else v)
            if normalized(params['from'])>=normalized(params['to']):raise ValueError('Period end must follow its start.')
        config=scenario_config(data.get('scenario',{}));baseline_config=scenario_config({})
        where,args=self.filters(params)
        rows=self.db.execute('SELECT '+DIMENSIONS[by]+''' AS dimension,e.model,e.granularity,e.input_tokens,
            e.cached_input_tokens,e.cache_write_input_tokens,e.output_tokens,e.total_tokens,
            json_extract(e.details,'$.provider') AS provider,
            json_extract(e.details,'$.usage_reported_fields') AS reported_fields'''+self.JOIN+' WHERE '+where,args)
        baseline,scenario=accumulator(),accumulator()
        alternatives={name:accumulator() for name in CATALOG}
        alternative_configs={name:{**config,'target':name} for name in CATALOG}
        groups={};observed_models=Counter();common_baseline=common_scenario=D(0);common_tokens=common_records=0
        records=tokens=missing_cache=0
        for row in rows:
            records+=1;tokens+=row['total_tokens'];observed_models[row['model']]+=row['total_tokens']
            fields=json.loads(row['reported_fields'] or '[]')
            if 'cached_input_tokens' not in fields or 'cache_write_input_tokens' not in fields:missing_cache+=1
            b,br=estimate(row,baseline_config);s,sr=estimate(row,config)
            accumulate(baseline,row,b,br);accumulate(scenario,row,s,sr)
            if b is not None and s is not None:
                common_baseline+=b['total'];common_scenario+=s['total'];common_tokens+=row['total_tokens'];common_records+=1
            group=groups.setdefault(row['dimension'],dict(dimension=row['dimension'],records=0,tokens=0,baseline=accumulator(),scenario=accumulator()))
            group['records']+=1;group['tokens']+=row['total_tokens']
            accumulate(group['baseline'],row,b,br);accumulate(group['scenario'],row,s,sr)
            for name,other in alternatives.items():
                price,reason=(s,sr) if config['target']==name else estimate(row,alternative_configs[name])
                accumulate(other,row,price,reason)
        def finalize(acc):
            if not acc['priced_records']:acc['total']=None
            acc['reasons']=dict(acc['reasons'])
            return acc
        table=[]
        for g in groups.values():
            b,s=finalize(g['baseline']),finalize(g['scenario'])
            table.append(dict(dimension=g['dimension'],records=g['records'],tokens=g['tokens'],baseline=b['total'],scenario=s['total'],
                priced_tokens=s['priced_tokens'],unpriced_records=g['records']-s['priced_records'],**s['components']))
        ranked=sorted(table,key=lambda r:(r['scenario'] is None,-(r['scenario'] or 0),r['dimension']))
        sort=params.get('sort_by','scenario');direction=params.get('direction','desc')
        if sort not in ('dimension','records','tokens','baseline','scenario','priced_tokens','unpriced_records',*COMPONENTS) or direction not in ('asc','desc'):raise ValueError('Invalid cost sort.')
        table.sort(key=lambda r:r['dimension'])
        known=sorted((r for r in table if r[sort] is not None),key=lambda r:r[sort].casefold() if isinstance(r[sort],str) else r[sort],reverse=direction=='desc')
        unknown=[r for r in table if r[sort] is None]
        return encode(dict(schema='observatory.cost-scenario.v1',as_of=now(),catalog=self.cost_catalog(),filters=params,scenario_config=config,
            records=records,tokens=tokens,missing_cache_fields=missing_cache,by=by,groups=known+unknown,ranking=ranked[:10],
            observed_models=[dict(model=k,tokens=v) for k,v in sorted(observed_models.items())],
            baseline=finalize(baseline),scenario=finalize(scenario),
            comparison=dict(baseline=common_baseline,scenario=common_scenario,change=common_scenario-common_baseline if common_records else None,
                percent=(common_scenario-common_baseline)/common_baseline*100 if common_baseline else None,records=common_records,tokens=common_tokens),
            alternatives=[dict(model=name,**finalize(acc)) for name,acc in alternatives.items()] ))
