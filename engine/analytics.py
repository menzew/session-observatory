"""Read-only analytics over the same included evidence and filters as the ledger."""
import math
from datetime import datetime, timedelta, timezone


DIMENSIONS = {
    'project': "COALESCE(NULLIF(a.project,''),e.project)",
    'person': "COALESCE(NULLIF(a.principal,''),NULLIF(e.actor,''),'Unknown')",
    'purpose': "COALESCE(NULLIF(a.purpose,''),'Not declared')",
    'task': "COALESCE(NULLIF(e.thread_id,''),'Unknown')",
    'model': 'e.model', 'application': 'e.application',
    'device': "COALESCE(NULLIF(e.device,''),'Unknown')",
    'directory': "COALESCE(NULLIF(e.cwd,''),'Unknown')",
    'branch': "COALESCE(NULLIF(json_extract(e.details,'$.branch'),''),'Unknown')",
    'evidence': 'e.granularity', 'day': 'substr(e.timestamp,1,10)',
    'weekday': "strftime('%w',e.timestamp)", 'hour': "strftime('%H',e.timestamp)",
}
METRICS = ('total_tokens', 'input_tokens', 'cached_input_tokens', 'output_tokens',
           'reasoning_output_tokens', 'cache_write_input_tokens', 'uncached_input_tokens', 'records')


