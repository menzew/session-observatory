# Windows, WSL, and multiple log folders

The browser edition reads folders you select through the native file picker. It does not need WSL, a local server, a mounted drive, or a server-path mapping to read files available to that picker. Start with the [browser guide](BROWSER.md).

Source locations depend on the Codex installation and its configured home. The examples below are starting points, not a claim that every installation or Work action writes metering logs there. Use the folders that actually contain your session JSONL files.

## Browser edition

In **Sources & privacy**, choose **Choose Codex log folder**. Select `sessions`, then repeat for `archived_sessions` if you want older history. Hidden folders may need to be shown in the file picker.

| Where the logs live | What to select |
|---|---|
| Native Windows default home | `%USERPROFILE%\.codex\sessions` and `%USERPROFILE%\.codex\archived_sessions` |
| Custom `CODEX_HOME` | The corresponding session folders inside that home |
| WSL installation | That distribution's session folders, if accessible to the picker; otherwise a local copy you make available |
| Linux/macOS default home | `~/.codex/sessions` and `~/.codex/archived_sessions` |
| Copied or synchronized logs | The folder containing the copied JSONL files |
| Multiple profiles or homes | Select each known location in succession |

Windows and WSL can have separate histories. Changing where SQLite state lives does not necessarily move the JSONL logs. Select evidence folders rather than application installation directories, credential stores, browser cookies, or caches.

Folder import reads eligible JSONL files recursively and reports what was imported or skipped. Re-select a folder to refresh it. Native response identity and legacy accounting rules reconcile duplicate evidence. The browser retains relative folder/file labels as source references, while absolute project paths inside the logs may remain in the ledger. Copied logs do not establish verified device or user identity. See [Privacy](PRIVACY.md#what-the-app-reads).

## Optional collector edition

Only the [collector edition](COLLECTOR.md) has **Sources & coverage**, persistent automatic source settings, and a **Path on this server** field.

| Source | Collector configuration |
|---|---|
| Native Windows home | For example, `C:\Users\alex\.codex`, type **Codex / ChatGPT Work home** |
| Custom home | Its actual absolute directory, added as a separate home |
| WSL home | The Linux home path accessible to the collector process |
| Windows home mounted in WSL | A Windows path can map through `/mnt/c` when available; otherwise supply an explicit accessible server path |
| Copied logs | Type **Session folder**; mark **Another computer / Windows copy** |

A configured home includes both `sessions` and `archived_sessions`; a direct session folder includes JSONL files recursively. Source settings persist in the collector database. Removing a source retains its previously indexed evidence.

**A browser tab does not give the collector access to the browser computer's disk.** If the collector runs in Linux/WSL or on another host, its process must already be able to read the configured path. A Windows folder remains unavailable until exposed through an existing mount/copy or read by a collector running on Windows. **Path on this server** maps to an accessible location; it does not mount drives, synchronize files, or authenticate to another computer.

Use **Import records** for a one-time file import when automatic source access is unnecessary. Provider and normalized activity JSON use that importer in either edition.

## Compatibility

Chromium on Linux and collector operation on Linux/WSL are verified. Native Windows/macOS testing is still welcome. Browser folder-picker support and access to WSL paths depend on the browser and OS environment. If a folder is inaccessible, work from a copy of the relevant logs and retain the originals.
