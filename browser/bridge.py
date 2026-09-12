"""In-process browser API. No HTTP server, filesystem collector or network client."""
import getpass
import json
import socket
from urllib.parse import urlparse, parse_qs
from pathlib import PurePosixPath
from ledger import Ledger
from demo import seed_demo

# A browser cannot establish the human/device that produced imported evidence.
getpass.getuser = lambda: 'Browser operator (unverified)'
socket.gethostname = lambda: 'This browser (unverified)'
ledger = Ledger(':memory:')


def restore(evidence):
    """Restore data into our own schema, never execute an imported SQL schema."""
    global ledger
    if not isinstance(evidence, dict) or evidence.get('schema') != 'observatory.evidence.v1':
        raise ValueError('Choose a complete Observatory evidence backup.')
    tables = evidence.get('tables')
    fresh = Ledger(':memory:')
    try:
        expected = fresh.evidence_export()['tables']
        if not isinstance(tables, dict) or set(tables) != set(expected):
            raise ValueError('Backup tables do not match this version. Use the matching app version.')
        fresh.db.execute('PRAGMA foreign_keys=OFF')
        with fresh.db:
            for name in expected:
                columns = [r[1] for r in fresh.db.execute('PRAGMA table_info(' + name + ')')]
                rows = tables[name]
                if not isinstance(rows, list) or len(rows) > 1000000:
                    raise ValueError('Invalid or oversized backup table.')
                fresh.db.execute('DELETE FROM ' + name)
                for row in rows:
                    if not isinstance(row, dict) or set(row) != set(columns):
                        raise ValueError('Backup columns do not match this version.')
                    if any(v is not None and type(v) not in (str, int, float) for v in row.values()):
                        raise ValueError('Invalid backup value.')
                    fresh.db.execute('INSERT INTO ' + name + ' (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')',
                                     [row[c] for c in columns])
            if fresh.db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Backup contains broken evidence references.')
            if not fresh.integrity()['valid']:
                raise ValueError('Backup audit chain is damaged. Existing data has been kept.')
        fresh.db.execute('PRAGMA foreign_keys=ON')
        # Force parsing of structured fields before replacing the active workspace.
        fresh.state()
        fresh.query({})
    except Exception:
        fresh.close()
        raise
    ledger.close()
    ledger = fresh
    return {'ok': True}


def dispatch(path, data=None):
    global ledger
    parsed = urlparse(path)
    path = parsed.path
    params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    if path == '/api/state':
        return {**ledger.state(), 'browser': True, 'demo': False, 'csrf': '', 'server_os': 'browser'}
    if path == '/api/ledger': return ledger.query(params)
    if path == '/api/breakdown': return ledger.breakdown(params)
    if path == '/api/event': return ledger.detail(params.get('id', ''))
    if path == '/api/provider': return ledger.provider(params)
    if path == '/api/analytics': return ledger.analytics(params)
    if path == '/api/limits': return ledger.limits(params)
    if path == '/api/export': return ledger.export(params)
    if path == '/api/evidence-export': return ledger.evidence_export()
    if path == '/api/activity':
        order = ledger.order(params, {k:k for k in ('timestamp','actor','action','device','purpose')}, 'timestamp', 'desc')
        return {'activity': [dict(r) for r in ledger.db.execute('SELECT * FROM activity ORDER BY ' + order + ',id LIMIT 500')],
                'audit': [dict(r) for r in ledger.db.execute('SELECT * FROM audit ORDER BY seq DESC LIMIT 500')],
                'activity_count': ledger.db.execute('SELECT COUNT(*) FROM activity').fetchone()[0],
                'audit_count': ledger.db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]}
    if path == '/api/activity-event':
        row = ledger.db.execute('SELECT * FROM activity WHERE id=?', (params.get('id', ''),)).fetchone()
        if not row: raise ValueError('Unknown activity record.')
        return dict(row)
    if not isinstance(data, dict): raise ValueError('Expected a request object.')
    if path == '/api/cost-analysis': return ledger.cost_analysis(data)
    if path == '/api/attribute': return ledger.attribute(data)
    if path == '/api/budget':
        ledger.budget(data)
        return {'ok': True}
    if path == '/api/activity-policy': return ledger.activity_policy(data)
    if path == '/api/import':
        name = str(data.get('name', ''))
        if any(s in PurePosixPath(name).name.lower() for s in ('auth', 'credential', 'secret', '.env')):
            raise ValueError('Authentication and credential files must not be imported.')
        return ledger.import_data(PurePosixPath(name).name, data.get('content'), data.get('scope'), source_label=name if '/' in name else None)
    if path == '/api/acknowledge':
        old = ledger.db.execute('SELECT * FROM alerts WHERE id=?', (data.get('id'),)).fetchone()
        if not old: raise ValueError('Alert not found.')
        with ledger.db:
            ledger.db.execute("UPDATE alerts SET status='acknowledged' WHERE id=?", (data['id'],))
            ledger.audit('alert.acknowledged', data['id'], 'Acknowledged in the browser; not a finding of safety.', dict(old), {'status': 'acknowledged'})
        return {'ok': True}
    if path == '/browser/restore': return restore(data)
    if path == '/browser/reset':
        ledger.close()
        ledger = Ledger(':memory:')
        return {'ok': True}
    if path == '/browser/demo':
        if any(ledger.db.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in ('events','files','buckets','activity')):
            raise ValueError('Try the demo in an empty workspace so fictional usage stays separate.')
        seed_demo(ledger)
        return {'ok': True}
    raise ValueError('This action is unavailable in browser mode. Select files to refresh evidence.')


def request(payload):
    try:
        value = json.loads(payload)
        return json.dumps({'value': dispatch(value['path'], value.get('data'))}, ensure_ascii=False)
    except Exception:
        # Imported text and Python traces must not leak through error messages.
        return json.dumps({'error': 'This file or request could not be processed. Check its format and version; existing evidence has been kept.'})
