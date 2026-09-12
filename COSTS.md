# Cost analysis: API what-ifs

Open **Cost analysis** to estimate how the selected local workload would cost at API text-token rates. This is an offline calculator: no API requests, keys, payments, or changes to usage evidence. It is not a ChatGPT subscription invoice or a reconstruction of historical provider charges. Imported provider costs remain separate.

## Explore

1. Select the period and any project, evidence or search filters. Existing consumption drill-downs carry across.
2. Keep the recorded model mix or assume every selected request uses a preset model. Alternatively, supply custom flat prices in USD per million tokens.
3. Choose the workload multiplier and caching. Open **Advanced assumptions** for processing tier, per-request input/output scaling and context pricing. Custom prices appear when that model option is selected. Click **Update estimate**. Quick presets reset the other controls to their defaults before applying the named change.
4. The page starts with the **Current model mix** estimate. After a change, **Your what-if** shows the alternative and the difference on entries priced in both scenarios. Open the coverage disclosure for counts and unpriced reasons. **Showing** describes the applied assumptions; unfinished edits are labeled **Changes not applied yet**.
5. Group by project, model, task, person, purpose, application, device, directory, branch, evidence or date. Click a ranked bar or table group to narrow the selection. **Inspect matching usage** opens the underlying evidence in the ledger.
6. Open **Save or export this estimate** to save named calculated assumptions in this browser. Loading a saved scenario applies those assumptions to the current selection, using the app's current rate snapshot; it does not restore old usage or filters. JSON export captures the scenario, price snapshot, exact filters, time of calculation, coverage and complete group breakdown. CSV exports every filtered group and all token cost columns, independently of pagination, in the selected order. Enable **Show token cost columns** to see those additional columns in the table. Decimal values retain calculation precision in exports; the UI rounds dollars to cents.

## Keep assumptions and exports

In the browser edition, **Save assumptions** creates a named scenario in the open workspace. Use **Save in this browser** afterward to persist it, or **Download complete backup** to include it in a portable workspace copy. Closing or reloading otherwise loses unsaved changes. In the optional collector edition, named assumptions are saved separately in that browser origin's localStorage, not in the collector database.

A scenario JSON or cost CSV is a calculation export, not a full evidence backup. It can include private project/group names and filters and is not anonymized. See [browser saving](BROWSER.md#save-or-make-a-backup) and [export privacy](PRIVACY.md#backups-sharing-and-deletion).

## Calculation

Per included source entry:

- Ordinary input = input − cached reads − cache writes. These are disjoint price categories in the calculation. Overlapping cache quantities remain unpriced.
- Output includes reasoning. Neither reasoning nor cached input is added to the total again.
- Input/output scaling changes individual request size. Workload repetitions multiply cost after context pricing is determined.
- With a target cached-read share, the reported proportion of cache writes within noncached input is preserved. Disabling caching sets reads and writes to zero and prices all input as ordinary input.
- Sum quantity × corresponding price, divide by one million, and apply the eligible tier and workload multipliers. Decimal arithmetic uses 50 significant digits. Preserving a write proportion may require rounding a recurring decimal at that precision.
- Missing optional cache amounts are assumed zero; the methodology reports how many entries lack declarations. Estimates rely on the source counts and do not establish billing identity or cache eligibility.

The fixed baseline keeps recorded models, reported caching and original request sizes at Standard rates. Only verified model names and the documented `gpt-5.6` alias are priced automatically. A different target model can price previously unknown models hypothetically; its extra coverage is not counted as savings against a missing baseline. No priced entries means **Not priced**, while valid zero-cost assumptions produce zero.

Auto context mode requires native response evidence. It prices requests above 272,000 input tokens at long-context rates and excludes requests exceeding the preset context/output limits. Legacy deltas cannot establish individual request size. Explicit short/long modes instead price token volumes at the chosen rates, including legacy deltas, without establishing request eligibility. Custom rates are flat: tier and long-context uplifts are ignored, while auto mode still requires native records.

## Rate sources and scope

The preset snapshot was checked on **9 September 2026** against [OpenAI API pricing](https://developers.openai.com/api/docs/pricing). It contains GPT-6 Astra and GPT-5.6 Sol, Terra and Luna. The page lists ordinary input, cached input, cache writes and output, short/long context, and Standard, Batch, Flex and Fast prices. Sol's current promotional prices are documented through at least 21 November 2026. This application does not fetch or update prices automatically.

Request limits and the Sol alias were checked against the official model pages: [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra), [Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol), [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra), and [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

Model comparisons hold token counts fixed or apply the user's explicit scaling. They do not predict equal capability, latency, cache reuse, or request eligibility. Tools, storage, media-specific charges, regional processing uplifts, taxes, credits, negotiated discounts and subscription charges are excluded. All values are USD; no exchange-rate conversion is implied.

## Validation

Cost tests cover input/cache/reasoning partitioning, context boundaries, tier and custom prices, scaling, incomplete coverage, comparable-only differences, exact filters, group reconciliation, global sorting, invalid inputs, excluded evidence and read-only accounting. Browser checks exercise presets, tier/custom changes, draft preservation, saved scenarios, JSON/CSV downloads, drill-through, mobile layout and empty/unpriced states.
