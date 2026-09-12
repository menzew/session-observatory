# Session Observatory

## 1. Decision and scope

One application can consolidate OpenAI identity activity, enrolled devices, Codex project usage, API consumption, and security alerts. It cannot independently discover every use of a personal ChatGPT credential. The recommended product is a monitoring and accounting application whose coverage is explicit for every account, workspace, device, and reporting period.

The two objectives require different evidence. Detecting credential misuse requires authentication, resource-access, endpoint, or gateway records. Assigning consumption to a project requires metering records and a reliable project mapping. A conversation identifier is useful for joining records; it is not a substitute for an authentication credential identifier.

The assessment covers personal subscriptions, ChatGPT Business, Enterprise/Edu, local and cloud Codex, API organizations, automation identities, and connected applications. The design below is a proposal, not a deployed monitor. Source-supported capabilities are cited; implementation choices and acceptance criteria are recommendations.

The recommended sequence is to deliver local Codex accounting first, add API usage reconciliation and gateway controls, then integrate eligible workspace security feeds. Personal accounts remain supported with an explicit limitation on remote credential-replay detection. No absence of alerts should be presented as proof that an account is safe.

## 2. Coverage by account and product

| Surface | Available foundation | Remote misuse visibility | Project accounting | Required qualification |
|---|---|---|---|---|
| Personal ChatGPT browser/mobile | Native Active Sessions; eligible account-security settings | Incomplete; no supported public account-wide replay feed established | Complete regular-chat token ledger not established | Native session list excludes several credential surfaces |
| Personal Codex on enrolled computers | Local usage records; configured telemetry | Activity on those computers only | Strong candidate for recorded local runs | Test each client/version and historical format |
| Personal Codex cloud tasks | Whatever supported account exports or task data are available | Complete feed not established | Conditional; local records alone are insufficient | Cloud consumption must stay unallocated when no reliable meter exists |
| ChatGPT Business | Workspace controls, eligible SSO, local collectors | Limited to connected evidence; do not assume Enterprise logs | Local Codex accounting; supported workspace reports if available | Business administration is not equivalent to compliance entitlement |
| ChatGPT Enterprise/Edu | Eligible compliance/authentication/app logs and workspace reports | Broader, but event coverage and replay observability need validation | Combine eligible provider reports with local project mappings | Separate workspace credentials, permissions, retention, and freshness |
| API organizations and projects | Usage API, Costs API, administrative audit records | Usage anomalies; audited events; detailed activity through an instrumented path | Strong with distinct keys/projects and explicit mappings | Aggregated usage does not identify an attacker's device |
| Codex automation | Eligible workspace service identities or API service identities | Depends on associated workspace/API and runner evidence | Stronger attribution when each workload has its own identity | Workspace and API identities have different access and billing |
| Third-party applications | Provider-specific consent and audit sources | Only the activity actually exported by each provider | Requires provider metering or a monitored API path | Installation, authorization, active use, and model billing are different facts |

The personal-session restriction follows OpenAI's documented exclusions. Business/Enterprise distinctions follow the current app-controls and compliance guidance. API accounting follows its separate usage interface. These sources do not establish complete remote-replay detection for every row. [1 · Active sessions](https://help.openai.com/en/articles/20001257-managing-active-sessions-in-chatgpt/) · [2 · App controls](https://help.openai.com/en/articles/11509118) · [3 · Compliance Platform](https://help.openai.com/en/articles/9261474-openai-compliance-platform-for-enterprise-and-edu-customers) · [4 · API usage](https://developers.openai.com/api/reference/ruby/resources/admin/subresources/organization/subresources/usage/methods/completions)

Every connection should expose separate states for **supported**, **connected**, **healthy**, and **validated**. A documented endpoint does not mean this installation has permission to call it. A connected collector does not mean all relevant devices are enrolled.

## 3. What a stolen credential can and cannot reveal

A bearer token permits use by whoever possesses it, subject to the receiving service's controls. OAuth security guidance distinguishes replay protection and sender constraints from the original login ceremony. Consequently, stronger sign-in authentication must not be advertised as a guarantee against replay of an already stolen bearer credential. This is a security inference from the bearer-token model, not a claim about undocumented OpenAI protections. [5 · RFC 6750](https://www.rfc-editor.org/info/rfc6750/) · [6 · RFC 9700](https://www.rfc-editor.org/info/rfc9700/)

For design purposes, consider seven distinct scenarios:

