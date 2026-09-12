# Consumption analysis

The existing local app provides live queries over its indexed accounting evidence. It does not call a remote analytics service or publish any data.

These views work in both editions. In the browser edition, they reflect the evidence you have imported; re-select a folder to refresh it. Charts and CSV exports can reveal private project names and source metadata. Use the fictional demo for shared screenshots and read the [export privacy guidance](PRIVACY.md#backups-sharing-and-deletion).

## Explore

1. Choose the period and evidence type. Search or keep the complete selection.
2. Choose a breakdown: project, model, task, person/workload, purpose, application, collector device, source folder, Git branch, evidence type or UTC day.
3. Choose a measure: total, input, cached input, uncached input, output, reasoning output, cache write, or metering-record count.
4. Click a share-chart slice, legend entry, ranked consumer or group name to filter to that exact category. Project drill-down continues to models, then tasks, then dates. Filters accumulate and remain visible as removable chips. **Back one level** restores the preceding drill-down selection.
5. The usage timeline defaults to model stacks. Hover a segment for its model and exact quantity; click it to focus on that model and interval. Click a model legend entry to focus on that model across the period. **Split by → Token type** restores the token-composition view. Click a timeline interval, a weekday/hour heatmap cell, or a response-size band to narrow the selection further. Changing the global period replaces any timeline focus. Removing a size filter restores the evidence type used before that size filter.
6. **Open matching records** carries the same selection into the ledger. Open a large metering record to inspect its evidence, ownership declarations and available quota context. CSV exports include all matching individual records, independently of the group table's page.

## Definitions and reconciliation

The source is SQLite `events`, joined once to its optional `attribution` row by event ID. Every query starts with `events.excluded=0`, preserving the collector's native-response deduplication and legacy-counter exclusions. The same `Ledger.filters()` predicates apply to summaries, charts, groups, underlying records and exports. Exact drill-downs use allowlisted dimensions and parameterized equality conditions, rather than free-text matches.

- **Observed total:** input plus output across the selected included metering records. Native responses and legacy snapshot deltas may coexist; the evidence filter separates them.
- **Token mix:** uncached input (`input - cached input`), cached input, and output form disjoint segments whose sum equals total. Reasoning is an output subset. Cache writes are an input subset; they are not added as another segment.
- **Reported cache share:** summed cached input divided by summed input, rather than an average of per-record percentages. Missing optional fields contribute zero, so this is the reported share rather than a verified efficiency or savings rate. A zero denominator renders unavailable.
- **Purpose coverage:** tokens without a nonempty declared purpose divided by all selected total tokens. This uses token weight, not record count. It does not infer intent from prompts.
- **Group share:** that group's selected measure divided by the same measure across every matching record. The pie shows five leading groups plus the exact sum of all remaining groups. It includes groups beyond the table's current page. A zero total has no percentage share.
- **Ranking:** the ten largest groups by the selected measure, independently of table sorting. Group rows retain all token components, counts, shares and weighted cache share. They are sorted over the complete result set and paginated in groups of 50.
- **Usage timeline:** every model contributes a separate series, with no top-model truncation. Model series sum to the selected measure in every interval and retain the same period and drill-down predicates. Colors are derived from the model name and remain stable when filters or measures change. The alternative token-type view retains the same total. All selected consumption is grouped into at most 90 consecutive intervals. Short periods show daily buckets; longer periods use labeled multi-day intervals. Empty intervals indicate no indexed consumption. Interval endpoints and drill-down filters are explicit and end-exclusive, including partial first/last intervals.
- **Heatmap:** the selected measure summed by UTC weekday and hour. Hour/day filters apply together when a cell is selected. It is a usage profile across the selected period, not a calendar of independently verified account access.
- **Response sizes:** native response records only. Bands are `[0, 1000)`, `[1000, 10000)`, `[10000, 100000)`, `[100000, 1000000)`, and `[1000000, ∞)` total tokens. Average is the arithmetic mean, median averages the middle two observations for an even count, and P95 uses the nearest rank. Legacy deltas do not establish individual response sizes.
- **Largest records:** the ten largest individual included metering records by total tokens, with granularity displayed. This section keeps that measure even when the chart selector is set to a token subset or record count.
- **Period comparison:** the selected chart measure compared with the immediately preceding interval of equal elapsed duration, with the same non-date predicates. The current interval ends at the query timestamp unless an explicit end is supplied. Both intervals can be partially observed. No percentage change is calculated from a zero baseline. All recorded time has no baseline. Exact dates appear in the definitions disclosure.

Charts and group shares reconcile to the analytics summary. Response-size counts reconcile to the native-response count, rather than to all metering records. Task counts across groups need not sum to unique tasks overall: a task can use multiple models or span dates. Top-record lists are bounded inspection aids, not another total.

## Limits of interpretation

These analytics describe collected evidence, not complete account usage or a provider invoice. Unavailable Windows folders, unconnected remote devices, missing records and optional metering fields affect coverage. Persons can be locally declared or collector users; device and folder fields do not authenticate the remote execution host. Provider costs, imported activity and subscription quota readings remain separate evidence layers. Token counts do not establish monetary cost, cache savings, security incidents or the reason work was performed.

Implementation: `analytics.py`, `Ledger.filters()` in `ledger.py`, and `static/analytics.js`. `/api/analytics` returns the shared aggregate model used by the view; API access retains the app's loopback and same-origin checks. Existing source configuration and immutable metering evidence are unchanged.
