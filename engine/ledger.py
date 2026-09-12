"""Metadata-only accounting. No authentication files, prompt bodies or network calls."""
from __future__ import annotations

import csv
import getpass
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path, PureWindowsPath
import re
import uuid
import socket
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation

from engine.costs import CostAnalysis
from engine.analytics import Analytics, DIMENSIONS
from engine.limits import LimitAccounting, SCHEMA as LIMIT_SCHEMA, normalize_limits

VERSION = '1.0.0'
TOKEN_FIELDS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
                'output_tokens', 'reasoning_output_tokens', 'total_tokens')
MAX_LINE = 16 * 1024 * 1024


def bounded_lines(stream):
    """Keep at most one bounded physical line in memory, including ignored bodies."""
    while True:
        raw = stream.readline(MAX_LINE + 1)
        if not raw: return
        if len(raw) > MAX_LINE and not raw.endswith(b'\n'):
            tail = raw
            while tail and not tail.endswith(b'\n'):
                tail = stream.readline(MAX_LINE + 1)
        yield raw


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256((value if isinstance(value, bytes) else value.encode())).hexdigest()


def stamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        dt = datetime.fromtimestamp(value, timezone.utc)
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError('Timestamps must include a timezone.')
    else:
        raise ValueError('A timestamp is required.')
    return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def text(value, limit=2048):
    return value[:limit] if isinstance(value, str) else ''


def usage(value):
    if not isinstance(value, dict):
        raise ValueError('Usage must be an object.')
    if 'input_tokens' not in value or 'output_tokens' not in value:
        raise ValueError('Input and output token counts are required.')
    result = {}
    for key in TOKEN_FIELDS:
        val = value.get(key, 0)
        if isinstance(val, bool) or not isinstance(val, int) or not 0 <= val <= 10**15:
            raise ValueError('Token counts must be non-negative integers below 10^15.')
        result[key] = val
    if 'total_tokens' not in value:
        result['total_tokens'] = result['input_tokens'] + result['output_tokens']
    if result['cached_input_tokens'] > result['input_tokens']:
        raise ValueError('Cached input exceeds input tokens.')
    if result['cache_write_input_tokens'] > result['input_tokens']:
        raise ValueError('Cache write exceeds input tokens.')
    if result['reasoning_output_tokens'] > result['output_tokens']:
        raise ValueError('Reasoning output exceeds output tokens.')
    if result['total_tokens'] != result['input_tokens'] + result['output_tokens']:
        raise ValueError('Total tokens do not equal input plus output.')
    return result