| Scenario | Best evidence | What remains uncertain |
|---|---|---|
| A new interactive login on an unfamiliar network | Provider authentication event plus identity-provider context | Travel, mobile networks, VPNs, and legitimate new devices |
| A copied access token used without a new login | Resource-access records with a useful credential/session join | A login-only feed may show nothing new |
| A stolen refresh credential used to obtain access | Provider token lifecycle or reuse events, if exposed | Public availability and semantics of these events are unverified |
| A copied API key used directly against OpenAI | Provider usage beyond known traffic; access restrictions | Aggregate usage alone does not reveal physical device or intent |
| Malware using the legitimate signed-in computer | Endpoint process/file-access evidence plus workload activity | The network and device may look entirely familiar |
| An authorized person or automation misusing access | Individual identities, project budgets, change and access records | A credential identifies an authority, not necessarily a human operator |
| The monitoring collector is disabled or falsified | Missing heartbeats, sequence gaps, remote ingestion history | A compromised device can forge telemetry while appearing healthy |

An unfamiliar country is a risk signal, not a verdict. Multiple simultaneous tasks are normal for Codex. A credential file changing can reflect ordinary refresh. A missing local usage record can reflect a second legitimate computer, cloud work, delayed writes, or a parser defect.

The product should state an alert's evidence precisely: “provider-reported usage exceeds known usage for this key and interval” is defensible. “Your session was stolen” requires stronger evidence and often investigation.

## 4. Personal ChatGPT and Codex

ChatGPT's native Active Sessions view can identify supported browser/app sessions and offer sign-out controls. It excludes Codex CLI, connected apps, third-party app sessions, and third-party-only Sign in with ChatGPT sessions. It is unavailable for accounts linked to organizational SSO. Its documented sign-out propagation can take up to 30 minutes. [1 · Active sessions](https://help.openai.com/en/articles/20001257-managing-active-sessions-in-chatgpt/)

