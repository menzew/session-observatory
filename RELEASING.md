# Preparing a public release

This directory is a standalone project. Its release archive has no dependency on its parent workspace. Do not publish the parent repository or copy the entire working folder: those may contain unrelated work and personal data.

## Release attachments

The main user download is **session-observatory-browser.html**. Put it first in release instructions and include its checksum. Publish these artifacts together:

| Artifact | Purpose |
|---|---|
| `session-observatory-browser.html` | Ready-to-open offline browser app |
| `session-observatory-browser.html.sha256` | Checksum for the HTML |
| `browser-runtime-manifest.json` | Embedded runtime asset hashes |
| `session-observatory-<version>.zip` and its `.sha256` | Reviewed standalone source and checksum |

GitHub's automatic source downloads do not include the built HTML. Make that distinction explicit so users do not need to install Node or Python just to try the app. Link [BROWSER.md](BROWSER.md) and [PRIVACY.md](PRIVACY.md) from release notes. Keep the collector download/setup instructions secondary.

## Build and verify

```sh
python3 -m unittest discover -v
npm ci --ignore-scripts
npx playwright install chromium
npm run test:syntax
npm run build:browser
npm run test:offline
npm run test:browser
python3 scripts/release.py --check
python3 scripts/release.py
```

The release builder reads **RELEASE_FILES.txt**, validates local documentation links, rejects unsafe paths and private file types (including SQLite sidecars and local agent configuration), scans common credential patterns in every file, and writes a source ZIP plus SHA-256 checksum into ignored `dist/`. The archive version comes from `package.json`; existing archives or checksums are never overwritten. Only explicitly reviewed files appear in the archive. When adding a public source file, add it to the manifest. Do not add real logs, exports, databases, screenshots of personal usage or generated caches. Automated scanning cannot establish that arbitrary data is safe to publish.

In a Git checkout, run `python3 scripts/release.py --check --check-tracked` after staging changes. CI enforces the same check, then builds, extracts and tests the source archive independently. This catches files accidentally tracked outside the allowlist; `.gitignore` does not remove already tracked files. Archive builds also work without Git.

Extract the ZIP into a fresh directory. From there, run the Python suite and `python3 server.py --demo`; then install the declared browser development dependencies and run the browser suite. Check that demo mode uses fictional data and the app can start independently. Documentation screenshots must be captured in demo mode; never copy a screenshot from your live workspace.

Test `dist/session-observatory-browser.html` directly as a local file with networking disabled. Verify first use with an empty browser context, explicit Save and reload, complete backup and restore, and Forget. The offline suite exercises these flows with synthetic evidence and checks zero HTTP requests. Publish the builder output, not a browser “Save page as” copy or a workspace backup. The HTML includes third-party licenses and source references; retain them.

## Repository setup

When the owner chooses a repository destination, initialize that repository from the reviewed archive contents. Retain LICENSE and NOTICE. Use the README description, Apache-2.0 license, and the bundled CI workflow. Enable GitHub private vulnerability reporting before announcing the project; SECURITY.md explains the fallback when this is unavailable. No deployment, telemetry service, inference key or repository secret is needed for CI.

Review repository visibility and the staged diff before the initial push. Create an annotated version tag and attach the verified ZIP/checksum when publishing a release. These publication steps are separate from preparing the local artifact; the build script never creates a repository, pushes, publishes, or sends notifications.

Initialize a fresh public repository from the extracted archive to publish only reviewed files. The release checks inspect current file contents, not Git history. If you instead reuse an existing repository, review its entire history for credentials and private evidence before changing visibility; a clean working tree does not establish a clean history.

Verify downloaded artifacts from their directory with `sha256sum -c <artifact>.sha256` on Linux, `shasum -a 256 -c <artifact>.sha256` on macOS, or compare `Get-FileHash <artifact> -Algorithm SHA256` with the checksum on Windows. Checksums detect changes to the downloaded bytes; they are not a publisher signature.

## Release notes

Use CHANGELOG.md. Lead with the browser workflow: local HTML, selected-file imports, no runtime network requests, and explicit workspace saving. State that metadata/backups remain private and are not encrypted by the app; link the privacy document for the complete boundary. Describe the local/import-only coverage and dated price snapshot. Do not advertise account-wide session monitoring, actual subscription spend, model routing or confirmed savings from switching models. Native Windows/macOS compatibility is not yet verified. Prices and provider log formats may change independently of the app.
