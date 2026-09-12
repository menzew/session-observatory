#!/usr/bin/env python3
"""Loopback-only app server. Python standard library; no external services required."""
import argparse
import hmac
import json
import mimetypes
import os
import re
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from ledger import Ledger, now

STATIC = Path(__file__).parent / 'static'


def loopback_authority(value):
    """Validate a browser-facing loopback host, including a forwarded local port."""
    match = re.fullmatch(r'(localhost|127\.0\.0\.1|\[::1\])(?::([0-9]{1,5}))?', value, re.IGNORECASE)
    if not match: return None
    port = int(match[2]) if match[2] else 80
    if not 1 <= port <= 65535: return None
    return match[1].lower(), port


def make_server(ledger, port=8787, demo=False):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Search terms and identifiers never enter HTTP access logs.

        def permitted(self, mutation=False):
            hosts = self.headers.get_all('Host', [])
            if len(hosts) != 1: return False
            authority = loopback_authority(hosts[0])
            if authority is None: return False
            # A desktop browser may forward a different local port to this
            # listener. Match Origin to the browser-facing Host, not bind port.
            # Forwarded/X-Forwarded-Host headers do not grant additional trust.
            origins = self.headers.get_all('Origin', [])
            if len(origins) > 1: return False
            if origins:
                origin = origins[0]
                if not origin.startswith('http://') or loopback_authority(origin[7:]) != authority: return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site': return False
            if mutation and not hmac.compare_digest(self.headers.get('X-Observatory-Token', ''), token): return False
            return True

        def send(self, code, value, content_type='application/json', download=None):
            body = json.dumps(value, ensure_ascii=False).encode() if content_type == 'application/json' else value
            if isinstance(body, str): body = body.encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if download: self.send_header('Content-Disposition', f'attachment; filename="{download}"')
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass

        def do_GET(self):
            if not self.permitted(): return self.send(403, {'error': 'Only same-origin local access is allowed.'})
            parsed = urlparse(self.path)
            params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
            path = parsed.path
            try:
                with ledger.lock:
                    if path == '/api/state':
                        state = ledger.state()
                        if demo: state.update(device='Demo workspace', operator='Demo operator')
                        return self.send(200, {**state, 'csrf': token, 'demo': demo})
                    if path == '/api/ledger': return self.send(200, ledger.query(params))
                    if path == '/api/breakdown': return self.send(200, ledger.breakdown(params))
                    if path == '/api/event': return self.send(200, ledger.detail(params.get('id', '')))
                    if path == '/api/provider': return self.send(200, ledger.provider(params))
                    if path == '/api/analytics': return self.send(200, ledger.analytics(params))
                    if path == '/api/limits': return self.send(200, ledger.limits(params))
                    if path == '/api/activity':
                        ordering = ledger.order(params, {k:k for k in ('timestamp','actor','action','device','purpose')}, 'timestamp', 'desc')
                        return self.send(200, {'activity': [dict(r) for r in ledger.db.execute('SELECT * FROM activity ORDER BY ' + ordering + ',id LIMIT 500')],
                                               'audit': [dict(r) for r in ledger.db.execute('SELECT * FROM audit ORDER BY seq DESC LIMIT 500')],
                                               'activity_count': ledger.db.execute('SELECT COUNT(*) FROM activity').fetchone()[0],
                                               'audit_count': ledger.db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]})
                    if path == '/api/activity-event':
                        row = ledger.db.execute('SELECT * FROM activity WHERE id=?', (params.get('id', ''),)).fetchone()
                        if not row: raise ValueError('Unknown activity record.')
                        return self.send(200, dict(row))
                    if path == '/api/export': return self.send(200, ledger.export(params), 'text/csv; charset=utf-8', 'observatory-ledger.csv')
                    if path == '/api/evidence-export': return self.send(200, ledger.evidence_export(), download='observatory-evidence.json')
                assets = {'/': 'index.html', '/app.js': 'app.js', '/limits.js': 'limits.js', '/analytics.js': 'analytics.js', '/costs.js': 'costs.js', '/style.css': 'style.css', '/favicon.svg': 'favicon.svg'}
                if path in assets:
                    file = STATIC / assets[path]
                    return self.send(200, file.read_bytes(), mimetypes.guess_type(file)[0] or 'application/octet-stream')
                return self.send(404, {'error': 'Not found.'})
            except (ValueError, TypeError, KeyError): return self.send(400, {'error': 'The request contains invalid filters or an unknown record.'})
            except Exception: return self.send(500, {'error': 'The request could not be completed. Existing records have not been deleted.'})

        def do_POST(self):
            if not self.permitted(True): return self.send(403, {'error': 'The local request token is missing or invalid. Reload the app.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(415, {'error': 'JSON is required.'})
            try:
                length = int(self.headers.get('Content-Length', 0))
                if length <= 0 or length > 36 * 1024 * 1024: return self.send(413, {'error': 'Request size must be below 36 MB.'})
                self.connection.settimeout(30)
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict): raise ValueError('Expected a request object.')
                path = urlparse(self.path).path
                if demo and path != '/api/cost-analysis':
                    return self.send(403, {'error': 'Demo data is read-only. Start without --demo to use your own records.'})
                with ledger.lock:
                    if path == '/api/cost-analysis': return self.send(200, ledger.cost_analysis(data))
                    if path == '/api/attribute': return self.send(200, ledger.attribute(data))
                    if path == '/api/budget':
                        ledger.budget(data); return self.send(200, {'ok': True})
                    if path == '/api/activity-policy': return self.send(200, ledger.activity_policy(data))
                    if path == '/api/source/save':
                        source = ledger.save_source(data)
                        threading.Thread(target=ledger.scan, daemon=True).start()
                        return self.send(200, source)
                    if path == '/api/source/remove':
                        ledger.remove_source(data)
                        return self.send(200, {'ok': True})
                    if path == '/api/import': return self.send(200, ledger.import_data(data.get('name'), data.get('content'), data.get('scope')))
                    if path == '/api/acknowledge':
                        old = ledger.db.execute('SELECT * FROM alerts WHERE id=?', (data.get('id'),)).fetchone()
                        if not old: raise ValueError('Alert not found.')
                        with ledger.db:
                            ledger.db.execute("UPDATE alerts SET status='acknowledged' WHERE id=?", (data['id'],))
                            ledger.audit('alert.acknowledged', data['id'], 'Acknowledged in the local app; not a finding of safety.', dict(old), {'status': 'acknowledged'})
                        return self.send(200, {'ok': True})
                    if path == '/api/scan':
                        if not ledger.scanning: threading.Thread(target=ledger.scan, daemon=True).start()
                        return self.send(202, {'ok': True})
                return self.send(404, {'error': 'Not found.'})
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                # Error messages are controlled locally, except JSON parse errors (no document contents).
                message = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else 'Invalid import or request. No partial changes were committed.'
                return self.send(400, {'error': message[:400]})
            except Exception: return self.send(500, {'error': 'The operation failed. Review the data and try again.'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description='Session Observatory: local token accounting and evidence.')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--db', default=str(Path(__file__).parent / '.data' / 'ledger.sqlite3'))
    parser.add_argument('--source', action='append', help='Codex home to index. Repeat for multiple homes.')
    parser.add_argument('--no-scan', action='store_true', help='Use import-only mode.')
    parser.add_argument('--demo', action='store_true', help='Explore fictional data in memory without reading local source folders.')
    args = parser.parse_args()
    if args.demo and (args.source or args.no_scan or args.db != parser.get_default('db')):
        parser.error('--demo cannot be combined with --source, --no-scan, or a custom --db.')
    os.umask(0o077)
    roots = [] if args.no_scan or args.demo else (args.source or [os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))])
    ledger = Ledger(':memory:' if args.demo else args.db, roots, override_sources=bool(args.source or args.no_scan))
    if args.demo:
        from demo import seed_demo
        seed_demo(ledger)
    server = make_server(ledger, args.port, demo=args.demo)
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            ledger.scan()
            stop.wait(30)

    if not args.demo:
        threading.Thread(target=worker, daemon=True).start()
    print(f'Session Observatory: http://127.0.0.1:{server.server_address[1]}', flush=True)
    print('Fictional demo data in memory. No local folders are read.' if args.demo else
          'Local metadata collection. No OpenAI credentials or network APIs are used.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        stop.set(); server.server_close()
        if args.demo: ledger.close()


if __name__ == '__main__': main()
