# Optional local collector

Use the collector when you want automatic rescanning of local log folders. For manual imports, offline analysis, and explicit saving, start with the [browser edition](BROWSER.md); it needs no Python or server.

The collector uses the same accounting engine as the browser edition, but a Python process reads configured sources and saves metadata automatically to SQLite. Read the [privacy comparison](PRIVACY.md#optional-collector-edition) before choosing this mode.

## Start with fictional data

Extract the source release, open a terminal in its directory, and run:

```sh
python3 server.py --demo
```

Open [127.0.0.1:8787](http://127.0.0.1:8787). Python 3.10+ is required; no Python packages need installing. Demo mode seeds fictional records in memory, reads no local Codex folders, and rejects evidence changes. Cost exploration is available, with named cost assumptions saved separately in browser storage. Stop the process with Ctrl+C.

On Windows, use `py -3` if `python3` is unavailable. Linux/WSL is the verified collector environment; native Windows/macOS operation has not yet been verified.

## Collect your own logs

```sh
python3 server.py
```

On first launch, the collector uses `CODEX_HOME`, or `~/.codex` when it is unset. Later launches use the source configuration saved in the database. In **Sources & coverage**, add, edit, disable, or remove folders and inspect their availability.

A configured home includes `sessions/**/*.jsonl` and `archived_sessions/**/*.jsonl`. A direct session folder includes its JSONL files recursively. The first scan runs in the background; the collector rescans every 30 seconds, skipping files whose size and modification time are unchanged. Changed files are reread, not tailed by byte offset. The open interface refreshes every 10 seconds. Removing a configured source retains evidence already indexed.

```sh
# Choose another port and a specific home.
python3 server.py --port 8788 --source /path/to/codex-home

# Collect more than one home.
python3 server.py --source /path/to/first-home --source /path/to/second-home

# Start with no automatic sources and a separate database.
python3 server.py --no-scan --db /path/to/import-only.sqlite3
```

Explicit `--source` or `--no-scan` options replace the saved source list and record that change in the audit history. You can add sources through the interface afterward. For copied logs, select **Another computer / Windows copy** so they do not acquire the local collector's identity. See [Windows and multiple sources](WINDOWS-SOURCES.md).

The process is not installed as a startup service. Collection ends when the process stops; closing a browser tab alone does not stop it. Desktop notifications require permission and an open app page. No email, webhook, credential revocation, or automatic request blocking is implemented.

## Local server boundary

The server binds to `127.0.0.1`. It validates Host and Origin, requires a per-process token for mutations, restricts public assets, escapes source text, and uses a Content Security Policy. There is no remote-user authentication. Do not expose this single-user service to an untrusted network.

Loopback port forwarding is supported when the browser-facing host is literal `localhost`, `127.0.0.1`, or `[::1]`, and any request Origin matches that host and port. Forwarding headers do not grant access. A process with your OS privileges can access the service or database.

## Storage and backups

The default database is `.data/ledger.sqlite3` beside the source code, with possible SQLite WAL sidecars. The collector attempts to create private filesystem permissions and uses a private umask; enforcement depends on the platform. The database is not encrypted by the app and is excluded from source releases.

Use **Sources & coverage → Export complete evidence** for a consistent normalized JSON snapshot. It includes all evidence tables and the audit chain, but no source log bodies or browser-local cost assumptions. View filters do not narrow this export. The collector has no JSON restore endpoint.

For a database backup, stop the collector before copying the database and any remaining WAL sidecars, or use SQLite's online backup API. Keep backups private. Cost assumptions in the collector's browser origin are separate from the database.

To migrate to the browser edition, download the complete evidence export and follow [Restore or migrate](BROWSER.md#restore-or-migrate). Migration does not delete the collector database, stop the collector process, or transfer saved browser-origin cost assumptions.

The collector has no per-record deletion endpoint or browser-edition Forget button. If you intend to remove its local workspace, stop the process and manage its database, sidecars, browser preferences, and downloaded copies separately. Keep the original logs if you need to reconstruct the ledger later.

## Next steps

- [Using the ledger, attribution, and imports](GUIDE.md)
- [Privacy and retained metadata](PRIVACY.md)
- [Development and tests](CONTRIBUTING.md)
