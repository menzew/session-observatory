# Product scope

Session Observatory helps a person understand their Codex usage from evidence they already have. The primary experience is a local HTML file: choose logs, explore usage and hypothetical API costs, inspect provenance, and decide whether to keep a workspace.

## Core workflow

Import selected evidence → identify a project, model, or task → inspect its records → declare responsibility or purpose → compare explicit cost assumptions → save or export deliberately.

The browser edition needs no installation, account connection, API key, server, or runtime network access. It has no automatic filesystem watcher. The optional Python collector provides scheduled folder rescanning and automatic SQLite persistence for users who need that workflow.

## Product commitments

- Make storage choices visible: memory only, unsaved changes, explicit Save, complete backup, restore, and Forget.
- Explain privacy precisely. Selected logs are read in memory; the ledger retains accounting metadata rather than conversation bodies. Metadata and exports remain potentially private.
- Preserve original metering, prevent double counting, retain revision history, and expose missing or conflicting evidence.
- Distinguish observed facts from declarations. Task identifiers and local operator labels are not credentials or verified login identities.
- Present API prices as dated, hypothetical text-token rates. Do not equate subscription usage with an API invoice.
- Keep coverage explicit. Historical limit observations and imported activity do not constitute live account-wide security monitoring.

The [privacy document](PRIVACY.md) defines the data boundary. The [user guide](GUIDE.md) defines accounting and import behavior. [Research proposals](docs/RESEARCH.md) describe possible future integrations, not shipped capabilities.
