# Browser guide

The browser edition is the main way to use Session Observatory. Open one local HTML file, import evidence you choose, and explore it offline. You do not need Python, Node, a local server, an OpenAI account connection, or an API key to use the built file.

This guide covers the workflow. [Privacy and your data](PRIVACY.md) explains exactly what is read and retained, how browser storage works, and what deletion leaves behind.

## First opening

Download **session-observatory-browser.html** from the repository's Releases page and open it in a recent desktop Chrome or Edge browser. If you only have source files, follow [Build from source](#build-from-source). An HTML attachment is separate from the source ZIP.

The file is about 18 MB because it includes its runtime. Startup takes a few seconds and needs no internet connection. The app opens at **Sources & privacy**. It loads a previously saved browser workspace if one is available; otherwise it starts empty, in **Memory only** mode.

To look around before importing real data, choose **Try fictional demo**. It works only in an empty workspace. Explore the charts and cost controls, then use **Forget this workspace** before importing your own records so fictional usage stays separate.

## Import your logs

1. In **Sources & privacy**, click **Choose Codex log folder**. The top-bar **Choose log folder** button opens the same picker.
2. Select a folder containing your Codex JSONL logs. Start with a `sessions` folder; add `archived_sessions` separately if you need older history.
3. Wait for the import summary. It reports imported files, new usage entries, limit readings, skipped files, and files that could not be imported.
4. Review **Source quality** for parsing notices, then open **Usage ledger** or **Consumption analysis**.

Default-home examples are `~/.codex/sessions` on Linux/macOS and `%USERPROFILE%\.codex\sessions` on Windows. Use the actual home configured for your installation if it differs. Hidden folders may need to be shown in the picker. See [Windows, WSL, and custom homes](WINDOWS-SOURCES.md).

You can choose multiple locations in succession. Folder selection reads eligible `.jsonl` files recursively, skips other file types and credential-like filenames, and accepts up to 30 MB per file. Files that fail do not undo successful imports from other files. Import large collections as smaller subfolders when needed.

The picker supplies relative source labels; project paths contained in the logs are retained separately. The app cannot discover every installation or verify the person/device that produced a copied log. Imported metadata remains private even though conversation bodies are not retained.

### Refresh manually

Re-select the folder to read updated files. There is no background watcher and no collection while the page is closed. Native response IDs and the legacy accounting rules reconcile duplicated evidence; copied logs do not automatically count as new usage. Deleting a log on disk does not remove previously imported evidence.

### Import one file or another evidence type

Use **Import one evidence file** on the privacy page, or **Import records** in the top bar. Supported inputs are Codex JSONL, provider usage/cost JSON pages, and the app's normalized activity JSON format. Provider and activity imports require an account/workspace label you declare; this does not authenticate an account.

