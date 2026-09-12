# Architecture and repository layout

Session Observatory is browser-first in operation: the primary deliverable is one offline HTML file. Its accounting implementation is Python, executed inside the browser through bundled Pyodide/WebAssembly. End users do not install Python, start a process, or connect to a server.

The optional collector runs the same engine in native Python. Sharing the engine keeps evidence parsing, response deduplication, decimal pricing, and audit validation consistent between the two editions.

## Browser execution

```text
Local HTML
  └─ web/ interface
       └─ web/browser/browser.js: selected files, saving, backups
            └─ web/browser/worker.js: embedded Pyodide runtime
                 └─ web/browser/bridge.py: in-process requests
                      └─ engine/: in-memory SQLite and accounting
```

The interface reads selected files and sends their text to a worker. The Python bridge calls the shared engine directly. Request names beginning `/api/` identify in-process operations in this mode; they do not create HTTP requests. The worker's runtime resources resolve from embedded bytes with no network fallback.

The browser adapter owns IndexedDB snapshots, explicit saving, complete backups, restoration, and stale-tab revision checks. The engine operates on an in-memory ledger. Privacy details are in [Privacy](../PRIVACY.md); user instructions are in the [browser guide](browser.md).

## What gets embedded

`scripts/build-browser.mjs` reads an explicit list of assets: the shared interface, browser adapter, worker/bridge, `engine/` Python modules, pinned runtime bytes, and license notices. It produces `dist/session-observatory-browser.html`, its checksum, and a runtime asset manifest.

The `collector/` server, tests, development dependencies unrelated to the runtime, and local evidence are not embedded. Node is a build tool, and Python is provided by the embedded runtime when the HTML runs. The source release includes both editions and their tests so contributors can inspect and reproduce them.

## Hosted static site

`npm run build:pages` stages the browser HTML as `dist/site/index.html` with an offline download and checksums. The Pages server only serves those static assets; selected evidence still goes through the in-browser worker and engine. Hosted storage uses the site origin, while a downloaded HTML uses the browser’s local-file storage rules.

## Optional collector execution

```text
Browser → loopback HTTP → collector/server.py → engine/ → local SQLite
```

`python3 -m collector` runs the optional server from the repository root. It serves the shared `web/` assets, validates local HTTP requests, and starts scheduled scans of configured sources. The default database remains `.data/ledger.sqlite3` at the repository root, separate from application source. Moving Python modules does not move an existing database.

The collector does not load the offline browser adapter. Its evidence persistence is automatic, while the browser edition saves snapshots explicitly. See the [collector guide](collector.md) for operation and backup details.

## Ownership by folder

| Folder | Owns |
|---|---|
| `web/` | Browser interface and offline adapter |
| `engine/` | Shared evidence and accounting behavior; no HTTP listener |
| `collector/` | Optional local HTTP server and collection scheduling |
| `tests/` | Synthetic engine and integration regressions |
| `scripts/` | Build and source-release tooling, including `release-files.txt` |
| `docs/` | User, architecture, product, and maintainer guides |
| `third_party/` | Runtime notices and preserved upstream license texts |
| `examples/` | Synthetic evidence for import examples |

Generated browser/source artifacts belong in ignored `dist/`; test screenshots belong in ignored `test-results/`. Local evidence stays outside the source allowlist. Keep the top level focused on the project overview, privacy/security policies, contribution guidance, changelog, licenses, and dependency manifests.

## Verification

`python3 -m unittest discover -v` discovers the `tests` package. `npm run test:offline` tests the generated local HTML with networking disabled. `npm run test:browser` tests the optional collector using an isolated temporary database. Browser tests resolve paths from their own location, and the collector test starts Python with the repository root as its working directory.

The release allowlist is `scripts/release-files.txt`. Packaging tests validate a standalone archive, so imports and asset paths must work after extraction without the original workspace. See [Contributing](../CONTRIBUTING.md) and [Releasing](releasing.md) for the full commands.
