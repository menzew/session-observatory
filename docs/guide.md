# User guide and evidence formats

This guide covers the ledger, attribution, accounting rules, and import contracts shared by both editions. Start with the [browser walkthrough](browser.md) to open the app and import your first files. Read [Privacy and your data](../PRIVACY.md) before saving or sharing a workspace. Automatic scanning and server setup belong to the optional [collector guide](collector.md).

The browser edition processes only selected evidence and refreshes when you re-import it. The collector reads configured folders on a schedule. Both use the same accounting engine; neither connects to an OpenAI account or makes model API calls.

## A first investigation

1. Import a log folder or choose **Try fictional demo** in an empty browser workspace.
2. Open **Consumption analysis**, choose a period, and inspect the largest projects or models.
3. Select a group to narrow the view, then open the matching ledger records and their source references.
4. Declare a responsible person or purpose when you know it; declarations supplement the original evidence.
5. Open **Cost analysis** to compare the selected workload under explicit API pricing assumptions.
6. Save the browser workspace or download a complete backup if you want to retain changes. Treat exports as private metadata.

Observed usage is limited to the evidence available. Historical quota readings are not live balances, and activity alerts are local review signals rather than complete account-wide monitoring.

## What you can do

- **Usage ledger:** filter by period, custom UTC dates, project, free-text search, or response/legacy evidence; sort and page through records; export every filtered record as CSV.
- **Limits & cycles:** inspect historical Pro (or all reported plans) quota readings, including percentage used, source-reported window duration and reset time. Filter by observation period, source or task. The latest reading retains its timestamp, task and source; it is never presented as a live account balance.
- **Evidence drawer:** inspect all available counts and identifiers, task lineage, model, client, working directory, Git branch/commit, collector identity, source timestamp, source path/line and SHA-256, first observation, conflicting evidence, and attribution history. Download the full record as JSON.
- **Projects:** compare included usage per source directory or declared project; set daily/monthly UTC token budgets. Alerts begin at 80% and escalate at 100%. An acknowledged warning reopens on escalation. Budgets do not stop requests.
- **Consumption analysis:** interactive share donuts, ranked consumers, stacked usage trends, token composition, weekday/hour heatmap, and native response-size distribution. Drill through project → model → task → matching evidence, or group by person, purpose, application, device, source folder, branch, evidence type or date. Switch the chart measure between token components and record counts. Cards, charts, paginated sortable groups and CSV exports retain the same filters. See [analytics definitions and exploration](analytics.md).
- **Cost analysis:** offline API what-ifs for model mix, processing tier, cache reuse, workload repetitions, input/output size and custom rates. Compare costs by project, model, task or other dimensions, save assumptions, and export exact scenario calculations. Missing prices stay visibly unpriced; differences use only comparable coverage. See [cost assumptions and rate sources](costs.md).
- **Accountability:** declare project, responsible person/workload, and purpose for one record or all currently indexed included records in the same task. Every change requires a reason and creates a separate audit entry. Bulk attribution replaces existing declarations on those records and does not automatically apply to future records or child tasks.
- **Provider records:** import completion-usage and Costs API export pages, preserving their declared account scope, native dimensions, interval, units, and revisions. The interface shows the first 1,000 buckets in the selected column order; full evidence export includes all of them.
- **Activity and alerts:** import normalized activity, declare approved device names and IP/CIDR networks per exact account label, and flag policy mismatches or missing evidence. Policy changes recheck historical imports; existing alerts remain as history. A mismatch is a review signal, not proof of theft. There is no automatic trusted-device baseline.
- **Sources & privacy (browser):** choose files, review import notices, save a snapshot, download a complete backup, restore evidence, or forget the workspace.
- **Sources & coverage (collector):** configure automatic sources, map paths accessible to the server, and inspect availability and scan progress. **Export complete evidence** downloads all normalized tables, including excluded records, conflicts, provider buckets, activity, policies, budgets, and the audit chain.

## Sorting and historical subscription limits

Click any table heading to sort ascending; click again to reverse. Arrows and accessible header states show the active order. Ledger, consumption groups, provider buckets, activity and limit history are sorted across all matching data before their display limit or pagination. Empty values sort last in both directions. Combined columns sort their main field (for example, project path, person, or period start); window columns sort percentage used. Provider values are grouped by kind and currency before sorting total tokens or exact decimal costs. The filtered ledger CSV follows the ledger column order. Each view retains its chosen order while navigating or refreshing in the open page.

Quota readings are collected from Codex `event_msg` / `token_count` records with `rate_limits`, including records where `info` is null. Re-import files in the browser edition to add newly supported limit evidence. The collector can backfill reachable files without recounting token usage; previously imported files must be imported again if their bodies are no longer available. Readings retain normalized source fields and file/line/hash provenance in `limit_snapshots`; full evidence export includes them. Identical readings from the same source line deduplicate. Copies in different files preserve separate observations and are never summed.

