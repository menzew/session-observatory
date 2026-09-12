# Contributing

Session Observatory is a browser-first, local accounting tool. Start with the [README](README.md), [browser guide](docs/browser.md), and [privacy boundary](PRIVACY.md). The [user guide](docs/guide.md) defines evidence formats and accounting behavior. [Product scope](docs/product.md) and [Design principles](docs/design.md) describe the product and interface principles.

## Build and try the browser edition

Node.js 22+ builds the standalone HTML and runs browser tests. Python 3.10+ runs the engine tests and optional collector; there are no additional Python packages to install.

```sh
npm ci --ignore-scripts
npm run build:browser
```

Open `dist/session-observatory-browser.html` and choose **Try fictional demo**. Use synthetic data for development, screenshots, and reports. For collector development, run `python3 -m collector --demo` and follow [the collector guide](docs/collector.md).

## Source map

| Location | Responsibility |
|---|---|
| `web/` | Shared browser interface, styles, filtering, and interaction |
| `web/browser/` | Offline file pickers, worker, in-process bridge, saving, and backups |
| `engine/` | Accounting, evidence, analysis, pricing, quotas, and synthetic demo data; embedded into the browser runtime |
| `collector/` | Optional loopback server; launch from the repository root with `python3 -m collector` |
| `tests/test_*.py` | Shared-engine, collector, bridge, and release regressions |
| `tests/browser/` | Offline HTML and collector browser integration checks |
| `scripts/` | Explicit browser asset embedding, source archive builder, and public file allowlist |
| `third_party/` | Bundled runtime license texts and source references |
| `docs/`, `examples/` | Detailed guides and synthetic import examples |

Read the [architecture guide](docs/architecture.md) before changing the boundary between browser, engine, and collector. Run commands from the repository root; no Python package installation or `PYTHONPATH` customization is required.

## Required checks

Run these from the source directory:

```sh
python3 -m unittest discover -v
npm ci --ignore-scripts
npx playwright install chromium
npm run test:syntax
npm run build:browser
npm run test:offline
npm run test:browser
npm run build:pages
npm run test:hosted
python3 scripts/release.py --check
```

The offline suite opens the HTML directly with networking disabled and uses only synthetic evidence. The collector browser suite starts an isolated temporary database and loopback server. Python tests also use temporary databases; none of these checks needs your local Codex history. Screenshots go into ignored `test-results/`.

Set `OBSERVATORY_BROWSER` to use an existing compatible Chromium executable. On Windows, `py -3` can replace `python3` for manual Python commands. The browser integration harness currently invokes `python3` itself. Linux/WSL is the verified development environment; native Windows/macOS validation is welcome.

In a Git checkout, run `python3 scripts/release.py --check --check-tracked` after staging changes. CI rejects tracked files outside `scripts/release-files.txt`, even if `.gitignore` matches them. Add new public source or documentation files to the manifest in the same change. See [Releasing](docs/releasing.md) for standalone archive verification.

## Preserve the privacy contract

Changes to imports, storage, exports, or the build must preserve the documented user choices:

- Opening the browser app reads no log folders automatically; a previously saved snapshot may load.
- Evidence and named cost assumptions persist only on explicit workspace Save or download. Do not introduce autosave implicitly.
- Runtime resources come from embedded assets. New fonts, analytics, CDNs, or network fallbacks would change the offline contract.
- Parsing retains supported metadata rather than conversation bodies. Do not log raw import text, credential values, or error traces containing evidence.
- Backups contain private metadata. Restore validates data in the app's schema and must preserve the current ledger on failure.
- Forget clears the current workspace and saved evidence while preserving the stale-tab protection. Its limits must remain explicit.

Update [Privacy](PRIVACY.md) and [Browser guide](docs/browser.md) whenever these behaviors change, and cover the resulting behavior in the offline tests. No real databases, rollout files, account labels, keys, prompts, private paths, or personal screenshots belong in issues or pull requests. Report vulnerabilities through [SECURITY.md](SECURITY.md).

## Make a focused change

Describe the user-visible problem, resulting behavior, and what you verified. For UI changes, include synthetic screenshots and check a narrow screen and keyboard navigation. Keep privacy status, save actions, and source uncertainty visible. Follow the existing rose accent, readable system typography, and native controls.

For metering changes, test deduplication, total reconciliation, missing fields, excluded observations, and exact filter matching. Cached input is already part of input; reasoning is already part of output. Preserve original observations and keep attribution in the audit trail. Pricing changes need explicit decimal examples and a dated primary source; never infer prices for unknown models.

## Dependencies and licensing

`package.json` is private to prevent accidental npm publication; distribution is source plus a standalone HTML artifact. Playwright is test-only. The pinned Pyodide runtime is embedded in the browser build. Preserve its license notices and matching upstream source references when upgrading, and verify the offline artifact again.

Contributions are under the repository's Apache-2.0 license. Retain LICENSE and NOTICE. Be respectful and constructive, and focus feedback on the work.
