# Privacy and your data

Session Observatory processes your selected evidence on your computer. The browser edition runs from one local HTML file, without an account connection, uploads, telemetry, or runtime downloads. You choose whether to keep a workspace snapshot or download an export.

Local processing still involves private data. Project paths, task identifiers, attribution, and activity metadata can reveal what you work on and who you work with. This page explains what the application reads and retains, and where its protections end. For operating instructions, see the [browser guide](docs/browser.md). Report vulnerabilities through [SECURITY.md](SECURITY.md).

## What happens when you open the HTML

The HTML contains the interface, accounting code, and WebAssembly runtime. Opening it starts the engine inside the browser. It does not search your disk, open your Codex home, or connect to an OpenAI account.

The app checks its browser storage for a workspace you previously saved. If one is available, it loads automatically. Otherwise, evidence starts in memory only. Opening the app can create an empty IndexedDB database; **memory only** means that the app does not persist your evidence or named cost assumptions until you choose **Save in this browser**. It does not mean the browser or operating system makes no disk writes.

The original HTML file is not modified when you import, save, or restore evidence. Your workspace is separate from the application download.

## What the app reads

| Action | Data read | What happens next |
|---|---|---|
| Choose a log folder | Eligible `.jsonl` files in the selected folder and its subfolders | Each file is read into memory, parsed, and reconciled with the current ledger |
| Import one evidence file | The selected supported JSON or JSONL file | Accounting or activity fields are extracted; provider and activity imports use your declared account label |
| Restore / migrate evidence | A complete evidence backup you select | The backup is validated and replaces this tab's workspace after confirmation |
| Open the app again | This app's previously saved browser snapshot, if available | The snapshot is restored without rereading the original logs |

Folder import skips other file extensions and filenames containing `auth`, `credential`, `secret`, or `.env`, without reading those files' contents. The single-file importer also rejects those filename patterns. These are filename checks, not a universal detector of secrets inside arbitrary files. Do not rename credential files to bypass them.

**Selected log files are read into memory, including any conversation text they contain.** Parsing retains supported accounting fields; it does not retain prompt bodies, tool arguments/results, or full conversations in the ledger. Transient file contents are not a secure-erasure boundary: this app cannot control browser memory management, swap, crash dumps, or operating-system backups.

Folder selection supplies relative folder/file labels. The app also retains project paths found *inside* the logs; those can be absolute paths even when the picker provides only a relative filename. A restored collector export can contain its original source paths and settings.

The browser edition does not keep a filesystem watcher, reread folders on a timer, or change the source files. Re-select a folder to import changes. Removing a source file from disk does not remove evidence already imported.

## What the ledger retains

When available in the input, retained metadata includes:

- Token counts, model/provider names, timestamps, and historical limit observations.
- Task, turn, response, and lineage identifiers; application/client details; project paths and Git branch/commit information.
- Source labels, file/line references, hashes, parsing notices, and conflicting observations.
- Your declared project, responsible person or workload, purpose, and reasons for changes.
- Imported provider buckets and their account/project/key identifiers; imported activity actor, device, IP address, action, and evidence references.
- Budgets, policies, alerts, and an audit history of changes.

Identifiers such as an API-key ID or session ID are intended to be non-secret references, not reusable credentials. Allowed text fields are not automatically anonymized or scrubbed: sensitive information placed in a project name, purpose, or imported metadata field can be retained and exported. Backup validation checks structure and consistency; it is not a privacy filter.

Source hashes support provenance and deduplication. They do not make the associated metadata anonymous or establish that the provider signed a record.

## Where your data lives

| Location | When a copy exists | Persistence and protection |
|---|---|---|
| Open tab | During use | Unsaved changes are lost on reload or close; the app adds no encryption or secure-erasure guarantee |
| Browser storage | After **Save in this browser** | A snapshot in IndexedDB, associated with the browser's storage context; no application-level encryption |
| Download folder or chosen destination | After an export or **Download complete backup** | An ordinary file under your control; no application-level encryption |
| Original log folders | Before import and afterward | Unchanged by the browser app; managed by you and the software that created them |

