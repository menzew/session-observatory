# Security policy

Session Observatory is a local, single-user application. The browser edition is the primary distribution; the optional collector has a separate loopback-server boundary. The current 0.1.x line receives fixes on a best-effort basis. The project has not received an independent security audit.

For user-facing details about selected files, storage, backups, and deletion, read [Privacy and your data](PRIVACY.md).

## Report a vulnerability

Use this repository's **Security → Report a vulnerability** feature when available. Include the affected version, browser/OS, edition (local HTML or collector), a minimal synthetic reproduction, and the impact.

Do not attach credentials, real logs, workspace exports, or private screenshots. If private reporting is unavailable, open an issue asking for a private reporting channel without disclosing exploit details or sensitive data. Ordinary bugs can use the repository's issue template.

## Browser edition boundary

The distributed HTML embeds its application and WebAssembly runtime. It reads selected files, performs parsing locally, and makes no runtime HTTP requests. A Content Security Policy blocks connections, frames, and form submission. Worker runtime resources resolve from embedded bytes with no network fallback. External documentation links are opened only on a user click.

Evidence starts in memory unless a previously saved snapshot is loaded. Explicit Save writes evidence to IndexedDB. The app does not encrypt snapshots or exports, provide a password lock, or isolate data from a privileged extension or someone with access to the browser profile. Separate local HTML copies are not a guaranteed storage isolation boundary.

Credential-like filenames are rejected or skipped by the import paths. This does not detect every possible secret in file contents. The log parser keeps selected metadata rather than conversation bodies; allowed text fields and restored backups must still be treated as potentially private. Source text is escaped, and CSV exports neutralize spreadsheet formula prefixes.

Backup restoration accepts data into the application's own schema. It checks table and column structure, evidence references, and audit-chain consistency; imported schemas, SQL, and Python are not executed. Failed validation leaves the active ledger intact. Large input limits bound individual operations but do not guarantee enough memory on every device.

Explicit saving uses revisions to reject stale-tab overwrites. Forget removes saved evidence and clears the current tab, while retaining a revision marker. It cannot erase downloaded backups, original logs, other profiles, or in-memory copies already held by other tabs.

## Optional collector boundary

The collector binds to loopback and uses Host/Origin validation, a per-process mutation token, CSP, source-text escaping, CSV formula protection, and an allowlist of public assets. It has no remote-user authentication. A process running with the same OS privileges can access the service or local data; do not expose the listener to an untrusted network.

The collector intentionally reads configured session logs and persists permitted accounting metadata to SQLite. It does not log in to OpenAI, open Codex authentication files as accounting sources, or intercept model requests. Database permissions are best effort and platform-dependent; the application does not encrypt the database. See [collector operation](docs/collector.md).

## Evidence integrity and scope

A local audit hash chain detects inconsistencies, not an operator rewriting both data and chain. Records and attribution do not establish verified login identity. Activity alerts evaluate imported evidence and cannot prove that a credential was stolen or that an account is safe. No account-wide session feed, credential revocation, or external alert delivery is implemented.

## Release handling

Build public source archives with [scripts/release.py](scripts/release.py) and the reviewed file allowlist. Local data, exports, agent configuration, and generated test screenshots are excluded. Automated credential scans supplement human review; they do not establish that arbitrary metadata is safe to publish or scan Git history.

Public screenshots and reproductions must use synthetic data. Preserve runtime license texts and source references, test the generated HTML offline, and follow [Releasing](docs/releasing.md).