class Analytics:
    def analytics(self, params):
        from engine.ledger import TOKEN_FIELDS, now, stamp
        metric = params.get('metric', 'total_tokens')
        by = params.get('by', 'project')
        if metric not in METRICS or by not in DIMENSIONS: raise ValueError('Unknown analytics metric or dimension.')
        params = dict(params)
        as_of = now()
        params.setdefault('to', as_of)
        for key in ('from','to'):
            if params.get(key):
                value=params[key]
                params[key]=stamp(value+'T00:00:00Z' if len(value)==10 else value)
        where, args = self.filters(params)
        base = self.JOIN + ' WHERE ' + where
        sums = ','.join('COALESCE(SUM(e.' + k + '),0) AS ' + k for k in TOKEN_FIELDS)
        aggregates = '''COUNT(*) AS records,COUNT(DISTINCT NULLIF(e.thread_id,'')) AS tasks,
          COUNT(DISTINCT COALESCE(NULLIF(a.project,''),e.project)) AS projects,
          MIN(e.timestamp) AS first_seen,MAX(e.timestamp) AS last_seen,
          COALESCE(SUM(e.input_tokens-e.cached_input_tokens),0) AS uncached_input_tokens,
          COALESCE(SUM(CASE WHEN e.granularity='response' THEN 1 ELSE 0 END),0) AS response_records,
          COALESCE(SUM(CASE WHEN e.granularity='response' THEN e.total_tokens ELSE 0 END),0) AS response_tokens,
          COALESCE(SUM(CASE WHEN COALESCE(a.purpose,'')='' THEN e.total_tokens ELSE 0 END),0) AS undeclared_tokens'''
        summary = dict(self.db.execute('SELECT ' + sums + ',' + aggregates + base, args).fetchone())
        n = summary['response_records']
        summary['mean_response_tokens'] = summary['response_tokens'] / n if n else None
        for name, quantile in (('p95_response_tokens', .95),):
            summary[name] = self.db.execute('SELECT e.total_tokens' + base + " AND e.granularity='response' ORDER BY e.total_tokens,e.id LIMIT 1 OFFSET ?",
                [*args, max(0, math.ceil(n * quantile)-1)]).fetchone()[0] if n else None
        middle = [r[0] for r in self.db.execute('SELECT e.total_tokens' + base + " AND e.granularity='response' ORDER BY e.total_tokens,e.id LIMIT ? OFFSET ?",
            [*args, 1 if n%2 else 2, max(0,(n-1)//2)])] if n else []
        summary['median_response_tokens'] = sum(middle)/len(middle) if middle else None
        summary['cache_share'] = summary['cached_input_tokens'] / summary['input_tokens'] if summary['input_tokens'] else None
        comparison = None
        if params.get('from'):
            def dt(value): return datetime.fromisoformat(stamp(value + 'T00:00:00Z' if len(value)==10 else value).replace('Z','+00:00'))
            start, end = dt(params['from']), dt(params['to'])
            if end <= start: raise ValueError('The period end must follow its start.')
            previous_from = start - (end-start)
            previous = {**params, 'from': previous_from.isoformat(), 'to': start.isoformat()}
            pwhere, pargs = self.filters(previous)
            prior = dict(self.db.execute('SELECT ' + sums + ',COUNT(*) AS records,COALESCE(SUM(e.input_tokens-e.cached_input_tokens),0) AS uncached_input_tokens' + self.JOIN + ' WHERE ' + pwhere, pargs).fetchone())
            comparison = dict(start=stamp(previous_from.isoformat()), end=stamp(start.isoformat()),
                value=prior[metric], current=summary[metric], records=prior['records'],
                change_percent=(summary[metric]-prior[metric])/prior[metric]*100 if prior[metric] else None)

        groups_sql = 'SELECT ' + DIMENSIONS[by] + ' AS dimension,' + sums + ',COUNT(*) AS records,COUNT(DISTINCT NULLIF(e.thread_id,\'\')) AS tasks,COALESCE(SUM(e.input_tokens-e.cached_input_tokens),0) AS uncached_input_tokens' + base + ' GROUP BY 1'
        # Compute chart shares over every group, independent of table sorting/page.
        ranked = [dict(r) for r in self.db.execute(groups_sql + ' ORDER BY ' + metric + ' DESC,dimension COLLATE NOCASE', args)]
        chart_groups = [dict(r, other=False) for r in ranked[:5]]
        if len(ranked)>5:
            chart_groups.append(dict(dimension='All other groups', other=True,
                **{k:sum(r[k] for r in ranked[5:]) for k in (*TOKEN_FIELDS, 'uncached_input_tokens', 'records')}))
        ordering = self.order(params, {**{k:k for k in ('dimension','records','tasks',*TOKEN_FIELDS,'uncached_input_tokens')}, 'share':metric, 'cache_share':'(1.0*SUM(e.cached_input_tokens)/NULLIF(SUM(e.input_tokens),0))'}, 'total_tokens', 'desc')
        offset = max(0,int(params.get('offset',0)))
        rows = [dict(r) for r in self.db.execute(groups_sql + ' ORDER BY ' + ordering + ',dimension LIMIT 50 OFFSET ?', [*args,offset])]
        for row in rows:
            row['share'] = row[metric]/summary[metric] if summary[metric] else None
            row['cache_share'] = row['cached_input_tokens']/row['input_tokens'] if row['input_tokens'] else None

        daily = [dict(r) for r in self.db.execute('SELECT substr(e.timestamp,1,10) AS day,' + sums + ',COUNT(*) AS records,COALESCE(SUM(e.input_tokens-e.cached_input_tokens),0) AS uncached_input_tokens' + base + ' GROUP BY 1 ORDER BY 1', args)]
        timeline = []
        interval_days = 1
        if daily:
            selected_start = datetime.fromisoformat(params.get('from', daily[0]['day']).replace('Z','+00:00')).replace(tzinfo=timezone.utc)
            start = selected_start.replace(hour=0,minute=0,second=0,microsecond=0)
            end = datetime.fromisoformat(stamp(params['to'] + 'T00:00:00Z' if len(params['to'])==10 else params['to']).replace('Z','+00:00'))
            days = max(1,math.ceil((end-start).total_seconds()/86400))
            interval_days = max(1,math.ceil(days/90))
            for index in range(math.ceil(days/interval_days)):
                first = start + timedelta(days=index*interval_days)
                last = min(first+timedelta(days=interval_days),end)
                timeline.append(dict(start=stamp(max(first,selected_start).isoformat()),end=stamp(last.isoformat()),
                    **{k:0 for k in (*TOKEN_FIELDS,'records','uncached_input_tokens')}))
            for day in daily:
                index=(datetime.fromisoformat(day['day']).replace(tzinfo=timezone.utc)-start).days//interval_days
                for key in (*TOKEN_FIELDS,'records','uncached_input_tokens'): timeline[index][key]+=day[key]

        metric_expr = 'COUNT(*)' if metric=='records' else 'SUM(e.input_tokens-e.cached_input_tokens)' if metric=='uncached_input_tokens' else 'SUM(e.'+metric+')'
        model_series = {}
        if timeline:
            model_days = self.db.execute('SELECT substr(e.timestamp,1,10) AS day,e.model AS model,' + metric_expr +
                ' AS value' + base + ' GROUP BY 1,2 ORDER BY 1,2', args)
            for row in model_days:
                series = model_series.setdefault(row['model'], dict(model=row['model'], values=[0]*len(timeline), total=0))
                index = (datetime.fromisoformat(row['day']).replace(tzinfo=timezone.utc)-start).days//interval_days
                series['values'][index] += row['value']
                series['total'] += row['value']
        timeline_models = sorted(model_series.values(), key=lambda r:(-r['total'],r['model']))
        heatmap = [dict(r) for r in self.db.execute("SELECT strftime('%w',e.timestamp) AS weekday,strftime('%H',e.timestamp) AS hour," + metric_expr + ' AS value,COUNT(*) AS records' + base + ' GROUP BY 1,2', args)]
        distribution = [dict(r) for r in self.db.execute('''SELECT CASE WHEN e.total_tokens<1000 THEN 0 WHEN e.total_tokens<10000 THEN 1 WHEN e.total_tokens<100000 THEN 2 WHEN e.total_tokens<1000000 THEN 3 ELSE 4 END AS bucket,COUNT(*) AS records,SUM(e.total_tokens) AS total_tokens''' + base + " AND e.granularity='response' GROUP BY 1 ORDER BY 1",args)]
        top_records = [self.serialize(r) for r in self.db.execute('SELECT ' + self.SELECT + base + ' ORDER BY e.total_tokens DESC,e.id LIMIT 10',args)]
        return dict(summary=summary,metric=metric,by=by,comparison=comparison,groups=rows,total_groups=len(ranked),
            chart_groups=chart_groups,ranking=ranked[:10],timeline=timeline,timeline_models=timeline_models,interval_days=interval_days,
            heatmap=heatmap,distribution=distribution,top_records=top_records,offset=offset,
            as_of=as_of,period=dict(start=params.get('from'),end=params['to']))