class Ledger(LimitAccounting, Analytics, CostAnalysis):
    def __init__(self, db_path, roots=(), override_sources=False):
        self.db_path = str(db_path)
        self.lock = threading.RLock()
        self.scanning = False
        self.progress = {'running': False, 'done': 0, 'total': 0, 'last_scan': None, 'error': None}
        Path(db_path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS events (
          id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, source_kind TEXT NOT NULL,
          granularity TEXT NOT NULL, project TEXT NOT NULL, cwd TEXT NOT NULL,
          thread_id TEXT NOT NULL, turn_id TEXT NOT NULL, response_id TEXT NOT NULL,
          parent_id TEXT NOT NULL, actor TEXT NOT NULL, device TEXT NOT NULL,
          application TEXT NOT NULL, model TEXT NOT NULL, account_ref TEXT NOT NULL,
          input_tokens INTEGER NOT NULL, cached_input_tokens INTEGER NOT NULL,
          cache_write_input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
          reasoning_output_tokens INTEGER NOT NULL, total_tokens INTEGER NOT NULL,
          details TEXT NOT NULL, first_seen TEXT NOT NULL, excluded INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS event_time ON events(timestamp);
        CREATE INDEX IF NOT EXISTS event_thread ON events(thread_id);
        CREATE INDEX IF NOT EXISTS event_thread_kind ON events(thread_id,granularity);
        CREATE TABLE IF NOT EXISTS observations (
          event_id TEXT NOT NULL REFERENCES events(id), source TEXT NOT NULL,
          line INTEGER NOT NULL, sha256 TEXT NOT NULL, received_at TEXT NOT NULL,
          UNIQUE(event_id,source,line,sha256));
        CREATE TABLE IF NOT EXISTS conflicts (
          event_id TEXT NOT NULL REFERENCES events(id), source TEXT NOT NULL,
          line INTEGER NOT NULL, sha256 TEXT NOT NULL, received_at TEXT NOT NULL,
          evidence TEXT NOT NULL, UNIQUE(event_id,source,line,sha256));
        CREATE TABLE IF NOT EXISTS files (
          path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
          indexed_at TEXT NOT NULL, mode TEXT NOT NULL, issues TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sources (
          id TEXT PRIMARY KEY, label TEXT NOT NULL, path TEXT NOT NULL,
          access_path TEXT NOT NULL, kind TEXT NOT NULL, origin TEXT NOT NULL,
          enabled INTEGER NOT NULL, revision TEXT NOT NULL, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, last_scan TEXT, status TEXT NOT NULL DEFAULT 'pending',
          detail TEXT NOT NULL DEFAULT '', file_count INTEGER NOT NULL DEFAULT 0,
          UNIQUE(path,kind));
        CREATE TABLE IF NOT EXISTS source_files (
          source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          path TEXT NOT NULL, revision TEXT NOT NULL, size INTEGER NOT NULL,
          mtime_ns INTEGER NOT NULL, PRIMARY KEY(source_id,path));
        CREATE TABLE IF NOT EXISTS attribution (
          event_id TEXT PRIMARY KEY REFERENCES events(id), project TEXT NOT NULL,
          principal TEXT NOT NULL, purpose TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, actor TEXT NOT NULL,
          action TEXT NOT NULL, target TEXT NOT NULL, reason TEXT NOT NULL,
          before_json TEXT NOT NULL, after_json TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS buckets (
          id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL,
          start TEXT NOT NULL, end TEXT NOT NULL, dimensions TEXT NOT NULL,
          values_json TEXT NOT NULL, imported_at TEXT NOT NULL, source TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS activity (
          id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
          account_ref TEXT NOT NULL, device TEXT NOT NULL, ip TEXT NOT NULL,
          project TEXT NOT NULL, purpose TEXT NOT NULL, details TEXT NOT NULL,
          source TEXT NOT NULL, received_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS budgets (
          project TEXT PRIMARY KEY, tokens INTEGER NOT NULL, period TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS activity_policies (
          scope TEXT PRIMARY KEY, devices TEXT NOT NULL, networks TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS alerts (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          severity TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', target TEXT NOT NULL);
        ''')
        self.db.executescript(LIMIT_SCHEMA)
        self.db.commit()
        initialized = self.db.execute("SELECT 1 FROM settings WHERE key='sources_initialized'").fetchone()
        if not initialized or override_sources:
            with self.db:
                before = [dict(r) for r in self.db.execute('SELECT * FROM sources')]
                self.db.execute('DELETE FROM sources')
                for root in dict.fromkeys(str(p) for p in roots):
                    path = self.validate_source_path(root)
                    source_id, revision = uuid.uuid4().hex, uuid.uuid4().hex
                    self.db.execute('''INSERT INTO sources
                      (id,label,path,access_path,kind,origin,enabled,revision,created_at,updated_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?)''',
                      (source_id, 'Local Codex / Work', path, '', 'codex_home', 'local', 1, revision, now(), now()))
                    # Carry the existing collector cache into the first registry
                    # migration; adding or editing a source still checks it anew.
                    if not initialized:
                        for name in ('sessions','archived_sessions'):
                            prefix = str(Path(path) / name) + os.sep
                            self.db.execute('''INSERT OR IGNORE INTO source_files
                              SELECT ?,path,?,size,mtime_ns FROM files WHERE substr(path,1,?)=?''',
                              (source_id,revision,len(prefix),prefix))
                self.db.execute("INSERT OR REPLACE INTO settings VALUES ('sources_initialized','1')")
                if initialized and override_sources:
                    self.audit('sources.startup_override', 'sources', 'Explicit --source or --no-scan launch option.', before,
                               [dict(r) for r in self.db.execute('SELECT * FROM sources')])
        if self.db_path != ':memory:':
            os.chmod(self.db_path, 0o600)

    def close(self):
        self.db.close()

    @staticmethod
    def validate_source_path(value, optional=False):
        if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
            raise ValueError('Use a valid absolute folder path, up to 4,096 characters.')
        value = value.strip()
        if not value and optional: return ''
        if not value: raise ValueError('A folder path is required.')
        if PureWindowsPath(value).is_absolute():
            if value.startswith(('\\\\?\\', '\\\\.\\')): raise ValueError('Windows device paths are not supported.')
            return str(PureWindowsPath(value))
        candidate = Path(value).expanduser()
        if not candidate.is_absolute() or value.startswith('//'):
            raise ValueError('Use an absolute folder path. URLs, drive-relative paths and variables are not accepted.')
        return str(candidate.resolve())

    @staticmethod
    def resolve_source_path(source):
        value = source['access_path'] or source['path']
        if os.name != 'nt' and PureWindowsPath(value).is_absolute():
            windows = PureWindowsPath(value)
            if re.fullmatch('[A-Za-z]:', windows.drive):
                mount = Path('/mnt') / windows.drive[0].lower()
                if mount.is_dir(): return mount.joinpath(*windows.parts[1:]), ''
            return None, 'Windows folder is not accessible from this server. Set its mounted or synced server path, or run Observatory on Windows.'
        return Path(value), ''

    def configured_sources(self):
        result = []
        for row in self.db.execute('SELECT * FROM sources ORDER BY created_at,id'):
            item = dict(row); item['enabled'] = bool(item['enabled'])
            path, message = self.resolve_source_path(item)
            item['resolved_path'] = str(path) if path is not None else ''
            if not item['enabled']: item.update(status='disabled', detail='Collection is disabled; indexed evidence is retained.')
            elif message: item.update(status='unavailable', detail=message)
            result.append(item)
        return result

    def save_source(self, data):
        ident = text(data.get('id'), 64)
        before = dict(self.db.execute('SELECT * FROM sources WHERE id=?', (ident,)).fetchone() or {}) if ident else {}
        if ident and not before: raise ValueError('Source not found. Reload source settings.')
        label = text(data.get('label'), 200).strip()
        kind, origin = data.get('kind'), data.get('origin')
        enabled = data.get('enabled', True)
        if not label or kind not in ('codex_home','session_folder') or origin not in ('local','external') or not isinstance(enabled, bool):
            raise ValueError('Supply a label, a supported folder type, a source location and an enabled setting.')
        path = self.validate_source_path(data.get('path'))
        access = self.validate_source_path(data.get('access_path', ''), optional=True)
        reason = text(data.get('reason'), 2000).strip()
        if not reason: raise ValueError('Explain why you are changing the source configuration.')
        duplicate = self.db.execute('SELECT id FROM sources WHERE path=? AND kind=?', (path,kind)).fetchone()
        if duplicate and duplicate[0] != ident: raise ValueError('This folder and source type are already configured. Edit that source instead.')
        if not before and self.db.execute('SELECT COUNT(*) FROM sources').fetchone()[0] >= 100:
            raise ValueError('Up to 100 source folders can be configured.')
        ident = ident or uuid.uuid4().hex
        after = dict(id=ident,label=label,path=path,access_path=access,kind=kind,origin=origin,enabled=int(enabled),
                     revision=uuid.uuid4().hex,created_at=before.get('created_at',now()),updated_at=now(),
                     last_scan=before.get('last_scan'),status='pending',detail='Saved. Waiting for collection.',file_count=0)
        with self.db:
            if before:
                self.db.execute('UPDATE sources SET ' + ','.join(k+'=?' for k in after if k!='id') + ' WHERE id=?',
                                [v for k,v in after.items() if k!='id']+[ident])
            else:
                self.db.execute('INSERT INTO sources ('+','.join(after)+') VALUES ('+','.join('?' for _ in after)+')',tuple(after.values()))
            self.audit('source.updated' if before else 'source.added',ident,reason,before or None,after)
        return next(s for s in self.configured_sources() if s['id']==ident)

    def remove_source(self, data):
        ident = text(data.get('id'),64)
        before = dict(self.db.execute('SELECT * FROM sources WHERE id=?',(ident,)).fetchone() or {})
        if not before: raise ValueError('Source not found.')
        with self.db:
            self.db.execute('DELETE FROM sources WHERE id=?',(ident,))
            self.audit('source.removed',ident,'Removed from source settings. Existing evidence retained.',before,None)

    def source_is_current(self, source):
        return bool(self.db.execute('SELECT 1 FROM sources WHERE id=? AND revision=? AND enabled=1',
                                   (source['id'],source['revision'])).fetchone())

    def source_status(self, source, status, detail, count=0):
        self.db.execute('UPDATE sources SET status=?,detail=?,file_count=?,last_scan=? WHERE id=? AND revision=?',
                        (status,detail,count,now(),source['id'],source['revision']))

    def audit(self, action, target, reason, before, after):
        previous = self.db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
        row = {'timestamp': now(), 'actor': getpass.getuser(), 'action': action,
               'target': target, 'reason': reason, 'before_json': dump(before),
               'after_json': dump(after), 'prev_hash': previous[0] if previous else ''}
        row['hash'] = digest(dump(row))
        self.db.execute('INSERT INTO audit (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))

    def integrity(self):
        previous = ''
        rows = self.db.execute('SELECT * FROM audit ORDER BY seq').fetchall()
        for item in rows:
            row = dict(item)
            seq, expected = row.pop('seq'), row.pop('hash')
            if row['prev_hash'] != previous or digest(dump(row)) != expected:
                return {'valid': False, 'entries': len(rows), 'first_invalid': seq}
            previous = expected
        return {'valid': True, 'entries': len(rows), 'head': previous,
                'assurance': 'Local hash chain. Not externally signed or tamper-proof.'}

    def _event(self, payload, ctx, timestamp, source, line, raw_hash, kind='codex', granularity='response', imported=False):
        counts = usage(payload.get('usage'))
        response_id = text(payload.get('response_id'))
        thread_id = text(payload.get('thread_id')) or ctx.get('thread_id', '')
        # A native response has one accounting identity across copied/forked log files.
        identity = ('codex-response:' + ctx.get('provider', 'openai') + ':' + response_id
                    if response_id and kind == 'codex' else kind + ':' + source + ':' + str(line) + ':' + raw_hash)
        if granularity == 'snapshot delta' and thread_id:
            identity = 'codex-snapshot:' + thread_id + ':' + raw_hash
        details = {k: ctx.get(k, '') for k in ('cli_version', 'provider', 'branch', 'commit', 'effort', 'speed', 'session_id')}
        details.update(root_turn_id=text(payload.get('root_turn_id')),
                       execution_session_id=text(payload.get('session_id')),
                       source_thread_id=ctx.get('thread_id', ''), source_timestamp=timestamp)
        details.update({'identity_basis': 'source-declared' if imported else 'local OS user; not proof of model-account identity',
                        'purpose_basis': 'Not collected; declare a purpose to explain this response.',
                        'usage_reported_fields': [k for k in TOKEN_FIELDS if k in payload.get('usage', {})],
                        'usage': counts, 'timestamp_basis': 'source record', 'original_kind': granularity})
        row = {'id': digest(identity), 'timestamp': stamp(timestamp), 'source_kind': kind,
               'granularity': granularity, 'project': ctx.get('cwd') or 'Unallocated',
               'cwd': ctx.get('cwd', ''), 'thread_id': thread_id,
               'turn_id': text(payload.get('turn_id')) or ctx.get('turn_id', ''),
               'response_id': response_id, 'parent_id': ctx.get('parent_id', ''),
               'actor': ctx.get('actor', ''), 'device': ctx.get('device', ''),
               'application': ctx.get('application', '') or 'Codex', 'model': ctx.get('model', '') or 'Unknown',
               'account_ref': ctx.get('account_ref', ''), **counts, 'details': dump(details), 'first_seen': now()}
        return row, (row['id'], source, line, raw_hash, now())

    def parse_codex(self, lines, source, imported=False, limit_records=None, limits_only=False):
        ctx = {'actor': '' if imported else getpass.getuser(), 'device': '' if imported else socket.gethostname()}
        explicit, legacy, issues = [], [], []
        previous = {k: 0 for k in TOKEN_FIELDS}
        last_snapshot = None
        native_seen = False
        for line_no, raw in enumerate(lines, 1):
            if len(raw) > MAX_LINE:
                issues.append(f'Line {line_no}: record exceeds 16 MB; skipped.'); continue
            if not raw.endswith(b'\n'):
                issues.append(f'Line {line_no}: incomplete final line; waiting for completion.'); break
            prefix = raw[:240]
            if not any(tag in prefix for tag in (b'"session_meta"', b'"turn_context"', b'"token_usage_record"', b'"event_msg"')):
                continue
            if b'"event_msg"' in prefix and b'"token_count"' not in raw[:500]:
                continue
            if limits_only and b'"token_usage_record"' in prefix: continue
            try:
                obj = json.loads(raw)
                p = obj.get('payload') or {}
                kind = obj.get('type')
                if kind == 'event_msg' and p.get('type') == 'token_count' and p.get('rate_limits') is not None and limit_records is not None:
                    try:
                        limit_records.append(normalize_limits(p['rate_limits'], obj.get('timestamp'), ctx,
                            source, line_no, digest(raw), stamp, digest, now))
                    except (ValueError, TypeError, OverflowError, OSError):
                        issues.append(f'Line {line_no}: invalid quota reading; limit snapshot skipped.')
                if kind == 'session_meta':
                    git = p.get('git') if isinstance(p.get('git'), dict) else {}
                    ctx.update({'thread_id': text(p.get('id')), 'session_id': text(p.get('session_id')),
                                'cwd': text(p.get('cwd')), 'application': text(p.get('originator')) or 'Codex',
                                'cli_version': text(p.get('cli_version')), 'provider': text(p.get('model_provider')) or 'openai',
                                'parent_id': text(p.get('parent_thread_id') or p.get('forked_from_id')),
                                'branch': text(git.get('branch')), 'commit': text(git.get('commit_hash'))})
                elif kind == 'turn_context':
                    for dest, key in [('cwd', 'cwd'), ('model', 'model'), ('turn_id', 'turn_id'), ('effort', 'effort'), ('speed', 'service_tier')]:
                        if isinstance(p.get(key), str): ctx[dest] = text(p[key])
                elif kind == 'token_usage_record':
                    native_seen = True
                    explicit.append(self._event(p, ctx, obj.get('timestamp'), source, line_no, digest(raw), imported=imported))
                elif not limits_only and kind == 'event_msg' and p.get('type') == 'token_count' and p.get('info'):
                    total = usage(p['info'].get('total_token_usage'))
                    if any(total[k] < previous[k] for k in TOKEN_FIELDS):
                        issues.append(f'Line {line_no}: cumulative counters decreased; snapshot excluded.'); continue
                    delta = {k: total[k] - previous[k] for k in TOKEN_FIELDS}
                    if delta['total_tokens']:
                        legacy.append(self._event({'usage': delta}, ctx, obj.get('timestamp'), source, line_no,
                                                  digest(raw), granularity='snapshot delta', imported=imported))
                    previous, last_snapshot = total, total
            except (ValueError, TypeError, AttributeError, OverflowError) as error:
                # No record content or exception text (which might include content) is persisted.
                issues.append(f'Line {line_no}: invalid metadata or metering record ({type(error).__name__}).')
        if native_seen:
            unique = {e[0]['id']: e[0] for e in explicit}
            total = sum(e['total_tokens'] for e in unique.values())
            if last_snapshot and total < last_snapshot['total_tokens']:
                issues.append('Response totals are below a cumulative snapshot; historical usage may be missing or inherited. No extra tokens were invented.')
            return explicit, 'response', issues[:100]
        if ctx.get('parent_id') and legacy:
            issues.append('Legacy child/fork counters may include inherited history; excluded from totals pending response-level evidence.')
            for event, _ in legacy: event['excluded'] = 1
        return legacy, 'snapshot delta' if legacy else 'no metering', issues[:100]

    def persist_events(self, records):
        added = 0
        for event, observation in records:
            old = self.db.execute('SELECT * FROM events WHERE id=?', (event['id'],)).fetchone()
            if old:
                if any(old[k] != event[k] for k in TOKEN_FIELDS):
                    self.db.execute('INSERT OR IGNORE INTO conflicts VALUES (?,?,?,?,?,?)', (*observation, dump(event)))
                    self._alert('conflict:' + event['id'], 'high', 'Conflicting metering evidence',
                                'The same response has different token counts in another source. Original counts retained.', event['id'])
                    continue
            else:
                self.db.execute('INSERT INTO events (' + ','.join(event) + ') VALUES (' + ','.join('?' for _ in event) + ')', tuple(event.values()))
                added += 1
            self.db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?)', observation)
            if event['granularity'] == 'response' and event['thread_id']:
                self.db.execute("UPDATE events SET excluded=1 WHERE thread_id=? AND granularity='snapshot delta'", (event['thread_id'],))
            elif event['granularity'] == 'snapshot delta' and event['thread_id']:
                native = self.db.execute("SELECT 1 FROM events WHERE thread_id=? AND granularity='response' LIMIT 1", (event['thread_id'],)).fetchone()
                if native: self.db.execute('UPDATE events SET excluded=1 WHERE id=?', (event['id'],))
        return added

    def scan(self):
        with self.lock:
            if self.scanning: return
            self.scanning = True
            self.progress.update(running=True, done=0, total=0, error=None)
            sources = [dict(r) for r in self.db.execute('SELECT * FROM sources WHERE enabled=1 ORDER BY created_at,id')]
        try:
            plans = []
            for source in sources:
                try:
                    root, message = self.resolve_source_path(source)
                    if root is None or not root.is_dir():
                        with self.lock, self.db:
                            self.source_status(source, 'unavailable', message or 'Folder does not exist or is not accessible to this server.')
                        continue
                    folders = [root / n for n in ('sessions','archived_sessions')] if source['kind']=='codex_home' else [root]
                    if not any(f.is_dir() for f in folders):
                        with self.lock, self.db:
                            self.source_status(source, 'unrecognized', 'No sessions or archived_sessions folders found. Choose a session folder directly if this is a copy of logs.')
                        continue
                    paths = sorted({p for folder in folders if folder.is_dir() for p in folder.rglob('*.jsonl') if not p.is_symlink()}, key=str, reverse=True)
                    plans.append((source,paths))
                    self.progress['total'] += len(paths)
                    with self.lock, self.db:
                        self.source_status(source, 'indexing', 'Checking session records.', len(paths))
                except OSError:
                    with self.lock, self.db:
                        self.source_status(source, 'unavailable', 'The folder could not be read. Check its mount and read permissions.')
            for source, paths in plans:
                notices = 0
                metering = 0
                for path in paths:
                    try:
                        with self.lock:
                            if not self.source_is_current(source): break
                            tracked = self.db.execute('SELECT * FROM source_files WHERE source_id=? AND path=?', (source['id'],str(path))).fetchone()
                            old = self.db.execute('SELECT * FROM files WHERE path=?',(str(path),)).fetchone()
                            limit_cache = self.db.execute('SELECT * FROM limit_files WHERE path=?',(str(path),)).fetchone()
                        st = path.stat()
                        unchanged = tracked and old and tracked['revision']==source['revision'] and tracked['size']==st.st_size and tracked['mtime_ns']==st.st_mtime_ns
                        if unchanged and limit_cache and limit_cache['size']==st.st_size and limit_cache['mtime_ns']==st.st_mtime_ns:
                            notices += bool(json.loads(old['issues']))
                            metering += old['mode'] in ('response','snapshot delta')
                            self.progress['done'] += 1
                            continue
                        limit_records = []
                        with path.open('rb') as f:
                            records, mode, issues = self.parse_codex(bounded_lines(f), str(path), imported=source['origin']=='external',
                                limit_records=limit_records, limits_only=bool(unchanged))
                        if unchanged:
                            mode, issues = old['mode'], list(dict.fromkeys(json.loads(old['issues']) + issues))[:100]
                        if mode == 'no metering' and limit_records: mode = 'limits'

                        if mode == 'no metering': issues.append('No supported metering records found. Conversation history and app caches are not converted into token usage.')
                        with self.lock, self.db:
                            if not self.source_is_current(source): break
                            self.persist_limits(limit_records)
                            self.db.execute('INSERT OR REPLACE INTO limit_files VALUES (?,?,?)', (str(path),st.st_size,st.st_mtime_ns))
                            if mode == 'response' and not unchanged:
                                self.db.execute("UPDATE events SET excluded=1 WHERE granularity='snapshot delta' AND id IN (SELECT event_id FROM observations WHERE source=?)", (str(path),))
                            self.persist_events(records)
                            self.db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?)',
                                            (str(path),st.st_size,st.st_mtime_ns,now(),mode,dump(issues)))
                            self.db.execute('INSERT OR REPLACE INTO source_files VALUES (?,?,?,?,?)',
                                            (source['id'],str(path),source['revision'],st.st_size,st.st_mtime_ns))
                        notices += bool(issues)
                        metering += mode in ('response','snapshot delta')
                    except (OSError, sqlite3.Error):
                        notices += 1
                        with self.lock, self.db:
                            self._alert('scan:' + digest(str(path)), 'warning', 'A source could not be indexed',
                                        'A local file was unavailable or could not be stored. Accounting coverage is incomplete.', str(path))
                    self.progress['done'] += 1
                with self.lock, self.db:
                    if self.source_is_current(source):
                        status = 'notices' if notices else 'ready' if metering else 'empty'
                        self.source_status(source, status,
                            f'{len(paths):,} JSONL files checked; {metering:,} files with recognized metering; {notices:,} files with notices. ' +
                            ('Review source quality below.' if notices else 'No metering evidence found.' if not metering else 'Up to date for reachable files.'),len(paths))
            with self.lock, self.db:
                self.evaluate_budgets()
                self.progress['last_scan'] = now()
        except Exception:
            self.progress['error'] = 'Indexing stopped unexpectedly. Review server health; existing records remain available.'
        finally:
            with self.lock:
                self.scanning = False; self.progress['running'] = False

    def _alert(self, ident, severity, title, detail, target):
        self.db.execute('''INSERT INTO alerts(id,created_at,updated_at,severity,title,detail,target)
          VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,
          detail=excluded.detail,title=excluded.title,
          status=CASE WHEN alerts.severity='warning' AND excluded.severity='high' THEN 'open' ELSE alerts.status END,
          severity=excluded.severity''', (ident, now(), now(), severity, title, detail, target))

    def evaluate_budgets(self):
        for b in self.db.execute('SELECT * FROM budgets').fetchall():
            date = now()[:10] if b['period'] == 'day' else now()[:7] + '-01'
            total = self.db.execute('''SELECT COALESCE(SUM(e.total_tokens),0) FROM events e
              LEFT JOIN attribution a ON a.event_id=e.id WHERE e.excluded=0
              AND COALESCE(NULLIF(a.project,''),e.project)=? AND e.timestamp>=? AND e.timestamp<=?''', (b['project'], date, now())).fetchone()[0]
            if total >= b['tokens'] * .8:
                self._alert('budget:' + b['project'] + ':' + b['period'] + ':' + date,
                            'high' if total >= b['tokens'] else 'warning', 'Project token budget reached' if total >= b['tokens'] else 'Project approaching token budget',
                            f'{total:,} observed tokens against a {b["tokens"]:,} token budget ({b["period"]}, UTC). Alerts do not stop provider usage.', b['project'])

    def filters(self, params):
        clauses, args = ['e.excluded=0'], []
        for name, op in [('from', '>='), ('to', '<')]:
            if params.get(name):
                value = params[name]
                if len(value) == 10: value += 'T00:00:00Z'
                clauses.append('e.timestamp' + op + '?'); args.append(stamp(value))
        if params.get('project'):
            clauses.append("COALESCE(NULLIF(a.project,''),e.project)=?"); args.append(params['project'])
        if params.get('thread'):
            clauses.append('e.thread_id=?'); args.append(params['thread'])
        if params.get('granularity') in ('response', 'snapshot delta'):
            clauses.append('e.granularity=?'); args.append(params['granularity'])
        if params.get('facets'):
            facets = json.loads(params['facets'])
            if not isinstance(facets, dict) or len(facets)>15: raise ValueError('Invalid drill-down filters.')
            for dimension, value in facets.items():
                if dimension not in DIMENSIONS or not isinstance(value, str) or len(value)>4096:
                    raise ValueError('Invalid drill-down filter.')
                clauses.append(DIMENSIONS[dimension] + '=?'); args.append(value)
        for key, op in (('tokens_min','>='),('tokens_max','<')):
            if params.get(key) is not None:
                value=int(params[key])
                if not 0<=value<=10**16: raise ValueError('Invalid token range.')
                clauses.append('e.total_tokens'+op+'?');args.append(value)
        if params.get('q'):
            clauses.append("(e.thread_id LIKE ? OR e.response_id LIKE ? OR e.model LIKE ? OR e.cwd LIKE ? OR e.actor LIKE ? OR e.application LIKE ? OR a.project LIKE ? OR a.principal LIKE ? OR a.purpose LIKE ?)")
            args.extend(['%' + params['q'][:300] + '%'] * 9)
        return ' AND '.join(clauses), args

    JOIN = ' FROM events e LEFT JOIN attribution a ON a.event_id=e.id '
    SELECT = "e.*,COALESCE(NULLIF(a.project,''),e.project) AS effective_project,COALESCE(NULLIF(a.principal,''),e.actor) AS effective_actor,COALESCE(a.purpose,'') AS purpose,a.updated_at AS attributed_at"

    @staticmethod
    def order(params, fields, default, direction='asc'):
        key = params.get('sort_by', default)
        if key not in fields: raise ValueError('Unknown sort column.')
        direction = params.get('direction', direction).lower()
        if direction not in ('asc', 'desc'): raise ValueError('Unknown sort direction.')
        expression = fields[key]
        return f"({expression} IS NULL OR {expression}='') ASC,{expression} COLLATE NOCASE {direction}"

    def event_order(self, params):
        if not params.get('sort_by'):
            return {'tokens': 'e.total_tokens DESC,e.timestamp DESC,e.id', 'oldest': 'e.timestamp ASC,e.id',
                    'newest': 'e.timestamp DESC,e.id'}.get(params.get('sort'), 'e.timestamp DESC,e.id')
        fields = {k: 'e.' + k for k in ('timestamp','model',*TOKEN_FIELDS)}
        fields.update(project="COALESCE(NULLIF(a.project,''),e.project)", actor="COALESCE(NULLIF(a.principal,''),e.actor)")
        return self.order(params, fields, 'timestamp', 'desc') + ',e.id'

    def query(self, params):
        where, args = self.filters(params)
        limit = min(max(int(params.get('limit', 50)), 1), 500)
        offset = max(int(params.get('offset', 0)), 0)
        sort = self.event_order(params)
        rows = self.db.execute('SELECT ' + self.SELECT + self.JOIN + ' WHERE ' + where + ' ORDER BY ' + sort + ' LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
        summary = dict(self.db.execute('''SELECT COUNT(*) AS records,COUNT(DISTINCT NULLIF(e.thread_id,'')) AS tasks,
          COUNT(DISTINCT COALESCE(NULLIF(a.project,''),e.project)) AS projects,
          COALESCE(SUM(e.total_tokens),0) AS total_tokens, COALESCE(SUM(e.input_tokens),0) AS input_tokens,
          COALESCE(SUM(e.cached_input_tokens),0) AS cached_input_tokens,COALESCE(SUM(e.output_tokens),0) AS output_tokens,
          COALESCE(SUM(CASE WHEN e.granularity='response' THEN 1 ELSE 0 END),0) AS response_records,
          COALESCE(SUM(CASE WHEN e.granularity='snapshot delta' THEN 1 ELSE 0 END),0) AS snapshot_records,
          COALESCE(SUM(CASE WHEN a.purpose IS NULL OR a.purpose='' THEN 1 ELSE 0 END),0) AS missing_purpose
          ''' + self.JOIN + ' WHERE ' + where, args).fetchone())
        days = [dict(r) for r in self.db.execute('''SELECT substr(e.timestamp,1,10) AS day,
          SUM(e.input_tokens-e.cached_input_tokens) AS uncached,SUM(e.cached_input_tokens) AS cached,
          SUM(e.output_tokens) AS output,SUM(e.total_tokens) AS total''' + self.JOIN + ' WHERE ' + where + ' GROUP BY day ORDER BY day', args).fetchall()]
        projects = [dict(r) for r in self.db.execute('''SELECT COALESCE(NULLIF(a.project,''),e.project) AS project,
          COUNT(*) AS records,COUNT(DISTINCT NULLIF(e.thread_id,'')) AS tasks,SUM(e.total_tokens) AS total_tokens,
          SUM(e.cached_input_tokens) AS cached_input_tokens,MAX(e.timestamp) AS last_seen''' + self.JOIN + ' WHERE ' + where + ' GROUP BY 1 ORDER BY total_tokens DESC', args).fetchall()]
        return {'events': [self.serialize(r) for r in rows], 'summary': summary, 'days': days, 'projects': projects, 'offset': offset, 'limit': limit}

    def serialize(self, row):
        row = dict(row); row['details'] = json.loads(row['details']); return row

    def breakdown(self, params):
        dimensions = DIMENSIONS
        by = params.get('by', 'model')
        if by not in dimensions: raise ValueError('Unknown accounting dimension.')
        where, args = self.filters(params)
        expression = dimensions[by]
        sums = ','.join('SUM(e.' + k + ') AS ' + k for k in TOKEN_FIELDS)
        sql = 'SELECT ' + expression + ' AS dimension,COUNT(*) AS records,' + sums + self.JOIN + ' WHERE ' + where + ' GROUP BY 1 ORDER BY ' + self.order(params, {k:k for k in ('dimension','records',*TOKEN_FIELDS)}, 'total_tokens', 'desc') + ',dimension'
        total = self.db.execute('SELECT COUNT(DISTINCT ' + expression + ')' + self.JOIN + ' WHERE ' + where, args).fetchone()[0]
        rows = [dict(r) for r in self.db.execute(sql + ' LIMIT 500', args)]
        return {'by': by, 'groups': rows, 'total': total,
                'notice': 'Groups partition included local/imported Codex metering only. People are declared owners or collector users; devices identify collectors, not verified remote execution hosts. Missing purposes remain unassigned.'}

    def detail(self, ident):
        row = self.db.execute('SELECT ' + self.SELECT + self.JOIN + ' WHERE e.id=?', (ident,)).fetchone()
        if not row: raise ValueError('Record not found.')
        event = self.serialize(row)
        observations = [dict(r) for r in self.db.execute('SELECT * FROM observations WHERE event_id=? ORDER BY received_at', (ident,))]
        history = [dict(r) for r in self.db.execute('SELECT * FROM audit WHERE target=? ORDER BY seq DESC', (ident,))]
        # Native evidence only; never return prompts or arbitrary filesystem contents.
        return {'event': event, 'observations': observations, 'history': history,
                'limit_context': self.limit_context(observations, event),
                'conflicts': [dict(r) for r in self.db.execute('SELECT * FROM conflicts WHERE event_id=?', (ident,))],
                'task_records': self.db.execute('SELECT COUNT(*) FROM events WHERE thread_id=? AND excluded=0', (event['thread_id'],)).fetchone()[0] if event['thread_id'] else 0,
                'attribution': dict(self.db.execute('SELECT * FROM attribution WHERE event_id=?', (ident,)).fetchone() or {})}

    def attribute(self, data):
        ident = text(data.get('id')); detail = self.detail(ident); before = detail['attribution']
        reason = text(data.get('reason'), 2000).strip()
        if not reason: raise ValueError('Explain why this attribution is being changed.')
        after = {key: text(data.get(key), 1000).strip() for key in ('project', 'principal', 'purpose')}
        if not any(after.values()) and not before: raise ValueError('Add a project, principal or purpose.')
        scope = data.get('apply_scope', 'record')
        if scope not in ('record', 'task'): raise ValueError('Choose a record or task attribution scope.')
        targets = [ident]
        if scope == 'task':
            thread = detail['event']['thread_id']
            if not thread: raise ValueError('This record has no task identity.')
            targets = [r[0] for r in self.db.execute('SELECT id FROM events WHERE thread_id=? AND excluded=0', (thread,))]
        with self.db:
            for target in targets:
                before = dict(self.db.execute('SELECT * FROM attribution WHERE event_id=?', (target,)).fetchone() or {})
                self.db.execute('INSERT OR REPLACE INTO attribution VALUES (?,?,?,?,?)', (target, after['project'], after['principal'], after['purpose'], now()))
                self.audit('attribution.changed', target, reason, before, {**after, 'apply_scope': scope})
            self.evaluate_budgets()
        return {**self.detail(ident), 'changed_records': len(targets)}

    def budget(self, data):
        project = text(data.get('project')).strip()
        tokens = data.get('tokens')
        period = data.get('period')
        if not project or isinstance(tokens, bool) or not isinstance(tokens, int) or not 1 <= tokens <= 10**15 or period not in ('day', 'month'):
            raise ValueError('Choose a project, a positive token budget, and a day or month period.')
        before = dict(self.db.execute('SELECT * FROM budgets WHERE project=?', (project,)).fetchone() or {})
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO budgets VALUES (?,?,?)', (project, tokens, period))
            self.audit('budget.changed', project, 'Token budget configured in the local app.', before, data)
            self.evaluate_budgets()

    def activity_policy(self, data):
        scope = text(data.get('scope'), 200).strip()
        devices = data.get('devices', [])
        networks = data.get('networks', [])
        reason = text(data.get('reason'), 2000).strip()
        if not scope or not reason: raise ValueError('An account label and policy-change reason are required.')
        if not isinstance(devices, list) or not isinstance(networks, list) or len(devices) > 100 or len(networks) > 100:
            raise ValueError('Supply up to 100 approved devices and networks.')
        if any(not isinstance(v, str) or not v.strip() or len(v) > 1000 for v in devices + networks):
            raise ValueError('Devices and networks must be non-empty text values.')
        try: networks = sorted(set(str(ipaddress.ip_network(v.strip(), strict=False)) for v in networks))
        except ValueError: raise ValueError('Use valid IP addresses or CIDR networks.')
        devices = sorted(set(v.strip() for v in devices))
        if not devices and not networks: raise ValueError('Declare at least one approved device or network.')
        before = dict(self.db.execute('SELECT * FROM activity_policies WHERE scope=?', (scope,)).fetchone() or {})
        after = dict(scope=scope, devices=devices, networks=networks)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO activity_policies VALUES (?,?,?,?)', (scope, dump(devices), dump(networks), now()))
            self.audit('activity.policy.changed', scope, reason, before, after)
            self.evaluate_activity(scope)
        return after

    def evaluate_activity(self, scope):
        policy = self.db.execute('SELECT * FROM activity_policies WHERE scope=?', (scope,)).fetchone()
        if not policy: return
        devices = json.loads(policy['devices'])
        networks = [ipaddress.ip_network(v) for v in json.loads(policy['networks'])]
        for row in self.db.execute('SELECT * FROM activity WHERE account_ref=?', (scope,)):
            reasons = []
            missing = []
            if devices:
                if not row['device']: missing.append('device')
                elif row['device'] not in devices: reasons.append('device is outside the declared approved list')
            if networks:
                try: address = ipaddress.ip_address(row['ip'])
                except ValueError: missing.append('valid IP address')
                else:
                    if not any(address in network for network in networks): reasons.append('IP address is outside the declared approved networks')
            if reasons:
                self._alert('activity-policy:' + row['id'], 'high', 'Activity outside declared access policy',
                            f'Imported {row["action"]} at {row["timestamp"]} in {scope}: ' + '; '.join(reasons) +
                            '. This is a policy mismatch in source-declared evidence, not proof of credential theft.', row['id'])
            if missing:
                self._alert('activity-missing:' + row['id'], 'warning', 'Activity cannot be fully checked',
                            f'Imported {row["action"]} at {row["timestamp"]} in {scope} is missing ' + ', '.join(missing) +
                            '. These access-policy checks are unknown.', row['id'])

    def import_data(self, name, content, scope, *, source_label=None):
        if not isinstance(content, str) or len(content.encode()) > 30 * 1024 * 1024:
            raise ValueError('Import files must be text, up to 30 MB.')
        scope = text(scope, 200).strip()
        name = Path(text(name, 200)).name
        label = name
        if source_label is not None:
            if not isinstance(source_label, str) or len(source_label) > 4096 or any(ord(c) < 32 for c in source_label):
                raise ValueError('Invalid relative source label.')
            label = source_label.replace('\\', '/')
            if label.startswith('/') or '..' in label.split('/') or ':' in label or not label.endswith('/' + name):
                raise ValueError('Use a relative folder/file label for imported evidence.')
        source = 'import:' + digest(content) + '/' + label
        if name.lower().endswith('.jsonl'):
            limit_records = []
            records, mode, issues = self.parse_codex(io.BytesIO(content.encode()), source, imported=True, limit_records=limit_records)
            if not records and not limit_records: raise ValueError('No valid Codex usage or limit records found in this JSONL file.')
            if not records: mode = 'limits'
            with self.db:
                count = self.persist_events(records)
                limit_count = self.persist_limits(limit_records)
                self.db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?)', (source, len(content.encode()), 0, now(), mode, dump(issues)))
                self.audit('source.imported', source, 'Codex metadata import.', None, {'new_records': count, 'new_limit_snapshots': limit_count, 'issues': issues})
                self.evaluate_budgets()
            return {'kind': 'Codex', 'new_records': count, 'new_limit_snapshots': limit_count, 'issues': issues}
        obj = json.loads(content, parse_float=Decimal)
        if not isinstance(obj, dict): raise ValueError('Expected a JSON object.')
        if not scope: raise ValueError('An account/workspace label is required for provider and activity imports.')
        if obj.get('schema') == 'observatory.activity.v1':
            values = obj.get('events')
            if not isinstance(values, list) or len(values) > 10000: raise ValueError('Expected up to 10,000 activity events.')
            count = 0
            with self.db:
                for value in values:
                    if not isinstance(value, dict) or not text(value.get('id')) or not text(value.get('action')):
                        raise ValueError('Every activity needs a stable id and action.')
                    row = {k: text(value.get(k), 1000) for k in ('actor', 'action', 'device', 'project', 'purpose')}
                    row.update(id=digest('activity:' + scope + ':' + text(value['id'])), timestamp=stamp(value.get('timestamp')),
                               account_ref=scope, ip=text(value.get('ip_address'), 100), source=source, received_at=now(),
                               details=dump({k: text(value.get(k)) for k in ('session_id', 'credential_id', 'application', 'evidence_ref')}))
                    old = self.db.execute('SELECT * FROM activity WHERE id=?', (row['id'],)).fetchone()
                    if old:
                        if any(old[k] != row[k] for k in ('timestamp','actor','action','account_ref','device','ip','project','purpose','details')):
                            raise ValueError('An activity id already exists with different evidence.')
                        continue
                    self.db.execute('INSERT INTO activity (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values())); count += 1
                self.audit('activity.imported', source, 'Source-declared activity; no provider authentication verified.', None, {'records': count, 'scope': scope})
                self.evaluate_activity(scope)
            return {'kind': 'Activity', 'new_records': count}
        if not isinstance(obj.get('data'), list) or len(obj['data']) > 10000:
            raise ValueError('Expected an OpenAI Usage/Costs API page or observatory.activity.v1 export.')
        count = 0
        with self.db:
            for bucket in obj['data']:
                if not isinstance(bucket, dict) or not isinstance(bucket.get('results'), list):
                    raise ValueError('Each provider bucket must contain a results list.')
                start, end = stamp(bucket['start_time']), stamp(bucket['end_time'])
                if end <= start: raise ValueError('Bucket end must be after its start.')
                for result in bucket['results']:
                    if not isinstance(result, dict): raise ValueError('Provider results must be objects.')
                    native = result.get('object', '')
                    if native == 'organization.usage.completions.result':
                        kind = 'usage'
                        counts = usage({**result, 'cached_input_tokens': result.get('input_cached_tokens', 0), 'cache_write_input_tokens': result.get('input_cache_write_tokens', 0)})
                        values = {**counts, 'num_model_requests': result.get('num_model_requests', 0)}
                        requests = values['num_model_requests']
                        if isinstance(requests, bool) or not isinstance(requests, int) or not 0 <= requests <= 10**15:
                            raise ValueError('Model request counts must be non-negative integers below 10^15.')
                    elif native == 'organization.costs.result':
                        kind = 'cost'
                        amount = result.get('amount', {})
                        try: number = Decimal(str(amount['value']))
                        except (InvalidOperation, KeyError): raise ValueError('Invalid cost amount.')
                        if not number.is_finite(): raise ValueError('Invalid cost amount.')
                        currency = text(amount.get('currency'), 12)
                        if not currency: raise ValueError('A cost currency is required.')
                        values = {'amount': str(number), 'currency': currency}
                    else:
                        raise ValueError('This import supports completion-usage and cost buckets only. Other units cannot be silently converted to tokens.')
                    dims = {k: result.get(k) for k in ('project_id', 'api_key_id', 'user_id', 'model', 'batch', 'service_tier', 'line_item') if k in result}
                    if any(not isinstance(v, (str, bool, type(None))) for v in dims.values()): raise ValueError('Invalid provider dimensions.')
                    # A grouping signature identifies an alternative view, not extra consumption.
                    ident = digest(dump([scope, kind, start, end, dims]))
                    old = self.db.execute('SELECT * FROM buckets WHERE id=?', (ident,)).fetchone()
                    if old and old['values_json'] == dump(values): continue
                    self.db.execute('INSERT OR REPLACE INTO buckets VALUES (?,?,?,?,?,?,?,?,?)',
                                    (ident, scope, kind, start, end, dump(dims), dump(values), now(), source))
                    self.audit('provider.bucket.revised' if old else 'provider.bucket.imported', ident,
                               'Provider-export import; scope label is declared by the local operator.', dict(old) if old else None,
                               {'scope': scope, 'start': start, 'end': end, 'dimensions': dims, 'values': values})
                    count += 1
            if obj.get('has_more'):
                self._alert('pagination:' + scope, 'warning', 'Provider export has more pages', 'The imported page reports has_more=true. Import the remaining pages before treating the dataset as complete.', scope)
        return {'kind': 'Provider buckets', 'new_records': count, 'has_more': bool(obj.get('has_more'))}

    def state(self):
        files = [dict(r) for r in self.db.execute('SELECT * FROM files ORDER BY indexed_at DESC')]
        issues = [{'source': f['path'], 'issues': json.loads(f['issues'])} for f in files if json.loads(f['issues'])]
        return {'version': VERSION, 'device': socket.gethostname(), 'operator': getpass.getuser(),
                'roots': [s['path'] for s in self.configured_sources() if s['enabled']],
                'sources': self.configured_sources(), 'server_os': os.name, 'progress': dict(self.progress),
                'files': len(files), 'issues': issues[:100], 'issue_files': len(issues),
                'events': self.db.execute('SELECT COUNT(*) FROM events WHERE excluded=0').fetchone()[0],
                'limit_snapshots': self.db.execute('SELECT COUNT(*) FROM limit_snapshots').fetchone()[0],
                'excluded': self.db.execute('SELECT COUNT(*) FROM events WHERE excluded=1').fetchone()[0],
                'budgets': [dict(r) for r in self.db.execute('SELECT * FROM budgets')],
                'activity_policies': [dict(r) for r in self.db.execute('SELECT * FROM activity_policies')],
                'alerts': [dict(r) for r in self.db.execute('SELECT * FROM alerts ORDER BY created_at DESC')],
                'integrity': self.integrity()}

    def provider(self, params=None):
        params = params or {}
        ordering = self.order(params, {k:k for k in ('start','scope','kind','dimensions','imported_at')}, 'start', 'desc') if params.get('sort_by') != 'values' else 'id'
        # Exact decimals must not be converted to binary floats for sorting costs.
        rows = [dict(r) for r in self.db.execute('SELECT * FROM buckets ORDER BY ' + ordering + ',id' + ('' if params.get('sort_by') == 'values' else ' LIMIT 1000'))]

        for row in rows:
            row['dimensions'] = json.loads(row['dimensions']); row['values'] = json.loads(row.pop('values_json'))
        if params.get('sort_by') == 'values':
            direction = params.get('direction', 'asc')
            if direction not in ('asc','desc'): raise ValueError('Unknown sort direction.')
            rows.sort(key=lambda r: (r['kind'], r['values'].get('currency', ''),
                Decimal(r['values'].get('amount', r['values'].get('total_tokens', 0)))), reverse=direction=='desc')
        return {'buckets': rows[:1000], 'total': self.db.execute('SELECT COUNT(*) FROM buckets').fetchone()[0],
                'note': 'Alternative groupings and overlapping time windows are separate views, never added together. Not reconciled to local usage without a verified account/key mapping.'}

    def export(self, params):
        where, args = self.filters(params)
        rows = self.db.execute('SELECT ' + self.SELECT + self.JOIN + ' WHERE ' + where + ' ORDER BY ' + self.event_order(params), args)
        stream = io.StringIO(); writer = csv.writer(stream)
        fields = ['id','timestamp','effective_project','effective_actor','purpose','device','application','model','account_ref','cwd','thread_id','turn_id','response_id','parent_id',*TOKEN_FIELDS,'granularity','source_kind','first_seen','attributed_at']
        writer.writerow(fields)
        for row in rows:
            # Neutralize spreadsheet formulas in free-text values.
            writer.writerow([("'" + row[k]) if isinstance(row[k],str) and row[k].lstrip().startswith(('=','+','-','@')) else row[k] for k in fields])
        return stream.getvalue()

    def evidence_export(self):
        tables = ('events', 'observations', 'conflicts', 'files', 'attribution', 'audit', 'buckets', 'activity', 'budgets', 'activity_policies', 'sources', 'source_files', 'settings', 'alerts', 'limit_snapshots', 'limit_files')
        return {'schema': 'observatory.evidence.v1', 'exported_at': now(), 'version': VERSION,
                'integrity': self.integrity(), 'coverage': self.state(),
                'notice': 'Metadata export, including excluded evidence. Tables represent different evidence levels; do not sum them together. Source bodies and credentials are not included.',
                'tables': {name: [dict(r) for r in self.db.execute('SELECT * FROM ' + name)] for name in tables}}
