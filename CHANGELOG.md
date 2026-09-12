# Changelog

## Unreleased

- Reorganize documentation around browser use, with dedicated privacy and optional collector guides, explicit storage/deletion boundaries, and backup/migration instructions.

- Clarify the source checkout and browser download setup paths.
- Reject additional credential formats, image metadata matches, local agent files and SQLite sidecars in public releases.
- Enforce the public file allowlist for tracked files in CI and test the extracted source archive.
- Derive source archive versions from package metadata and preserve existing checksums.
- Keep background refreshes from canceling pending table sorts and other user updates.

## Browser-only release candidate

- Self-contained local HTML with no Python installation, server, CDN or runtime network access.
- Shared accounting engine in a bundled WebAssembly worker; existing analytics, costs, limits and audit rules retained.
- Manual multi-folder import with relative source provenance, explicit browser saving, complete backups, migration, restore validation and stale-tab save protection.
- Memory-only default, clear privacy/storage status, offline browser tests and bundled runtime license notices.

## 0.1.0 — initial source release candidate

- Local Codex usage collection with configurable sources and response deduplication.
- Searchable, sortable ledger, task attribution and evidence exports.
- Consumption analytics with model/time breakdowns and exact drill-down filters.
- Historical source-reported quota observations.
- API cost what-ifs with a clear current/alternative comparison, progressive controls, cost composition, partial coverage and decimal exports.
- Provider and normalized activity imports with local policy review alerts.
- In-memory synthetic demo, standalone browser tests, CI, release allowlist, and Apache-2.0 licensing.

API text-token prices are a snapshot checked on 2026-09-09. This is local accounting and imported-evidence analysis; it has no live account-wide stolen-session detection or model router.