Eligible consumer accounts can use Advanced Account Security. The documented changes include passkey/security-key sign-in, shorter sessions, and email login notifications, alongside significant recovery changes. That is an existing source of login notifications, not a documented feed of every access-token use. Enrollment should be a deliberate account-owner action. [7 · Advanced Account Security](https://help.openai.com/en/articles/20001221)

Codex documents local credential caching in a file or operating-system credential store. That makes protecting the endpoint relevant to the theft scenario. The accounting collector should not open authentication files: it needs usage records, not reusable secrets. A separate endpoint-security integration can report access to sensitive paths without exporting their contents. [8 · Codex authentication](https://learn.chatgpt.com/docs/auth)

Codex's supported OpenTelemetry export can provide run, request, streaming, and tool events, including token counts on completed responses. Export is opt-in. Disabling prompt logging does not guarantee that every event is free of content: tool-result snippets require separate filtering. Collect an allowlisted set of accounting fields and discard prompt/tool bodies before transmission. [9 · Advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)

**Recommended personal-account mode:** a local service reads usage from explicitly selected Codex homes; a desktop or browser interface shows project totals and local anomalies; optional enrolled machines send sanitized events to a private hub. Native account-security controls remain accessible from the dashboard. Unsupported account-wide security feeds appear as unavailable, not as a green status indicator.

A browser extension could observe authorized browser activity, but it would not cover other browsers, mobile apps, CLI activity, or an attacker elsewhere. Session-cookie scraping would introduce sensitive access and unstable dependencies without solving that coverage problem. It should not be the foundation of a security claim.

## 5. Business, Enterprise, Edu, and automation

Business should have its own capability profile. Current OpenAI guidance distinguishes Business workspace administration from Enterprise/Edu compliance access and does not grant Business administrators automatic visibility into members' ordinary private conversations. Local accounting and eligible identity-provider logs remain useful, but the app should enable enterprise feeds only after checking actual entitlement. [2 · App controls](https://help.openai.com/en/articles/11509118)

For eligible Enterprise/Edu workspaces, the Compliance Platform provides append-only logs and complementary stateful resources. Its current guide documents a 30-day log retention window and the removal of the older stateful conversation route on June 5, 2026. A new integration must use current log resources and persist collection cursors. Do not build on the removed conversation route. [3 · Compliance Platform](https://help.openai.com/en/articles/9261474-openai-compliance-platform-for-enterprise-and-edu-customers)

The Codex compliance guide explicitly demonstrates authentication-log collection and directs implementers to the Admin API reference for schemas and coverage. Authentication records are therefore a credible integration path, but exact fields such as source IP, user agent, session identifier, refresh activity, and resource-access linkage must be verified in the authorized schema and sample events. Do not invent them. [10 · Compliance API and audit events](https://learn.chatgpt.com/docs/enterprise/compliance-api)

There is a documentation conflict worth resolving before implementation. The Codex analytics overview still says a Platform organization API key authenticates analytics. The current Help Center instead specifies workspace-scoped Admin keys and explicitly says Platform organization keys do not grant workspace analytics access. Use the newer workspace-key instructions as the working setup, then confirm the canonical API contract and a least-privilege request. The public reference linked by both guides was not readable through the available research retrieval; this assessment therefore does not fabricate analytics routes or response fields. [11 · Analytics overview](https://learn.chatgpt.com/docs/enterprise/analytics-api) · [12 · Codex plan access](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan) · [13 · Admin keys](https://help.openai.com/en/articles/20001407)

Workspace Admin keys have a workspace boundary. Current guidance provides `codex.enterprise.analytics.read` for Codex analytics and separate read/write usage-limit permissions. Authentication/app-log access and broader content access have distinct role requirements. The monitoring service should request only needed read scopes, with no model-inference credential in the browser. [13 · Admin keys](https://help.openai.com/en/articles/20001407)

Eligible workspaces also have usage-limit and overage controls. These can constrain eligible consumption at user, group/default, and workspace levels, while alerts themselves do not stop use. Their units and billing scope differ from API token pricing. Model an alert threshold, an enforced limit, and a reported invoice as separate objects. [14 · Workspace usage controls](https://help.openai.com/en/articles/20001001)

There is already a useful built-in accounting surface for eligible Enterprise/Edu users: Desktop Usage & billing and Personal Analytics. Documentation describes Work/Codex credit and token views and locally available high-consuming chats. Regular Chat usage is excluded, and the top-chat list can rank lifetime totals for chats active within the selected recent period. An integration must preserve that difference between selection window and measurement window. [15 · Personal Analytics](https://help.openai.com/en/articles/20001478)

Automation should have identities separate from employees. Codex workspace service accounts are documented for pay-as-you-go plans, support scoped expiring tokens, and attribute runs to the service identity. They differ from API Platform project service accounts. A service account per workflow makes “release runner” distinguishable from “interactive developer,” but still does not identify who used a copied service token. [16 · Codex service accounts](https://learn.chatgpt.com/docs/enterprise/service-accounts)

## 6. API organizations and keys

The Usage API exposes model consumption grouped by project, user, API-key identifier, model, batch status, and service tier. The documented completion-usage interface supports minute, hour, and day buckets. Bucket size describes aggregation, not a guaranteed publication delay. Provider identifiers should remain namespaced by organization. [4 · API usage](https://developers.openai.com/api/reference/ruby/resources/admin/subresources/organization/subresources/usage/methods/completions)

The current Costs API documents daily buckets and grouping by project, line item, and API-key identifier. This is useful for reconciling charges, but its dimensions should not be assumed identical to the usage endpoint. Preserve currencies, time boundaries, and unallocated line items. [17 · Costs API](https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/usage/methods/costs)

Platform administrative audit schemas include login outcomes, API-key changes, and allowlist changes. A session actor may include an IP address; a key actor has key-identification fields. These are records of audited actions, not evidence that every inference request appears with its source IP. [18 · Audit-log schema](https://developers.openai.com/api/reference/typescript/__sdk_schema?declaration=%28resource%29+admin.organization.audit_logs+%3E+%28model%29+audit_log_list_response+%3E+%28schema%29&selected=%28resource%29+admin.organization.audit_logs)

The recommended API design assigns distinct provider keys or service identities to workloads, keeps upstream credentials server-side, and issues constrained gateway credentials to clients. Each gateway request gets an authenticated project mapping and an internal request identifier. Provider request/response identifiers should be retained when available. A client-supplied project label alone is not an accounting boundary.

Reconcile provider aggregates against gateway totals after a measured settling interval. A positive difference is unexplained consumption. Before escalating, account for direct authorized clients, retries, asynchronous jobs, missing terminal stream events, model aliases, clock boundaries, and late provider updates. Reconciliation should use comparable units and complete scopes, never percentages of a subscription allowance versus raw tokens.

## 7. Controls that reduce the value of a stolen key

OpenAI API IP allowlisting rejects requests outside approved network ranges even when they carry a valid API key. Project allowlists take precedence over organization lists rather than merging with them. The API guide describes propagation of up to 15 minutes and excludes Platform web sign-in from this control. [19 · API IP allowlists](https://developers.openai.com/api/docs/guides/ip-allowlist)

**Design recommendation:** keep upstream keys on a controlled gateway and restrict provider access to that gateway's egress addresses where available. This closes a common direct-bypass path for a stolen upstream key. It does not protect against compromise of the gateway, an allowed network, or another still-authorized route. Gateway-issued credentials also require authentication, expiry, limits, and revocation.

Enterprise/Edu ChatGPT has separately documented workspace and Compliance API network controls. The guidance covers major ChatGPT endpoints and distinguishes sign-in from loading workspace data. Validate each required Codex local/cloud and remote-control path before claiming equivalent enforcement across products. [20 · ChatGPT IP allowlists](https://help.openai.com/en/articles/12111596-ip-allowlisting-for-chatgpt/)

OpenAI also documents mutual TLS and workload identity federation. Federation exchanges an external workload identity for a short-lived OpenAI access token, reducing reliance on stored long-lived credentials. Mutual TLS adds certificate checks on its supported hosts. Neither should be claimed to constrain all alternative routes without testing enforcement and product eligibility. [21 · Workload identity federation](https://developers.openai.com/api/docs/guides/workload-identity-federation) · [22 · Mutual TLS](https://developers.openai.com/api/docs/guides/mutual-tls)

Identity-provider controls and endpoint protection are complementary. Identity logs can help identify unusual sign-ins; endpoint evidence can reveal a process reading credential storage. Neither establishes complete visibility into a remote bearer-token replay. Keep the dashboard's prevention, detection, and accounting coverage separate.

## 8. Connected apps and external sign-in

Three relationships must be represented separately: a plugin being installed, an app being authorized to access another service, and an external service accepting Sign in with ChatGPT. A connection to Google or Microsoft is not evidence that the provider holds the user's Codex login credential.

Eligible tenant controls can govern supported external Sign in with ChatGPT applications. Workspace app logs can, where supported, describe app requests/responses and connection/disconnection activity. Neither surface promises a complete audit trail inside the external service. [23 · Tenant administration](https://help.openai.com/en/articles/12289294-managing-your-tenant-in-admin-console) · [2 · App controls](https://help.openai.com/en/articles/11509118)

**Design recommendation:** each app integration declares whether it supplies installation inventory, authorization inventory, authentication events, action events, or billing. An installed app with no recent activity should appear as “authorized; activity unavailable” or “no activity observed in this feed,” not “unused.” Revocation must target the correct authority: the provider grant, the workspace permission, and any independently issued credential can require different actions.

## 9. An accounting model that survives real usage

The accounting unit should be an observed metering event or provider bucket, with its original source preserved. The reporting unit is a canonical project. A local folder, a Git repository, a ChatGPT Project, and an API Platform project are different entities that can map to that canonical project.

Use a versioned mapping table. A local mapping can start from a repository root or an explicitly selected folder; Git worktrees can roll up to a shared project. Strip embedded credentials from remote URLs before considering repository metadata. Keep ambiguous mappings in an Unallocated queue. For monorepos, allow subproject rules and explicit task assignment; do not silently guess from a directory basename.

Recommended identity dimensions are account, workspace or API organization, principal, credential metadata identifier, enrolled device, application, canonical project, conversation/task, execution, parent execution, model, reasoning/speed setting, and billing source. Fields can be unknown. Never substitute a task ID for a credential ID, or infer the same account from an email match alone.

The normalized usage event should include:

| Field group | Required design behavior |
|---|---|
| Provenance | Source, collector version, schema version, record identity, original timestamp, received timestamp |
| Identity | Namespaced account/workspace/organization and actor; device identity only when evidenced |
| Work attribution | Canonical project plus mapping method, confidence, and mapping version |
| Execution | Task, turn, response, parent execution, and attempt identifiers where available |
| Metering | Input, cached input, cache-write input, output, reasoning-output details, and native total |
| Billing | Provider credits, estimated monetary cost, provider-reported cost, currency, price version |
| Completeness | Final/provisional/partial, reporting interval, reconciliation state, missing dimensions |

Input, cached input, output, and reasoning-output fields need source-specific semantics. For a source where cached input is a subset of input and reasoning output is a subset of output, total tokens are input plus output. Adding the subset fields again inflates usage. If a provider exposes disjoint cache-write categories, use its documented adapter rules rather than a universal formula.

For example, an explicitly illustrative record with 100,000 input tokens, including 80,000 cached tokens, and 5,000 output tokens has 105,000 total tokens under those semantics. It does not have 185,000. An estimated model charge would price 20,000 uncached input, 80,000 cached input, and 5,000 output at the applicable rates. No current model prices are assumed here.

Subscription charges, purchased credits, contracted workspace usage, API line items, and an API-equivalent estimate must remain distinct. Allocate a fixed subscription fee only under a disclosed policy; a proportional allocation is a management estimate, not a provider bill for that project. Non-token charges such as tools or storage need their own line items.

Deduplicate repeated imports by source identity. When a local record, OTel event, gateway event, and provider report describe the same usage, select one accounting authority and use the others as evidence. Provider buckets generally cannot be deduplicated request-by-request; they reconcile a matching aggregate instead. Count actual additional requests from retries when metered, but never duplicate a request merely because two collectors observed it.

Forks and subagents require explicit ownership. Count a child execution once, assign it to the project actually evidenced, and offer an inclusive parent rollup separately from direct parent usage. Historical snapshots copied into a resumed or forked task must not become new spending. If request identity or fork lineage is missing, flag the uncertainty rather than presenting an exact total.

### Local feasibility evidence

A read-only sample of three local Codex session files from version 0.153.4 contained project-folder metadata and both response-level `token_usage_record` entries and cumulative `token_count` events. Response records included response, task, turn, and session identifiers plus detailed usage counters. Authentication files and browser cookies were not opened.

For two sampled files, summing unique response usage matched the latest cumulative event. The currently active file initially differed; a follow-up showed its last cumulative event matched a prefix of response records, with a newer response recorded afterward. This demonstrates a timing difference that a reconciler must handle. It does not validate every historical format, every client, cross-device deduplication, or invoice accuracy.

## 10. Alert rules and response behavior

The following rules are proposed product behavior. Each rule should be unavailable until its required evidence is connected and tested. Initial thresholds should be configured per account and workload, then tuned with observed legitimate activity.

| Rule | Required evidence | Initial response | False-positive controls |
|---|---|---|---|
| New authentication context | Provider/identity auth event with usable context | Notify and request recognition | Known VPNs, travel, new enrollment, confidence of geolocation |
| Suspicious cross-context credential use | Stable credential/session join and resource-access events | High-priority investigation | Confirm provider semantics; legitimate refresh and delegated jobs |
| Unexplained API consumption | Provider and monitored usage with aligned scope/units | Alert after reconciliation delay | Late buckets, direct approved clients, retries, missing streams |
| Usage surge | Historical project/key usage and complete recent interval | Budget warning; investigate if sustained | Minimum volume, scheduled jobs, known workload changes |
| Project budget threshold | Trustworthy project ledger and configured budget | Warn at configured levels | Distinguish estimate, credits, and actual provider cost |
| Unrecognized local credential access | Endpoint audit event with process identity | Investigate the process | Legitimate clients, credential managers, backup activity |
| Security-control change | Provider/admin audit event | Notify with before/after evidence | Approved change windows and operator identity |
| Monitor health failure | Heartbeats, ingestion errors, cursor state | Coverage warning | Maintenance windows, sleep/offline devices, retry state |
| Credential expiry approaching | Provider metadata or managed secret inventory | Notify owner | Rotated replacements and scoped retirement plans |
| Provider rejection after revocation | Test outcome from the intended authorization boundary | Mark that boundary verified | Propagation delay; independent token families remain separate |

Alerts should contain source evidence, affected scope, observation time, ingestion delay, rule version, severity, uncertainty, and next action. Use stable incident keys to group repeated signals. Acknowledgment records recognition, not proof of safety. Suppress unchanged repeat notifications; re-notify on worsening evidence or a configured unresolved-incident interval.

Notification delivery itself needs retries, deduplication, health reporting, and a test action. Desktop notifications can be the first channel; email or messaging destinations should be connected explicitly. The monitor must not send secrets or sensitive conversation bodies in an alert.

Default remediation is reviewable: open the relevant native security page, identify the affected key/device, and show the consequences of revocation. API write actions belong in a separate restricted component. Automatic revocation is appropriate only for an expressly configured policy with verified scope and recovery behavior.

Signing out browser sessions, revoking an API key, disabling a workspace service identity, and disconnecting a third-party grant are different actions. A single “log out everywhere” button must not imply that all credential types were invalidated. Show each action's status as requested, effective/verified, failed, or unverified.

## 11. Application architecture

Use a local service for endpoint collection and a web or desktop interface for review. A browser-only app cannot independently read Codex records across computers, monitor credential-file access, or keep administrative secrets safely separated from page code.

```text
Enrolled Codex devices ─── sanitized usage / heartbeats ───┐
API gateway ─────────────── request usage / policy events ┤
API organization feeds ─── usage / costs / audit events ──┤
Eligible workspace feeds ─ auth / app logs / analytics ───┤
Identity & endpoint tools ─ sign-in / process evidence ───┤
                                                        ▼
                                      Authenticated ingestion
                                                        ▼
                               Normalized records + provenance
                                         │              │
                                   Usage ledger    Security timeline
                                         │              │
                                   Reconciliation    Alert rules
                                         └──────┬───────┘
                                                ▼
                               Dashboard + notification outbox
                                                │
                                 Separate remediation service
```

A single-user deployment can keep records in a local database and listen only on loopback. Multiple computers need authenticated enrollment, encrypted transport, scoped device credentials, and a central service. Each collector should retain a bounded local queue during outages, send monotonic sequence numbers, and receive acknowledgment only after durable ingestion. Reinstalling or rotating a device identity must be an explicit lifecycle event.

A compromised enrolled device can still produce false records. Device certificates and signatures improve origin verification; they do not prove the truth of events emitted by compromised software. Stronger assurance comes from independent provider records and endpoint controls, with that trust difference visible to investigators.

Recommended screens are Overview, Devices, Accounts & Credentials, Projects, Security Timeline, Alerts, and Coverage. Overview should show what is connected and current before showing consumption totals. Devices should distinguish enrolled, reporting, stale, retired, and provider-observed-but-unmatched. “Active task” and “signed-in session” must be separate labels.

Projects should offer daily usage, direct/inclusive task rollups, source/model breakdowns, budgets, and an Unallocated queue. Every total should have a unit, period, completeness state, and explanation of how it was attributed. A downloadable report should include the mapping and pricing versions used to produce it.

Coverage is a first-class screen. Show each source's entitlement, permission check, last successful fetch, latest event time, expected delay, historical reach, missing dimensions, and validation date. Report separately how many declared devices are enrolled and how much provider-metered usage is explained. Do not manufacture a percentage for unseen activity when no denominator exists.

## 12. Protecting the monitor

The monitor consolidates sensitive metadata and may hold powerful read credentials. Keep it outside repositories routinely edited by agents where practical. Store connection secrets in an operating-system credential store or server secret manager. Serve only redacted credential metadata to the interface. Prefer provider tracking IDs over reading or hashing raw credentials.

Use metadata-only collection by default. Local session files may contain full conversations, tool output, and instructions even when only a few accounting fields are needed. Parse only allowlisted records and avoid retaining the original content. Treat project names, repository URLs, event text, and logs as untrusted display data: escape them and never execute instructions found inside them.

The local web service needs authenticated access and protections against hostile websites reaching loopback endpoints. Do not enable permissive cross-origin access. For a shared deployment, apply workspace isolation, role-based views, encrypted backups, scoped ingestion credentials, and audited administrative changes.

Keep finance access separate from content-investigation access. A project owner can see consumption without reading other people's conversations. Keep raw compliance content out of routine accounting exports. Set explicit retention for metadata, incident evidence, and raw ingestion buffers, and provide deletion and backup behavior appropriate to the deployment.

No centralized collector should require users to paste ChatGPT session cookies into it. If an optional integration genuinely needs a reusable secret, identify the credential type and authority, explain its access, and store it through a secure connection flow. It must not be confused with harmless task identifiers.

## 13. Existing tools and the build decision

| Option | Documented fit | Assessment for this requirement |
|---|---|---|
| ccusage | Reads local agent usage files; daily/session reports and estimated costs | Useful accounting component and comparison tool; cannot observe remote stolen-key activity from local files alone |
| CodexBar | Provider usage windows, credits/spend views, and local cost scans; macOS UI and Linux CLI builds | Useful personal usage display; its documented sources do not establish complete theft detection |
| LiteLLM gateway | Virtual keys and spend tracking by key/user/team, with budget controls | Candidate API enforcement layer; covers routed traffic, not every personal ChatGPT session |
| OpenAI native controls | Session review, eligible account security, workspace usage/security controls | Keep as authoritative controls within each documented scope |
| Existing enterprise security system | Compliance integration ecosystem documented by OpenAI | Reuse an existing approved deployment for investigations; validate the exact integration instead of assuming partner status guarantees coverage |

These comparisons are based on project documentation, not installation tests or a security certification. No reviewed source establishes an off-the-shelf application satisfying every requested surface. [24 · ccusage](https://ccusage.com/guide/) · [25 · CodexBar](https://github.com/steipete/CodexBar) · [26 · LiteLLM virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys) · [3 · Compliance integrations](https://help.openai.com/en/articles/9261474-openai-compliance-platform-for-enterprise-and-edu-customers)

The best build boundary is a unifying dashboard, source adapters, project mapping, accounting reconciliation, and evidence-based alerting. Reuse established gateways and security feeds where appropriate. Do not rebuild identity-provider risk detection or make browser-cookie scraping a mandatory dependency. Each reused component needs a pinned version, permission review, and integration test before receiving credentials.

## 14. Delivery stages and acceptance criteria

**Stage 1 — Local accounting.** Read selected Codex records without authentication-file access. Deliver project/task breakdowns, direct and child usage, time filters, unallocated records, CSV export, and local budget warnings. Release only when duplicates, restarts, forks, partial writes, time-boundary crossings, and changing counters are handled. This stage does not claim remote theft detection.

**Stage 2 — Multiple devices and API accounting.** Add authenticated enrollment and resumable ingestion. Connect API usage/cost feeds and reconcile with local or gateway evidence. Show provider totals and explained/unexplained consumption separately. Verify that an unknown device cannot enroll itself and that repeated imports do not increase totals.

**Stage 3 — API access protection.** Integrate a monitored gateway with separate project/workload credentials and supported provider network restrictions. Test permitted and denied routes in an isolated environment, including alternate hosts and project overrides. Confirm that budget behavior during streaming, concurrency, and database failure matches the product's claims.

**Stage 4 — Managed-workspace security.** Connect eligible authentication, audit, and app logs, plus authorized analytics. Verify source schemas, entitlement, permission scopes, identity joins, retention, pagination, publication delay, and coverage of Codex local/cloud. Use test events to establish whether replay without interactive login produces useful evidence. If it does not, retain that explicit blind spot.

**Stage 5 — Incident operations.** Add notification channels, tested revocation actions, investigator views, exports, retention, and recovery exercises. Validate that a collector outage generates a coverage alert and that account administration remains possible if the monitoring service fails.

Proposed latency targets apply after evidence reaches the service: process and evaluate ordinary events within 30 seconds at the 95th percentile, with retries and backlog visibility. These are design targets, not measured performance or provider guarantees. Total detection time also includes provider publication delay, polling, ingestion, and notification delivery.

Essential validation scenarios include:

1. A legitimate new laptop produces an enrollment event without a theft verdict.
2. A VPN location change does not trigger automatic account revocation.
3. Two collectors import the same response without double-counting it.
4. A fork includes inherited history without charging that history again.
5. A child task is counted once and appears correctly in both direct and inclusive views.
6. A cumulative snapshot trails response usage without generating unexplained-spend alerts.
7. A broken stream leaves provisional usage until reliable metering arrives.
8. A provider bucket is revised and updates the ledger rather than appending duplicate usage.
9. Currency, credits, subscription fees, and token estimates cannot be summed accidentally.
10. A permitted gateway request succeeds and a disallowed-network request is rejected after propagation.
11. A replay-style test using a dedicated test identity establishes what the provider logs actually reveal, without copying production credentials.
12. A collector is offline while provider usage grows; the UI explains both the coverage gap and the accounting discrepancy.
13. A workspace permission is revoked; collection becomes visibly degraded rather than silently empty.
14. A notification destination fails; delivery retries and failure status remain visible.
15. Every supported revocation action has a verified scope and an independently checked result.

## 15. Remaining uncertainty and evidence quality

The key unresolved item is not dashboard implementation. It is whether each supported account can export resource-use evidence sufficient to detect stolen credentials used outside enrolled infrastructure. The available personal-account documentation does not establish such a complete feed. Enterprise authentication logs are promising, but must be inspected for event fields and replay coverage before a detection guarantee is made.

Additional qualification items are regular Chat token metering, cloud Codex project attribution, analytics authentication/schema conflicts, third-party token lifecycle visibility, cross-client local format compatibility, source-IP availability for inference requests, and enforcement across alternate API/Codex routes. A connector should retain the evidence and date supporting each capability claim.

Evidence was checked on 9 September 2026. Official OpenAI pages establish product capabilities; IETF standards support the security model; upstream project documentation supports the tool comparison. Local inspection was limited to three files and cannot establish global accounting completeness. No production credentials, account settings, network restrictions, notification destinations, or installed applications were changed.

The report is an implementation blueprint and feasibility assessment. Delivering the monitoring service and validating authorized provider connections are separate work. The defensible product promise is: **show observed activity, explain consumption, alert on supported evidence, and make every monitoring gap visible.**

## Sources

All web sources were consulted on 9 September 2026. Dates are omitted where a stable publication date was not established.

1. OpenAI. [Managing active sessions in ChatGPT](https://help.openai.com/en/articles/20001257-managing-active-sessions-in-chatgpt/). Session visibility, exclusions, SSO restriction, sign-out timing.
2. OpenAI. [Admin controls, security, and compliance for plugins and apps](https://help.openai.com/en/articles/11509118). Business versus Enterprise/Edu access and app-log coverage.
3. OpenAI. [Compliance Platform for Enterprise and Edu Customers](https://help.openai.com/en/articles/9261474-openai-compliance-platform-for-enterprise-and-edu-customers). Eligibility, retention, conversation-route migration, integration ecosystem.
4. OpenAI. [Organization completion usage](https://developers.openai.com/api/reference/ruby/resources/admin/subresources/organization/subresources/usage/methods/completions). Metering dimensions and aggregation windows.
5. M. Jones and D. Hardt, IETF. [RFC 6750: OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/info/rfc6750/), October 2012. Bearer-token security model.
6. T. Lodderstedt, J. Bradley, A. Labunets, and D. Fett, IETF. [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/info/rfc9700/), January 2025. Replay threats and OAuth countermeasures; not evidence of OpenAI implementation details.
7. OpenAI. [Advanced Account Security](https://help.openai.com/en/articles/20001221). Eligible consumer protections and login notifications.
8. OpenAI. [Codex authentication](https://learn.chatgpt.com/docs/auth). Credential storage and local authentication behavior.
9. OpenAI. [Advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced). OTel event export and privacy considerations.
10. OpenAI. [Compliance API and audit events](https://learn.chatgpt.com/docs/enterprise/compliance-api). Authentication-log integration and schema authority.
11. OpenAI. [Analytics API overview](https://learn.chatgpt.com/docs/enterprise/analytics-api). Aggregated reporting; credential guidance conflicts with sources 12–13.
12. OpenAI. [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan). Enterprise analytics eligibility and workspace Admin-key guidance.
13. OpenAI. [Managing Admin keys in Admin Console](https://help.openai.com/en/articles/20001407). Workspace scope, role requirements, permissions, and separation from Platform keys.
14. OpenAI. [Manage usage limits and overages](https://help.openai.com/en/articles/20001001). Eligible workspace limits, credits, alerts, and billing distinctions.
15. OpenAI. [Reviewing Work and Codex usage and using Personal Analytics](https://help.openai.com/en/articles/20001478). Eligible desktop accounting views and measurement-window caveats.
16. OpenAI. [Codex service accounts](https://learn.chatgpt.com/docs/enterprise/service-accounts). Automation identity, plan condition, and token lifecycle.
17. OpenAI. [Organization Costs API](https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/usage/methods/costs). Daily costs and supported grouping.
18. OpenAI. [Organization audit-log response schema](https://developers.openai.com/api/reference/typescript/__sdk_schema?declaration=%28resource%29+admin.organization.audit_logs+%3E+%28model%29+audit_log_list_response+%3E+%28schema%29&selected=%28resource%29+admin.organization.audit_logs). Audited event types and actor metadata.
19. OpenAI. [API IP allowlist](https://developers.openai.com/api/docs/guides/ip-allowlist). Provider-side network enforcement and scope precedence.
20. OpenAI. [IP allowlisting for ChatGPT](https://help.openai.com/en/articles/12111596-ip-allowlisting-for-chatgpt/). Enterprise/Edu workspace and compliance network controls.
21. OpenAI. [Workload identity federation](https://developers.openai.com/api/docs/guides/workload-identity-federation). External workload identity and short-lived access.
22. OpenAI. [Mutual TLS](https://developers.openai.com/api/docs/guides/mutual-tls). Certificate authentication on supported API hosts.
23. OpenAI. [Managing your tenant in Admin Console](https://help.openai.com/en/articles/12289294-managing-your-tenant-in-admin-console). External sign-in controls and administration boundaries.
24. ccusage maintainers. [Introduction](https://ccusage.com/guide/). Local usage analysis and documented limitations.
25. CodexBar maintainers. [CodexBar repository](https://github.com/steipete/CodexBar). Usage-monitoring features, platforms, and credential-access considerations.
26. LiteLLM maintainers. [Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys). Gateway identities, spend tracking, and budget integration.
27. OpenAI. [Public Admin API reference](https://chatgpt.com/public/admin/api-reference). Linked canonical contract; not readable through the available retrieval, so no unverified endpoint schemas were inferred from it.