Use **Restore / migrate evidence** for a complete workspace backup. It is a different operation from importing additional records. See the [import contracts and examples](GUIDE.md#import-formats).

## Explore the workspace

Start with **Consumption analysis** to find the largest projects, models, or tasks. Click a chart segment or group to narrow the selection, then open the matching ledger records to inspect the source evidence.

In **Cost analysis**, compare your recorded workload at the included API rates with a different model, cache assumption, or workload size. These are hypothetical costs at a dated snapshot, not subscription charges. Unknown prices and unsupported comparisons stay explicit. See [Cost analysis](COSTS.md).

**Limits & cycles** shows source-reported historical observations, not a live quota feed. Ownership and purpose are explicit declarations with an audit history. Other features and accounting definitions are in the [user guide](GUIDE.md).

## Save or make a backup

| Control or status | What to expect |
|---|---|
| **Memory only** | No saved evidence snapshot has been loaded or created for this workspace |
| **Unsaved changes** | The tab contains changes that are not in its saved browser snapshot |
| **Save in this browser** / **Save changes in browser** | Write a snapshot to IndexedDB in this browser's storage context |
| **Saved in this browser** | The snapshot can load on reopening, subject to browser storage availability |
| **Download complete backup** | Download a portable JSON snapshot, including evidence, audit history, and named saved cost assumptions |

Save again after later imports or edits. There is no autosave. A complete backup includes the whole evidence workspace, not just the current filtered view. A cost export, ledger CSV, or individual record JSON is not a restorable workspace backup.

In the browser edition, **Save assumptions** names a cost scenario inside the current workspace. To keep it after closing, also use **Save in this browser** or **Download complete backup**. Naming a scenario alone does not persist it to disk.

Reloading or closing discards unsaved changes. If a saved snapshot exists, reopening returns to that snapshot. The app asks the browser to warn before leaving with unsaved work, but browsers may suppress the prompt. Downloading a backup does not mark the tab as saved, so the warning can still appear.

Saved workspaces and downloads are not encrypted by the app. Browser cleanup, private mode, changing profiles, or moving/renaming the HTML can make a saved snapshot unavailable. Use a complete backup for a workspace you need to keep, and store it as private data.

## Restore or migrate

1. Download a complete backup of the current tab if you need to keep it.
2. Choose **Restore / migrate evidence** and select a complete Observatory evidence JSON file.
3. Confirm that the selected backup should replace this tab's workspace.
4. Check the restored records. Choose **Save in this browser** if you want this state to load on the next opening.

Restore replaces the tab's evidence; it does not merge workspaces or overwrite the saved browser copy until you Save. The engine checks table/column structure, evidence references, and the audit chain, and inserts values into its own schema. Invalid or incompatible evidence is rejected without replacing the active ledger. Restore accepts JSON up to 512 MB, subject to available browser memory; the size limit is not a promise that every device can load a file that large.

To migrate from the optional collector, use **Sources & coverage → Export complete evidence** there, then restore that JSON here. Evidence and audit history are retained. Collector source settings stay historical metadata and are never activated by the browser. Cost assumptions saved under the collector's browser origin must be recreated or exported separately. The original collector database and process are unaffected.

## Forget a workspace

Choose **Forget this workspace** and confirm. This clears the current tab's evidence and named assumptions and removes the saved evidence snapshot. Original logs, downloaded backups, and collector databases remain.

Other open tabs can still hold their own in-memory copies. A revision marker prevents them from silently saving stale evidence over the deletion. Close those tabs too if you want to clear the active session. Forget is not forensic erasure; see [the deletion boundary](PRIVACY.md#backups-sharing-and-deletion).

## Troubleshooting

| Problem | What to do |
|---|---|
| The engine does not start | Open the actual HTML file in a recent desktop Chrome or Edge browser, rather than a preview pane. Close other large tabs and retry. No runtime download is required. |
| No usage appears | Check the selected folder and import summary. Only recognized usage or limit records become evidence; unrelated JSONL files do not. Incomplete final lines are skipped until a later import. |
| A large folder import fails | Select smaller subfolders. Individual imports are limited to 30 MB and browser memory is finite. Successful files from the batch remain imported. |
| Saved data is missing after reopening | Check the browser/profile and HTML location. Restore your complete backup; do not assume another local HTML copy has separate or identical storage. |
| Storage is unavailable or a Save fails | Keep the tab open and download a complete backup before closing. A storage failure does not intentionally clear the in-memory workspace. |
| “Another tab changed the saved workspace” | Back up this tab, reload to see the newer saved revision, and decide which workspace to keep. The app rejects silent overwrites. |
| A backup cannot be restored | Keep the original file. Check its format and app version; ledger CSV and cost exports are not backups. Prefer the app version that created it when investigating compatibility. |

For a bug report, provide the app/build version, browser, operating system, and a synthetic reproduction. Do not attach your real logs, workspace backup, or private screenshots. See [Contributing](CONTRIBUTING.md).

## Build from source

Developers need Node.js 22+; end users need only the output HTML. From the extracted source directory or checkout:

```sh
npm ci --ignore-scripts
npm run build:browser
```

Open `dist/session-observatory-browser.html`. The build also writes its `.sha256` checksum and `browser-runtime-manifest.json`. Installing dependencies needs network access; using the built app does not. The builder reads explicit source/runtime assets, not `.data`, user logs, browser storage, or test screenshots.

To verify the browser edition:

```sh
npx playwright install chromium
npm run test:syntax
npm run test:offline
```

The offline test opens the local HTML with networking disabled and synthetic data. It covers imports, saving, backups, restoration, deletion, and zero HTTP requests. Chromium on Linux is verified. Native Windows/macOS testing is still welcome; narrow layouts are tested, but large imports target desktop browsers.

The shared Python accounting engine runs inside a worker with bundled Pyodide, SQLite, and decimal arithmetic. No Python installation or additional runtime package download is required. See [Contributing](CONTRIBUTING.md) for the source map and complete checks.

## Licenses and sources

Application source is Apache-2.0. Bundled components retain their licenses, including Pyodide MPL-2.0. Full texts and source references are included under **Sources & privacy → About, licenses and runtime sources** and in [third-party notices](browser/THIRD-PARTY.txt). External source links use the network only when you choose to open them.