**Save is explicit.** Imports, attributions, and other changes do not update the saved snapshot automatically. Save again to keep later changes. In the browser edition, naming a cost scenario with **Save assumptions** changes the open workspace; use **Save in this browser** or **Download complete backup** to keep it after closing.

Browser storage depends on the browser, profile, and handling of local files. Private browsing, storage cleanup, a different profile, or moving/renaming the HTML may make a saved workspace unavailable. Separate HTML copies are not a guaranteed isolation boundary between people or projects. Keep a complete backup when the workspace matters.

If two tabs share a saved workspace, a stale tab cannot silently overwrite a newer saved revision. It must download a backup and reload before saving. This protects against accidental conflicts; it does not make another open tab forget data already in its memory.

## Backups, sharing, and deletion

**Download complete backup** includes all evidence tables, including excluded records and conflicts, attribution and audit history, policies, and named saved cost assumptions. View filters do not limit the complete backup. A ledger CSV, individual-record JSON, or cost-scenario export contains a subset and cannot restore the whole workspace.

All these exports can contain private metadata. They are not anonymized reports. A destination folder may be synchronized or backed up by other software; the app does not control what happens after a download. For public issues and screenshots, use the fictional demo rather than real records.

**Forget this workspace** clears this tab's evidence and assumptions and removes the app's saved evidence snapshot after confirmation. A revision marker remains in browser storage to prevent a stale tab from silently saving old evidence over the deletion. Original logs, downloaded files, collector databases, copies in other browser profiles, and evidence already open in other tabs remain. Close other tabs containing the workspace as part of clearing your current session. Forget is not forensic erasure.

Restoring a backup replaces this tab's workspace, not the saved browser snapshot. Choose Save afterward if you want the restored workspace to load on the next opening. Download a backup before replacing evidence you still need.

## Hosted web edition

The public GitHub Pages site serves the same browser app over HTTPS. Opening or reloading the page makes a request to the site host, which can receive normal request metadata such as your IP address and user agent. Once loaded, selected evidence is processed in the browser; it is not uploaded to GitHub or an application backend. Explicitly downloading the offline HTML also contacts the host.

Hosted browser storage is associated with the site origin and profile, not a guaranteed per-page isolation boundary. Other Pages projects on the same origin can share that browser storage boundary. A saved hosted workspace does not automatically transfer to the downloaded local HTML: use a complete backup and restore. The downloaded version can be opened without contacting the site.

## Network boundary

After its initial document load, the browser application makes no HTTP requests while processing evidence. Opening the downloaded HTML directly also avoids a request for that document. It has no OpenAI client, account login, telemetry, remote fonts, or CDN fallback. Its Content Security Policy blocks runtime connections, frames, and form submissions. The worker loads its runtime resources from embedded bytes.

Downloading the application initially, installing development dependencies, and clicking external documentation or runtime-source links involve network access. External links open only when clicked. The offline guarantee describes the application while processing evidence; it does not disable networking for your browser, extensions, or operating system.

The automated offline test opens the HTML directly with networking disabled, imports synthetic evidence, exercises saving and restoration, and asserts zero HTTP requests. That test covers the tested build and browser; it is not an independent security audit.

## Optional collector edition

The [collector](docs/collector.md) has a different storage and access boundary. A Python process reads configured folders and persists metadata automatically in a local SQLite database, normally `.data/ledger.sqlite3`. Your browser talks to that process over loopback HTTP. The app makes no OpenAI API calls, but it does use a local server.

Collector cost assumptions are stored separately in the browser's localStorage. Browser-edition Save and Forget controls do not manage the collector database or its browser preferences. An evidence export can migrate the collector's ledger into the browser edition, but the original database remains on disk.

## Limits of protection

This is a local, single-user tool. It does not protect evidence from someone with access to your browser profile, a privileged extension, a compromised browser or operating system, or downloaded copies. The app provides no password lock or application-level encryption.

The audit chain can detect internal inconsistencies. It cannot prevent someone who controls the data from rewriting the ledger and chain together. Local imports also cannot establish verified login identity, see all account activity on other devices, or prove that an account is safe.