The record drawer finds the last reading at or before that response in the same observed source file and task, respecting both timestamp and physical line order. It reports the time gap. A later reading is not assigned to an earlier response. If the reset preceded the record, its quota position remains unknown. This association is context only: it does not establish which request consumed a particular percentage, validate account identity, or reconstruct missing readings.

OpenAI describes usage percentage, quota-window duration and reset time in its [app-server documentation](https://learn.chatgpt.com/docs/app-server). Window names are not fixed durations: a primary window may be weekly, and an absent secondary window is not zero usage. Expired reset times are labeled explicitly. The display does not infer a billing-cycle start, monthly subscription budget, token-to-percentage conversion, or separate account identities from source paths. The Pro filter uses the source-reported plan. Quota readings currently come from saved logs; no live authenticated limit endpoint is connected.

## Who / what / when / where / why

| Question | Observed or declared evidence | What it does not establish |
|---|---|---|
| Who | Source actor when supplied; OS user for local collection; unverified browser operator for browser changes; optional declared responsible person/workload | Verified human behind a request, provider billing identity, or separate browser-user authentication |
| What | Model response or legacy snapshot delta; model, client, task/turn/response IDs, token counts | Per-tool or per-file token allocation within a response |
| When | Source timestamp, normalized UTC accounting timestamp, ingestion time, attribution-change time | Independently verified clock accuracy or full request latency |
| Where | Source working directory, collector hostname, branch/commit when present; device/IP in imported activity | A verified remote execution host, request egress IP, or location inferred from a local log |
| Why | Explicit purpose declaration with change reason and audit history | Automatically inferred intent, justification, or a claim that prompt text proves purpose |

Session metadata ID, execution session ID, source task ID, parent task, root turn, turn ID, and response ID are separate fields when the source supplies them. Missing identifiers stay unavailable. Selected files are read into memory, but the parser retains supported metadata rather than prompt bodies or tool arguments/results. Text entered in retained metadata fields is not automatically scrubbed; do not put credentials or private conversation text into declarations. See the [retention boundary](../PRIVACY.md#what-the-ledger-retains).

## Accounting rules and uncertainty

1. A native response ID plus provider identifies one metering event across copied/forked logs. Each matching observation retains its path, physical line number, and source-line hash. Conflicting counts are stored separately and trigger an alert; the first observed counts remain in the ledger pending review.
2. Native response records take precedence over legacy cumulative snapshots. Snapshots are never added to native response totals for the same task. When a partial native history replaces snapshots, the result may be incomplete; the app does not invent a balancing record.
3. Without native response records, non-decreasing cumulative snapshots yield labeled deltas. Identical legacy snapshots for the same task are deduplicated across copies. Decreasing or invalid counters produce source notices. Legacy child/fork counters are excluded because they may contain inherited usage. Unrecognized lineage or differently rewritten logs cannot always be deduplicated with certainty.
4. Input and output counts are required. Total is input plus output. Cached input and cache-write input are subsets of input; reasoning is a subset of output. Subsets are not added again. Missing optional counters normalize to zero for arithmetic; newly indexed native evidence records the fields actually reported and displays unavailable counters as **Not reported**. A snapshot delta remains a derived observation, not a provider request ID.
5. Records larger than 16 MB and incomplete final lines are skipped with notices. Unknown log types are ignored. Changed files are read again when re-imported in the browser or on the next collector scan. Existing evidence is retained if a source disappears; absence/deletion is not a negative usage adjustment.
6. “Observed tokens” is the sum of included indexed metering evidence. “Exact” means the unrounded integer sum, not guaranteed complete or invoice-accurate account consumption. Source quality and account coverage must be considered separately.
7. Provider buckets are a separate accounting layer. Alternative dimension groupings and overlapping intervals are never summed into local totals or presented as reconciled. An identical scope/kind/interval/dimension import is idempotent; a changed value revises the bucket and preserves the prior value in the audit log.
8. Monetary amounts retain decimal precision and their currency. The app does not invent prices for subscription tokens, convert currencies, or treat ChatGPT subscription usage as API spend. Non-token usage categories are rejected rather than converted.
9. All date filters and budgets use UTC. Custom “through” dates include that entire UTC day; the accounting engine applies an exclusive next-day endpoint. Future-dated usage does not count toward the current budget.

## Import formats

Use **Import records** in either edition, or **Import one evidence file** on the browser privacy page. Evidence imports accept local text files up to 30 MB. The collector also has a 36 MB encoded HTTP request limit, so heavily escaped Unicode content can need smaller chunks. Source content is hashed for provenance; only supported metadata is retained in the ledger. Do not import authentication files, cookies, access/refresh tokens, or credential values. `session_id` and `credential_id` below mean **non-secret identifiers**, never reusable credentials.

### Codex JSONL

Import an existing rollout file. The parser recognizes `session_meta`, `turn_context`, `token_usage_record`, and `event_msg` / `token_count`. Each physical JSONL line must end with a newline. Copied files are matched by response identity. Imported logs do not establish an account, operator, or device identity.

### OpenAI completion-usage export page

Provide an API response page already exported by an authorized operator, with `data[].start_time`, `end_time`, and `results[]`. This app does not obtain an API key or fetch the page. The account/workspace label is required and is declared by you.

```json
{
  "data": [{
    "start_time": 1788825600,
    "end_time": 1788912000,
    "results": [{
      "object": "organization.usage.completions.result",
      "project_id": "example-project",
      "api_key_id": "example-key-id-not-the-key",
      "user_id": "example-user",
      "model": "example-model",
      "input_tokens": 1000,
      "input_cached_tokens": 400,
      "output_tokens": 200,
      "num_model_requests": 2
    }]
  }],
  "has_more": false
}
```

Native `batch`, `service_tier`, and `line_item` dimensions are also preserved when present. `has_more: true` creates a completeness warning; import all required pages. The app cannot prove that your export contains every page or every required interval. Completion, cost, activity, and Codex imports are distinct evidence types.

For Costs pages, each result uses this shape inside the same bucket envelope:

```json
{
  "object": "organization.costs.result",
  "project_id": "example-project",
  "line_item": "example-line-item",
  "amount": {"value": "0.00123456789", "currency": "usd"}
}
```

### Normalized activity

This is **the app's import contract**, not an assertion about an OpenAI Compliance API schema. Normalize authorized exports from your provider, identity system, device agent, or gateway to this format. Keep an evidence reference to the original source. Up to 10,000 events per import:

```json
{
  "schema": "observatory.activity.v1",
  "events": [{
    "id": "stable-source-event-id",
    "timestamp": "2026-09-09T10:15:00Z",
    "actor": "person-or-service-id",
    "action": "session.used",
    "device": "my-laptop",
    "ip_address": "192.0.2.5",
    "application": "Codex CLI",
    "session_id": "non-secret-session-identifier",
    "credential_id": "non-secret-key-identifier",
    "project": "Release",
    "purpose": "Run release checks",
    "evidence_ref": "export-file/event-id"
  }]
}
```

Only `id`, timezone-aware `timestamp`, and `action` are required. Missing optional evidence stays unknown. The account label scopes identities and policy evaluation. An identical event ID in the same scope is idempotent; conflicting activity evidence rejects the entire import atomically. Exact device names are case-sensitive. Network checks support IPv4, IPv6, and CIDR notation. Approved lists are declarations, not authenticated provider settings, and do not configure provider IP allowlisting.

## Storage and audit

In the browser edition, evidence is held in memory until **Save in this browser** writes a snapshot. Named saved cost assumptions are part of that workspace and its complete backup. Reloading loses changes since the last Save. The collector instead persists evidence automatically in SQLite and stores cost assumptions separately in browser localStorage. See [browser saving](browser.md#save-or-make-a-backup), [collector backups](collector.md#storage-and-backups), and the full [privacy explanation](../PRIVACY.md).

Attributions supplement original observations. Changes, imports, policies, budgets, and acknowledgements record an operator label, UTC time, target, reason, before/after data, and a chained SHA-256 hash. The browser operator is explicitly unverified; a local collector's OS username is not proof of provider account identity. The integrity check detects inconsistencies but cannot prevent an operator from rewriting the database and chain. There is no external signature or independent checkpoint.

A complete backup/export includes every evidence table, including excluded records and audit history; it is not narrowed by view filters. The browser's **Download complete backup** also includes named saved cost assumptions. The collector's **Export complete evidence** can be restored in the browser, but does not include the collector origin's saved cost assumptions. Neither contains the original log bodies. Keep those separately if you may need to re-parse them.

CSV formula protection and source-text escaping reduce risks when viewing imported text. They do not anonymize exports. Use synthetic data for public reports and screenshots.

## Validation

The shared engine is tested with temporary databases and synthetic evidence for deduplication, conflicting counts, inherited history, source filtering, exact totals, attribution, audit integrity, budgets, pricing, provider revisions, and atomic imports.

The offline browser suite opens the HTML directly with networking disabled and tests imports, charts, saving, backups, restore, forgetting, migration, and zero HTTP requests. The collector browser suite uses its own temporary database and loopback server. Neither suite needs your real logs. Commands and the code map are in [Contributing](../CONTRIBUTING.md).

## Provider connections still needed for broader coverage

- Authenticated collectors on other computers with reliable device and workload identity.
- Authorized live API Usage/Costs polling and verified organization/project/key mappings.
- Eligible Enterprise/Edu compliance, authentication, application and analytics feeds, using verified current schemas.
- Gateway or provider controls for request provenance and enforcement; an attacker using a stolen key outside an optional gateway cannot be observed by that gateway alone.
- Authenticated alert delivery that remains available when this browser and computer are closed.

Personal ChatGPT, Business workspaces, Enterprise/Edu, and API organizations do not expose identical evidence. Nothing in this release treats a local Codex task ID as a login credential or claims visibility into all uses of a personal bearer session.
