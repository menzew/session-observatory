"""Historical quota readings from metering logs; no account authentication."""
import json
import math


SCHEMA = '''
CREATE TABLE IF NOT EXISTS limit_snapshots (
 id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, source TEXT NOT NULL,
 line INTEGER NOT NULL, sha256 TEXT NOT NULL, received_at TEXT NOT NULL,
 thread_id TEXT NOT NULL, plan TEXT NOT NULL, limit_id TEXT NOT NULL,
 limit_name TEXT NOT NULL, windows TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS limit_time ON limit_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS limit_context ON limit_snapshots(source,thread_id,timestamp,line);
CREATE TABLE IF NOT EXISTS limit_files (
 path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL);
'''


def normalize_limits(value, timestamp, ctx, source, line, sha, stamp, digest, now):
    if not isinstance(value, dict):
        raise ValueError('Invalid limit reading.')
    windows = {}
    for slot in ('primary', 'secondary'):
        window = value.get(slot)
        if window is None:
            windows[slot] = None
            continue
        if not isinstance(window, dict): raise ValueError('Invalid window.')
        percent = window.get('used_percent', window.get('usedPercent'))
        duration = window.get('window_minutes', window.get('windowDurationMins'))
        reset = window.get('resets_at', window.get('resetsAt'))
        if percent is not None and (isinstance(percent, bool) or not isinstance(percent, (int, float)) or not math.isfinite(percent) or not 0 <= percent <= 100):
            raise ValueError('Invalid utilization.')
        if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int) or not 0 < duration <= 5256000):
            raise ValueError('Invalid duration.')
        if reset is not None and (isinstance(reset, bool) or not isinstance(reset, (int, float))):
            raise ValueError('Invalid reset.')
        windows[slot] = dict(used_percent=percent, window_minutes=duration,
                             resets_at=stamp(reset) if reset is not None else None)
    def label(snake, camel):
        v = value.get(snake, value.get(camel))
        return v[:200] if isinstance(v, str) else ''
    return dict(id=digest(source + ':' + str(line) + ':' + sha), timestamp=stamp(timestamp),
                source=source, line=line, sha256=sha, received_at=now(),
                thread_id=ctx.get('thread_id', ''), plan=label('plan_type', 'planType'),
                limit_id=label('limit_id', 'limitId'), limit_name=label('limit_name', 'limitName'),
                windows=json.dumps(windows, sort_keys=True, separators=(',', ':')))


class LimitAccounting:
    def persist_limits(self, records):
        added = 0
        for row in records:
            added += self.db.execute('INSERT OR IGNORE INTO limit_snapshots (' + ','.join(row) +
                ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values())).rowcount
        return added

    @staticmethod
    def limit_record(row):
        if row is None: return None
        row = dict(row)
        row['windows'] = json.loads(row['windows'])
        return row

    def limits(self, params):
        from ledger import stamp, now
        clauses, args = ['1=1'], []
        for key, op in (('from', '>='), ('to', '<')):
            if params.get(key):
                v = params[key]
                clauses.append('timestamp' + op + '?')
                args.append(stamp(v + 'T00:00:00Z' if len(v) == 10 else v))
        for key in ('source', 'thread_id', 'plan'):
            if params.get(key):
                clauses.append(key + '=?'); args.append(params[key])
        if params.get('q'):
            clauses.append('(source LIKE ? OR thread_id LIKE ? OR plan LIKE ? OR limit_id LIKE ?)')
            args.extend(['%' + params['q'][:300] + '%'] * 4)
        where = ' WHERE ' + ' AND '.join(clauses)
        ordering = self.order(params, {**{k: k for k in ('timestamp','plan','limit_id','source','thread_id')},
            'primary': "json_extract(windows,'$.primary.used_percent')",
            'secondary': "json_extract(windows,'$.secondary.used_percent')"}, 'timestamp', 'desc')
        offset = max(0, int(params.get('offset', 0)))
        rows = self.db.execute('SELECT * FROM limit_snapshots' + where + ' ORDER BY ' + ordering + ',id LIMIT 50 OFFSET ?', [*args, offset])
        latest = self.db.execute('SELECT * FROM limit_snapshots' + where + ' ORDER BY timestamp DESC,source,line DESC,id LIMIT 1', args).fetchone()
        return dict(snapshots=[self.limit_record(r) for r in rows], latest=self.limit_record(latest),
            total=self.db.execute('SELECT COUNT(*) FROM limit_snapshots' + where, args).fetchone()[0],
            offset=offset, checked_at=now())

    def limit_context(self, observations, event):
        """Prior evidence only, from the same observed file and its source task."""
        from ledger import stamp
        result = []
        thread = event['details'].get('source_thread_id') or event['thread_id']
        if not thread: return result
        for observation in observations:
            row = self.db.execute('''SELECT * FROM limit_snapshots
              WHERE source=? AND thread_id=? AND timestamp<=? AND line<=?
              ORDER BY timestamp DESC,line DESC,id LIMIT 1''',
              (observation['source'], thread, stamp(event['details'].get('source_timestamp') or event['timestamp']), observation['line'])).fetchone()
            if row is not None: result.append(self.limit_record(row))
        return result
