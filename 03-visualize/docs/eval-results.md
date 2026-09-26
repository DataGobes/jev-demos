# Golden-set eval results (Gate 2)

**Date:** 2026-09-21 · **Model:** `jev-latest` · **SDK:** typesafe-sdk 0.7.1 · **max questions/request:** 72
**Golden set:** `src/jevviz/golden.toml` — 10 seed cases (Run 1), extended to 20 (Run 2) and to 30 (Run 7). Only the seed 10 were written by the owner; the other 20 were drafted by Claude.
**Dataset:** `uv run python -m jevviz.data jevviz.duckdb` (seed 7).

## Run 1 — `uv run python -m jevviz.eval jevviz.duckdb 72`

```
backend=jev-latest simulated=False
✓ region_trend                 chose=multi_line   p=1.00 top3=True baseline=False
✓ declining_region             chose=multi_line   p=1.00 top3=True baseline=False
✓ seasonality                  chose=line         p=0.99 top3=True baseline=True
✓ top_categories               chose=bar          p=1.00 top3=True baseline=True
✓ channel_share                chose=pie          p=0.98 top3=True baseline=True
✓ price_vs_rating              chose=scatter      p=0.98 top3=True baseline=False
✓ order_value_distribution     chose=histogram    p=1.00 top3=True baseline=True
✗ region_channel_mix           chose=stacked_bar  p=0.99 top3=True baseline=False
✓ margin_problem               chose=bar          p=0.99 top3=True baseline=False
✗ identifier_trap              chose=pie          p=0.86 top3=True baseline=False

Jev top-1 80% · top-3 100% · rules-only top-1 40%
```

**Gate 2: PASS.** Jev top-1 80% vs rules-only 40% = +40 percentage points (required: ≥ 15). No tuning rounds were needed; rule descriptions and `LEVELS` wording are unchanged from the plan.

## The two misses

Both are near-ties between charts a person would accept, not relevance failures:

- `region_channel_mix` ("which region and channel combinations are strongest"): chose `stacked_bar` at 0.99; the accepted `grouped_bar` (0.99/0.98) and `heatmap` (0.98) are within 0.01. In a second live run the top pick was `grouped_bar` — scores on near-ties move by ~0.01 between runs, so top-1 on this case is not stable.
- `identifier_trap` ("which customer segment spends the most"): chose `pie` of revenue by segment (0.86–0.89) over the accepted `bar` of the same columns (0.82). The trap itself worked: see Noul values below.

## Second live run — per-candidate inspection (throwaway script, not committed)

Identifier Noul (`id.<column>`, P(column is an identifier, not a measure)):

| column | noul |
|---|---|
| `customer_id` | 0.90 |
| `rating` | 0.20 |
| `revenue`, `profit`, `price` | 0.02–0.03 |

Rank key `P(level ≥ 2)` across all 10 cases:

| | min | median | p90 | max |
|---|---|---|---|---|
| candidates matching `accept` | 0.82 | 0.98 | | |
| all other candidates (n=36) | | 0.22 | 0.93 | 0.98 |

10 of the 36 non-accepted candidates score ≥ 0.6; on inspection these are defensible second choices (pie vs bar for a ranking, stacked vs grouped bars), which is what the alternates strip is for. A clearly partial answer — `line` of total revenue for "how are regions trending" — scored 0.57, i.e. just inside the weak band.

## Thresholds

| constant | value | basis |
|---|---|---|
| `ID_NOUL` | 0.5 (unchanged) | identifier 0.90 vs next-highest real measure 0.20 — wide margin either side |
| `STRONG` | 0.6 (unchanged) | every accepted candidate ≥ 0.82; the partial-answer example sits at 0.57, below the line |
| `WEAK` | 0.3 (unchanged) | no case in the seed set exercises the weak/none boundary; keep the spec default |

Ten cases are too few to justify moving any threshold; the defaults are consistent with the data. Revisit after the golden set is extended.

---

## Run 2 — golden set extended to 20 cases (2026-09-21)

The owner asked for the set to be extended to 20; the 10 added cases were drafted by Claude, not by the owner (they are marked in `golden.toml`). They target what the seed set lacked: the same SQL under different intents (`region_trend` / `region_total` / `region_share` / `latam_vague`; `channel_growth` / `channel_biggest`; `margin_problem` / `category_revenue_compare`), trap columns (`signup_year`, `rating`), and vague phrasing. Every added case was checked offline to be reachable (at least one enumerated candidate satisfies its `accept`).

```
backend=jev-latest simulated=False
✓ region_trend                 chose=multi_line   p=1.00 top3=True baseline=False
✓ declining_region             chose=multi_line   p=1.00 top3=True baseline=False
✓ seasonality                  chose=line         p=0.99 top3=True baseline=True
✓ top_categories               chose=bar          p=1.00 top3=True baseline=True
✓ channel_share                chose=pie          p=0.98 top3=True baseline=True
✓ price_vs_rating              chose=scatter      p=0.98 top3=True baseline=False
✓ order_value_distribution     chose=histogram    p=0.99 top3=True baseline=True
✓ region_channel_mix           chose=grouped_bar  p=0.99 top3=True baseline=False
✓ margin_problem               chose=bar          p=0.99 top3=True baseline=False
✗ identifier_trap              chose=pie          p=0.89 top3=True baseline=False
✓ region_total                 chose=bar          p=0.97 top3=True baseline=False
✓ region_share                 chose=pie          p=0.95 top3=True baseline=False
✓ latam_vague                  chose=multi_line   p=0.95 top3=True baseline=False
✓ signup_trend                 chose=line         p=0.96 top3=True baseline=True
✓ price_by_rating              chose=bar          p=1.00 top3=True baseline=True
✓ category_revenue_compare     chose=bar          p=1.00 top3=True baseline=True
✓ channel_growth               chose=multi_line   p=0.99 top3=True baseline=False
✓ channel_biggest              chose=pie          p=0.99 top3=True baseline=False
✓ segment_country_mix          chose=stacked_bar  p=0.99 top3=True baseline=False
✓ order_size_profit            chose=scatter      p=1.00 top3=True baseline=False

Jev top-1 95% · top-3 100% · rules-only top-1 35%
```

**Gate 2: PASS**, +60 percentage points. The one query asked four ways (`order_month, region, revenue`) got four different, correct charts: multi-line for the trend and the vague LATAM question, bar for "sold the most", pie for "share".

Caveats, stated plainly:
- The only miss is again `identifier_trap` (pie of revenue by segment over the accepted bar of the same columns) — a form preference, not a relevance or identifier error.
- `region_channel_mix` flipped from ✗ (run 1) to ✓ here with no code change: near-tie scores move ~0.01 between live runs.
- The rules-only baseline is "first candidate in pre-rank order". Because `rules/advanced.py` registers before `rules/basic.py`, position ties go to `histogram`, so for a `month, region, revenue` result the baseline's pick is a histogram of revenue. That makes the baseline weak on exactly the multi-intent cases; the margin against a smarter hand-written heuristic would be smaller.
- 20 cases, half of them written by the same model family's assistant that built the system. Treat 95% as "the approach works", not as a benchmark number.

Thresholds unchanged (`STRONG` 0.6, `WEAK` 0.3, `ID_NOUL` 0.5): the lowest accepted top pick in this run is 0.95.

---

## Run 3 — after the final-review fix wave (2026-09-21)

**Correction to Run 2.** The final code review found that integer-year columns (`signup_year`) were encoded as Vega-Lite `temporal`, which renders `2015` as 2015 ms after 1970-01-01 — a meaningless chart. Run 2 counted `signup_trend chose=line` as correct because the eval checks the chosen candidate's kind and columns, not what it renders. Jev's pick was the right *candidate*; the chart it would have drawn was broken. Fixed (integer years are now an ordinal axis, verified in the browser: axis reads 2015 … 2025). The same wave added `aggregate: sum` to `multi_line` and moved specs to the Vega-Lite v6 schema; no rule description or `LEVELS` wording changed, so the questions Jev sees are identical to Run 2.

```
backend=jev-latest simulated=False
✓ region_trend                 chose=multi_line   p=1.00 top3=True baseline=False
✓ declining_region             chose=multi_line   p=1.00 top3=True baseline=False
✓ seasonality                  chose=line         p=0.99 top3=True baseline=True
✓ top_categories               chose=bar          p=1.00 top3=True baseline=True
✓ channel_share                chose=pie          p=0.98 top3=True baseline=True
✓ price_vs_rating              chose=scatter      p=0.98 top3=True baseline=False
✓ order_value_distribution     chose=histogram    p=1.00 top3=True baseline=True
✓ region_channel_mix           chose=grouped_bar  p=0.99 top3=True baseline=False
✓ margin_problem               chose=bar          p=0.99 top3=True baseline=False
✗ identifier_trap              chose=pie          p=0.90 top3=True baseline=False
✗ region_total                 chose=pie          p=0.98 top3=True baseline=False
✓ region_share                 chose=pie          p=0.92 top3=True baseline=False
✓ latam_vague                  chose=multi_line   p=0.92 top3=True baseline=False
✓ signup_trend                 chose=line         p=0.96 top3=True baseline=True
✓ price_by_rating              chose=bar          p=1.00 top3=True baseline=True
✓ category_revenue_compare     chose=bar          p=1.00 top3=True baseline=True
✓ channel_growth               chose=multi_line   p=0.99 top3=True baseline=False
✓ channel_biggest              chose=pie          p=0.99 top3=True baseline=False
✓ segment_country_mix          chose=stacked_bar  p=1.00 top3=True baseline=False
✓ order_size_profit            chose=scatter      p=1.00 top3=True baseline=False

Jev top-1 90% · top-3 100% · rules-only top-1 35%
```

**Gate 2: PASS**, +55 points. `region_total` ("which region sold the most overall") flipped from bar (Run 2, 0.97) to pie (0.98) with identical questions — run-to-run jitter on a near-tie. Both misses are a pie chosen over the accepted bar of the same columns. A recurring pattern worth acting on: for "which X is the most" intents Jev rates pie and bar almost equally, because both descriptions say they compare categories. Sharpening the pie description toward "share of a whole" and the bar description toward "ranking" is the obvious next tuning step (it requires a fresh eval run).

## Live end-to-end timing (spec §1 success criterion 2)

Live backend on localhost, wall clock from request to the `spec` event, 2026-09-21:

| query | candidates | jev ms | wall ms to `spec` | input tokens | cache |
|---|---|---|---|---|---|
| regions trending (first request after server start) | 5 | 654 | 671 | 1,493 | miss |
| same SQL, "which region sold the most overall" | 5 | 351 | 357 | 1,473 | miss |
| regions trending again | 5 | 0.4 | 7 | 0 | hit |
| identifier trap | 7 | 228 | 241 | 1,756 | miss |
| 3-intent dashboard | 13 | 406 | 414 | 7,451 | miss |
| signup years (with a trailing `--` comment) | 1 | 238 | 240 | 630 | miss |

The `result` (table) event arrived within 2–16 ms in every case. Vega render time measured in the browser (timing bar): 42 ms for the 5-series multi-line chart, 13 ms for the year line chart. So run → chart painted is roughly 0.25–0.45 s warm and about 0.7 s for the first request on a cold connection.

---

## Run 4 — after removing two `LIMIT`s from the golden set (2026-09-22)

**Why this run.** Two golden cases truncated their results with a `LIMIT` and no `ORDER BY`:

- `identifier_trap` — `LIMIT 2000` against a query producing **4983** groups. Measured over five identical runs, DuckDB returned **three different row sets**, so the case fed Jev a nondeterministic ~40% sample of customers. The per-segment totals it plotted (`smb 2.62M · consumer 2.52M · enterprise 2.34M`) were ~41% of the truth (`6.42M · 6.23M · 6.06M`), and moved ~2% between runs against a ~4% gap between the top two segments.
- `order_size_profit` — `LIMIT 3000` against 31283 rows. Stable across five runs in practice, but only because DuckDB happened to return a consistent prefix; nothing in SQL guarantees it.

Both `LIMIT`s are now removed (an `ORDER BY ... LIMIT` was rejected for `order_size_profit`: ordering by `revenue` would keep only the smallest orders and destroy the correlation the case tests). The same fix was applied to the `Identifier trap` demo example in `web/src/examples.ts`.

This wave also added `aggregate: sum` to `pie`, `bar` and `grouped_bar`, which were emitting one mark per row rather than one per category. No rule description or `LEVELS` wording changed, so the questions Jev sees are identical to Run 3.

```
backend=jev-latest simulated=False
✓ region_trend                 chose=multi_line   p=1.00 top3=True baseline=False
✓ declining_region             chose=multi_line   p=1.00 top3=True baseline=False
✓ seasonality                  chose=line         p=0.99 top3=True baseline=True
✓ top_categories               chose=bar          p=1.00 top3=True baseline=True
✓ channel_share                chose=pie          p=0.98 top3=True baseline=True
✓ price_vs_rating              chose=scatter      p=0.96 top3=True baseline=False
✓ order_value_distribution     chose=histogram    p=1.00 top3=True baseline=True
✓ region_channel_mix           chose=grouped_bar  p=0.98 top3=True baseline=False
✓ margin_problem               chose=bar          p=0.99 top3=True baseline=False
✗ identifier_trap              chose=pie          p=0.91 top3=True baseline=False
✓ region_total                 chose=bar          p=0.97 top3=True baseline=False
✓ region_share                 chose=pie          p=0.94 top3=True baseline=False
✓ latam_vague                  chose=multi_line   p=0.90 top3=True baseline=False
✓ signup_trend                 chose=line         p=0.97 top3=True baseline=True
✓ price_by_rating              chose=bar          p=1.00 top3=True baseline=True
✓ category_revenue_compare     chose=bar          p=1.00 top3=True baseline=True
✓ channel_growth               chose=multi_line   p=0.99 top3=True baseline=False
✓ channel_biggest              chose=pie          p=0.99 top3=True baseline=False
✓ segment_country_mix          chose=grouped_bar  p=0.99 top3=True baseline=False
✓ order_size_profit            chose=scatter      p=1.00 top3=True baseline=False

Jev top-1 95% · top-3 100% · rules-only top-1 35%
```

**Gate 2: PASS**, +60 percentage points.

**The 90% → 95% is not attributable to this change.** Both cases whose SQL changed scored exactly as they did in Run 3: `identifier_trap` still misses (pie 0.91 vs 0.90), `order_size_profit` still hits (scatter 1.00, now over all 31283 rows). The entire difference is `region_total` flipping ✗ → ✓ — the same near-tie Run 3 flagged as jitter, on a case whose SQL was not touched. Read this run as "the fix changed the data without disturbing the result", not as an improvement.

Other movement, all within the documented ~0.01–0.02 jitter band: `segment_country_mix` chose `grouped_bar` rather than `stacked_bar` (both in `accept`), `price_vs_rating` 0.98 → 0.96, `latam_vague` 0.92 → 0.90.

**The one miss is unchanged and still the same pattern.** `identifier_trap` picks a pie of revenue by segment over the accepted bar of the same columns — a form preference, not a relevance or identifier failure. **(Corrected in Run 5: calling this a form preference was too lenient. The three segments differ by 1.9% of the total, i.e. 6.8 degrees of arc — a pie genuinely cannot answer "which spends the most" on this data, so it is a real wrong-chart miss.)** The identifier guard itself still works: no per-customer candidate is offered, now against 4983 distinct `customer_id` values rather than 2000. The tuning step named in Run 3 is still the open one — sharpen the `pie` description toward "share of a whole" and `bar` toward "ranking", which needs its own eval run.

Thresholds unchanged (`STRONG` 0.6, `WEAK` 0.3, `ID_NOUL` 0.5): the lowest accepted top pick here is 0.90.

---

## Run 5 — after sharpening the `pie` and `bar` descriptions (2026-09-22)

**Correction to Run 4.** Run 4 called the `identifier_trap` miss "a form preference, not a relevance or identifier failure". That was too lenient. Measuring the arc each slice actually gets:

| pie case | intent asks for | spread, top to bottom | as arc |
|---|---|---|---|
| `channel_share` | a share | 1.0% | 3.6° |
| `identifier_trap` | a ranking | 1.9% | **6.8°** |
| `region_share` | a share | 12.4% | 44.8° |

Three slices of 123.5° / 119.9° / 116.6° cannot be ranked by eye, so a pie does not answer "which customer segment spends the most" on this dataset. It was a real wrong-chart miss, and `accept = ["bar:segment+revenue"]` was right to call it.

**A numeric guard was considered and rejected.** Suppressing `pie` when the values are too close looks attractive and fits the project's "numeric guards live in code" rule, but the arithmetic kills it: any threshold that catches `identifier_trap` at 6.8° necessarily also catches `channel_share` at 3.6°, where the pie is correct and accepted. The discriminator is not the data shape — `channel_share` and `identifier_trap` have nearly identical shape and opposite right answers — it is whether the question asks for a *share* or a *ranking*. That is semantic judgment, i.e. Jev's job, so the fix belongs in the descriptions.

**The change.** `bar` and `pie` both previously said, in effect, that they compare categories, which is why Jev rated them within 0.01 on ranking intents. They are now split along the axis that separates them — ranking against a common axis (`bar`) versus how a total divides up, with the explicit note that close slices cannot be ordered by eye (`pie`). No `LEVELS` wording changed; the golden set is unchanged from Run 4.

```
backend=jev-latest simulated=False
✓ region_trend                 chose=multi_line   p=1.00 top3=True baseline=False
✓ declining_region             chose=multi_line   p=1.00 top3=True baseline=False
✓ seasonality                  chose=line         p=0.99 top3=True baseline=True
✓ top_categories               chose=bar          p=0.99 top3=True baseline=True
✓ channel_share                chose=pie          p=0.81 top3=True baseline=True
✓ price_vs_rating              chose=scatter      p=0.98 top3=True baseline=False
✓ order_value_distribution     chose=histogram    p=0.98 top3=True baseline=True
✗ region_channel_mix           chose=stacked_bar  p=0.98 top3=True baseline=False
✓ margin_problem               chose=bar          p=0.98 top3=True baseline=False
✓ identifier_trap              chose=bar          p=0.90 top3=True baseline=False
✓ region_total                 chose=bar          p=0.95 top3=True baseline=False
✓ region_share                 chose=pie          p=0.96 top3=True baseline=False
✓ latam_vague                  chose=multi_line   p=0.93 top3=True baseline=False
✓ signup_trend                 chose=line         p=0.98 top3=True baseline=True
✓ price_by_rating              chose=bar          p=0.99 top3=True baseline=True
✓ category_revenue_compare     chose=bar          p=1.00 top3=True baseline=True
✓ channel_growth               chose=multi_line   p=0.99 top3=True baseline=False
✓ channel_biggest              chose=bar          p=0.89 top3=True baseline=False
✓ segment_country_mix          chose=grouped_bar  p=0.99 top3=True baseline=False
✓ order_size_profit            chose=scatter      p=1.00 top3=True baseline=False

Jev top-1 95% · top-3 100% · rules-only top-1 35%
```

**Gate 2: PASS**, +60 percentage points. The headline is unchanged at 95%, but it is unchanged for a different reason, and the composition moved in exactly the intended direction:

| case | Run 4 | Run 5 | reading |
|---|---|---|---|
| `identifier_trap` | ✗ pie 0.91 | **✓ bar 0.90** | the target miss, converted |
| `channel_biggest` | ✓ pie 0.99 | ✓ **bar** 0.89 | scored ✓ either way (both in `accept`), but now picks the better chart for "which is biggest" |
| `channel_share` | ✓ pie 0.98 | ✓ pie **0.81** | still correctly a pie for a share question, but less confidently — the description now discloses the limitation, and the score reflects it |
| `region_share` | ✓ pie 0.94 | ✓ pie 0.96 | unmoved, correctly a pie |
| `region_total` | ✓ bar 0.97 | ✓ bar 0.95 | held; this case had flickered ✗/✓ across Runs 2–4 |
| `region_channel_mix` | ✓ grouped_bar | **✗ stacked_bar 0.98** | the new miss — see below |

Every pie-vs-bar case moved the right way, and none of them is a near-tie any more: pie now wins share questions and loses ranking questions, rather than the two sitting within 0.01 of each other.

**The new miss is the long-standing flaky case, not a regression from this change.** `region_channel_mix` has landed on both sides across the whole history — ✗ `stacked_bar` (Run 1), ✓ `grouped_bar` (Runs 2, 3, 4), ✗ `stacked_bar` (Run 5) — with `stacked_bar`, `grouped_bar` and `heatmap` all inside 0.01 every time. Neither of those two descriptions was touched in this wave.

**The obvious next step, by the same logic.** `stacked_bar` and `grouped_bar` are now in the position `pie` and `bar` were in before this run: both descriptions say they show one measure broken down by two dimensions, and neither says what the reader can actually *do* with it. And the perceptual asymmetry is the same one — in a stacked bar only the bottom segment starts at the axis, so segments above it are compared without a common baseline, exactly the problem that makes pie slices hard to rank. Sharpening `stacked_bar` toward "each category's total, and its composition" and `grouped_bar` toward "comparing the sub-values against each other" is the same one-line fix that worked here. It needs its own eval run.

Thresholds unchanged (`STRONG` 0.6, `WEAK` 0.3, `ID_NOUL` 0.5). The lowest accepted top pick is now 0.81 (`channel_share`), down from 0.90 — still comfortably above `STRONG`, but worth watching if the `pie` description is sharpened further.

---

## Run 6 — after sharpening the `stacked_bar` and `grouped_bar` descriptions (2026-09-22)

**The change.** The pair named at the end of Run 5. `stacked_bar` and `grouped_bar` both said, in effect, that they show one measure broken down by two dimensions, leaving them within 0.01 of each other — and of `heatmap` — on every two-dimension intent. They are now split on what the reader can actually do, using the same perceptual asymmetry that separated `bar` from `pie`: a grouped bar puts every bar on a common baseline, so any sub-value can be compared with any other (but it shows no category totals); a stacked bar shows totals and composition, but only its bottom segment starts at the axis, so sub-values cannot be compared across categories. No `LEVELS` wording or golden-set SQL changed.

```
backend=jev-latest simulated=False
✓ region_trend                 chose=multi_line   p=1.00 top3=True baseline=False
✓ declining_region             chose=multi_line   p=1.00 top3=True baseline=False
✓ seasonality                  chose=line         p=0.99 top3=True baseline=True
✓ top_categories               chose=bar          p=0.99 top3=True baseline=True
✓ channel_share                chose=pie          p=0.80 top3=True baseline=True
✓ price_vs_rating              chose=scatter      p=0.98 top3=True baseline=False
✓ order_value_distribution     chose=histogram    p=1.00 top3=True baseline=True
✓ region_channel_mix           chose=grouped_bar  p=0.98 top3=True baseline=False
✓ margin_problem               chose=bar          p=0.98 top3=True baseline=False
✓ identifier_trap              chose=bar          p=0.88 top3=True baseline=False
✓ region_total                 chose=bar          p=0.95 top3=True baseline=False
✓ region_share                 chose=pie          p=0.92 top3=True baseline=False
✓ latam_vague                  chose=multi_line   p=0.94 top3=True baseline=False
✓ signup_trend                 chose=line         p=0.97 top3=True baseline=True
✓ price_by_rating              chose=bar          p=1.00 top3=True baseline=True
✓ category_revenue_compare     chose=bar          p=1.00 top3=True baseline=True
✓ channel_growth               chose=multi_line   p=0.99 top3=True baseline=False
✓ channel_biggest              chose=bar          p=0.93 top3=True baseline=False
✗ segment_country_mix          chose=heatmap      p=0.99 top3=True baseline=False
✓ order_size_profit            chose=scatter      p=0.99 top3=True baseline=False

Jev top-1 95% · top-3 100% · rules-only top-1 35%
```

**Gate 2: PASS**, +60 percentage points. The targeted case converted and a different two-dimension case broke:

- `region_channel_mix` ("which region and channel combinations are strongest"): ✗ `stacked_bar` → **✓ `grouped_bar` 0.98**. This case had flickered across all five previous runs; it is now decided on a stated capability rather than a coin flip.
- `segment_country_mix` ("how do customer segments break down within each country"): ✓ `grouped_bar` → **✗ `heatmap` 0.99**. `accept` is `stacked_bar` or `grouped_bar`.

**In the demo** — which is what this pass was for — the dashboard's middle panel now resolves correctly. "Which channel is biggest" picks the plain `bar` at 0.90, with `stacked_bar` demoted to 0.84 and `pie` to 0.79; before this change `stacked_bar` took it at 0.93 over `bar` at 0.90. All three dashboard panels are now right.

### Diagnosis: three forms compete for two-dimension intents, and only two were differentiated

`stacked_bar`, `grouped_bar` and `heatmap` all answer "one measure, two dimensions". Sharpening two of the three did not remove the ambiguity — it moved it. `heatmap` is now the only member of the trio whose description does not say what it cannot do, and it absorbed the slack: it won a *composition* question ("break down within each country"), which a heatmap does not answer. It shows each cell's level; it gives no totals per row or column and no sense of how a total divides.

That makes one more targeted change available, and it is principled rather than fitted to the failing case: say plainly that a heatmap reads combination levels, not composition or totals. If that does not close the gap, the honest read is that 19/20 is where this golden set bottoms out.

### A caveat on continuing to tune

Three consecutive runs have now landed on 95% with a different single miss each time (`identifier_trap`, `region_channel_mix`, `segment_country_mix`). Each pass fixed the case it targeted. But near-ties in this set move ~0.01 between identical runs, the set is 20 cases, and half of them were drafted by the same assistant that wrote the rules. Tuning descriptions until the last case flips would be fitting to that set rather than improving the system. The `heatmap` change is worth one run because it completes a trio on a stated principle; past that, extending the golden set is the better investment than further wording passes.

Thresholds unchanged (`STRONG` 0.6, `WEAK` 0.3, `ID_NOUL` 0.5). Lowest accepted top pick: 0.80 (`channel_share`).

---

## Run 7 — golden set extended to 30 cases (2026-09-22)

**No rule or description changed since Run 6.** This run isolates the effect of the new cases; the `heatmap` description change proposed in Run 6 was deliberately *not* bundled in, because a run that changes both the set and a description cannot say which one moved the score.

**The 10 added cases** (drafted by Claude, marked in `golden.toml`) target what the 20-case set never exercised: the `kpi` path (no case at all, despite being a demo feature), a count-based `line`, a second `histogram`, a numeric-guard trap, a 5×5 grid for `heatmap`, a pure composition intent for `stacked_bar`, and `scatter`/ranking with distractor columns. Every case was checked offline to be reachable *and* to have at least two competing candidates — three first drafts (`price_distribution`, `orders_per_month`, `country_ranking`) had only one non-table candidate, which makes a case a path test rather than a discrimination test, so each got a distractor measure before the run.

```
backend=jev-latest simulated=False
✓ region_trend                 chose=multi_line   p=1.00 top3=True baseline=False
✓ declining_region             chose=multi_line   p=1.00 top3=True baseline=False
✓ seasonality                  chose=line         p=0.99 top3=True baseline=True
✓ top_categories               chose=bar          p=1.00 top3=True baseline=True
✓ channel_share                chose=pie          p=0.81 top3=True baseline=True
✓ price_vs_rating              chose=scatter      p=0.98 top3=True baseline=False
✓ order_value_distribution     chose=histogram    p=1.00 top3=True baseline=True
✓ region_channel_mix           chose=heatmap      p=0.98 top3=True baseline=False
✓ margin_problem               chose=bar          p=0.99 top3=True baseline=False
✓ identifier_trap              chose=bar          p=0.88 top3=True baseline=False
✓ region_total                 chose=bar          p=0.91 top3=True baseline=False
✓ region_share                 chose=pie          p=0.94 top3=True baseline=False
✓ latam_vague                  chose=multi_line   p=0.91 top3=True baseline=False
✓ signup_trend                 chose=line         p=0.98 top3=True baseline=True
✓ price_by_rating              chose=bar          p=0.99 top3=True baseline=True
✓ category_revenue_compare     chose=bar          p=1.00 top3=True baseline=True
✓ channel_growth               chose=multi_line   p=0.99 top3=True baseline=False
✓ channel_biggest              chose=bar          p=0.91 top3=True baseline=False
✓ segment_country_mix          chose=grouped_bar  p=0.99 top3=True baseline=False
✓ order_size_profit            chose=scatter      p=0.99 top3=True baseline=False
✓ total_revenue_kpi            chose=kpi          p=0.98 top3=True baseline=False
✓ order_count_kpi              chose=kpi          p=0.97 top3=True baseline=False
✓ price_distribution           chose=histogram    p=0.97 top3=True baseline=True
✓ orders_per_month             chose=line         p=1.00 top3=True baseline=True
✓ region_category_grid         chose=heatmap      p=0.99 top3=True baseline=False
✗ category_channel_mix         chose=grouped_bar  p=0.98 top3=False baseline=False
✓ negative_profit_trap         chose=bar          p=0.70 top3=True baseline=False
✓ country_ranking              chose=bar          p=0.97 top3=True baseline=True
✓ segment_growth               chose=multi_line   p=0.97 top3=True baseline=False
✓ profit_vs_revenue_by_channel chose=scatter      p=0.98 top3=True baseline=False

Jev top-1 97% · top-3 97% · rules-only top-1 33%
```

**Gate 2: PASS**, +64 percentage points. The 10 new cases went 9/10; the original 20 went 20/20 for the first time — but see the caveat below before reading that as progress.

### The miss is the first top-3 miss in the project's history, and it is diagnostic

`category_channel_mix` ("what is the channel mix within each category") chose `grouped_bar` at 0.98. The accepted `stacked_bar` was **not in the top 3 at all** — every previous run, across 20 cases and six runs, had top-3 at 100%.

"Mix within each category" is a composition question, and a stacked bar is the textbook form for it. It lost because of the Run 6 wording. `stacked_bar`'s description now closes on a limitation — *"only the bottom segment starts at the axis, so individual channel values cannot be compared across category"* — and `grouped_bar`'s opens on the matching strength — *"any channel value can be compared with any other, within one category"*. Read against "channel mix within each category", the grouped description matches on the surface words and the stacked one warns against them. The limitation clause is doing more work than the composition claim it was meant to qualify.

This is precisely the failure the 20-case set could not show: it had one composition intent (`segment_country_mix`), and that one accepts `grouped_bar` too, so an over-penalised `stacked_bar` was invisible until a case existed that accepts *only* the stacked form.

**Fix, principled and one line:** lead `stacked_bar` with what it is for — the form for composition, "mix", "breakdown", how a total divides — and demote the baseline caveat to a trailing qualifier. Together with the still-pending `heatmap` change from Run 6 ("reads combination levels, not composition or totals"), that completes the two-dimension trio on stated capabilities. One run, both changes: they touch different rules and different intents, so the result stays attributable.

### Other findings from the new cases

- **The `kpi` path is evaluated for the first time, and it discriminates.** With `revenue` and `orders` both on the single row, Jev picked the *right* KPI for each intent (0.98 / 0.97), and neither `orders` (a count) was mistaken for an identifier by the Noul question. A 1-row result also enumerates a one-bar `bar` and a one-slice `pie` — the profiler classifies a single-value integer as both nominal and quantitative — so the KPI had genuine competition; both those forms are anti-patterns and were correctly not chosen.
- **The numeric-guard trap behaved as designed, and shows what a forced fallback looks like.** `negative_profit_trap` asks "what share of profit", but row-level profit reaches −224.65, so the `pie` rule's `q.min < 0` guard never emitted a pie. Jev picked the `bar` — the best chart available — at **0.70**, the lowest accepted top pick in any run (previous floor: 0.80). That number is honest: a bar is a mediocre answer to a "share" question, and the score says so. It also narrows the margin over `STRONG` (0.6) from 0.20 to 0.10. Worth keeping in view: when a guard removes the ideal form, the chosen chart still wears a plain "70% match" chip, with nothing telling the reader the better form was withheld on purpose.
- **The 5×5 grid went to `heatmap` (0.99)** over `grouped_bar`, as intended — a larger grid is where a heatmap earns its place, and the 5×3 `region_channel_mix` also landed on `heatmap` this run (Run 6: `grouped_bar`). Both are in `accept`; the trio is still a near-tie underneath.

### Caveats

- **20/20 on the old cases is not evidence of improvement.** No rule changed since Run 6. `region_channel_mix` and `segment_country_mix` each landed in `accept` because both accept two of the three two-dimension forms; the underlying scores are still within ~0.01. The old set landing clean is the coin coming up heads twice, not a fixed coin.
- **Two thirds of the set is now Claude-drafted** (20 of 30). The percentage measures agreement between a model-drafted benchmark and a model-ranked system. Treat 97% as "the approach works and the misses are legible", not as a benchmark number.
- The rules-only baseline fell from 35% to 33%: the new cases are harder for "first candidate in enumeration order", which is the intended direction for a baseline.

Thresholds unchanged (`STRONG` 0.6, `WEAK` 0.3, `ID_NOUL` 0.5). Lowest accepted top pick: **0.70** (`negative_profit_trap`, guard-forced), then 0.81 (`channel_share`).

---

## Run 8 — `stacked_bar` and `heatmap` descriptions completed (2026-09-22)

**The change.** The two edits proposed at the end of Run 7, and nothing else: `stacked_bar` now *leads* with what it is for (composition — how a total breaks down, what mix makes it up) and carries the common-baseline caveat as a trailing qualifier instead of a closing warning; `heatmap` now says what it cannot do (reads cell levels only; no totals, nothing about how a total is made up). That completes the two-dimension trio: all three of `stacked_bar`, `grouped_bar` and `heatmap` now state a capability *and* a limitation. Golden set unchanged from Run 7.

```
backend=jev-latest simulated=False
✓ region_trend                 chose=multi_line   p=1.00 top3=True baseline=False
✓ declining_region             chose=multi_line   p=1.00 top3=True baseline=False
✓ seasonality                  chose=line         p=0.99 top3=True baseline=True
✓ top_categories               chose=bar          p=1.00 top3=True baseline=True
✓ channel_share                chose=pie          p=0.80 top3=True baseline=True
✓ price_vs_rating              chose=scatter      p=0.98 top3=True baseline=False
✓ order_value_distribution     chose=histogram    p=1.00 top3=True baseline=True
✓ region_channel_mix           chose=grouped_bar  p=0.98 top3=True baseline=False
✓ margin_problem               chose=bar          p=0.98 top3=True baseline=False
✓ identifier_trap              chose=bar          p=0.92 top3=True baseline=False
✓ region_total                 chose=bar          p=0.93 top3=True baseline=False
✓ region_share                 chose=pie          p=0.95 top3=True baseline=False
✓ latam_vague                  chose=multi_line   p=0.91 top3=True baseline=False
✓ signup_trend                 chose=line         p=0.97 top3=True baseline=True
✓ price_by_rating              chose=bar          p=0.98 top3=True baseline=True
✓ category_revenue_compare     chose=bar          p=1.00 top3=True baseline=True
✓ channel_growth               chose=multi_line   p=0.99 top3=True baseline=False
✓ channel_biggest              chose=bar          p=0.89 top3=True baseline=False
✓ segment_country_mix          chose=stacked_bar  p=1.00 top3=True baseline=False
✓ order_size_profit            chose=scatter      p=1.00 top3=True baseline=False
✓ total_revenue_kpi            chose=kpi          p=0.97 top3=True baseline=False
✓ order_count_kpi              chose=kpi          p=0.95 top3=True baseline=False
✓ price_distribution           chose=histogram    p=0.98 top3=True baseline=True
✓ orders_per_month             chose=line         p=1.00 top3=True baseline=True
✗ region_category_grid         chose=stacked_bar  p=0.99 top3=True baseline=False
✓ category_channel_mix         chose=stacked_bar  p=1.00 top3=True baseline=False
✓ negative_profit_trap         chose=bar          p=0.63 top3=True baseline=False
✓ country_ranking              chose=bar          p=0.98 top3=True baseline=True
✓ segment_growth               chose=multi_line   p=0.98 top3=True baseline=False
✓ profit_vs_revenue_by_channel chose=scatter      p=0.98 top3=True baseline=False

Jev top-1 97% · top-3 100% · rules-only top-1 33%
```

**Gate 2: PASS**, +64 percentage points. Top-3 is back to 100%: the Run 7 regression is gone.

- `category_channel_mix` ("what is the channel mix within each category"): ✗ with `stacked_bar` outside the top 3 → **✓ `stacked_bar` 1.00**. The targeted fix, converted decisively.
- `segment_country_mix` ("how do segments break down within each country"): ✓ `grouped_bar` → **✓ `stacked_bar` 1.00**. Both are accepted, but the stacked bar is the textbook composition chart, and it now wins outright rather than by coin flip.
- `region_channel_mix` ("which combinations are strongest"): `heatmap` (Run 7) → `grouped_bar` (Run 8), both 0.98, both accepted. This one is a genuine tie and probably should be: both forms answer that question well. The trio is now split on composition-vs-not; heatmap-vs-grouped for "strongest combination" is a preference, not a distinction.

### The new miss is most likely a wrong answer key, and I am not going to fix it myself

`region_category_grid` — *"is there a region where one product category dominates"* — chose `stacked_bar` 0.99. `accept` is `heatmap` or `grouped_bar`.

I wrote this case in Run 7 to give `heatmap` a 5×5 grid to earn its place on. But read the intent I gave it: "a region where one category *dominates*" is answered by looking at each region's make-up and seeing whether one category takes most of it — that is a composition read, and a stacked bar shows it directly (one segment swallowing a region's bar). A heatmap answers it too (one dark cell in a row), as does a grouped bar. All three are defensible; the key admits two of them. The pick is reasonable. The key is arguably too narrow for the intent's wording.

**Two honest options, both of which are set corrections, not tuning wins:** widen `accept` to include `stacked_bar:region+category+revenue`, or rephrase the intent to something genuinely grid-flavoured ("which single region and category pairs bring in the most revenue"). I drafted the case, the description change, and this diagnosis, so changing the key on my own say-so is exactly the overfitting move the Run 6 and Run 7 caveats warned against. It is the owner's call, and whichever way it goes the record should say the *set* changed, not that the model improved.

**Key corrected after Run 8 (owner's decision).** `region_category_grid` now also accepts `stacked_bar:region+category+revenue`. Re-scoring Run 8's recorded picks under the corrected key — a deterministic check of `matches()`, not a new run — gives **30/30**. That is a set correction, and it is recorded as one: the model's picks did not change.

### Watch item: the guard-forced fallback is now on the threshold

`negative_profit_trap` fell from 0.70 (Run 7) to **0.63** — 0.03 above `STRONG` (0.6). Neither `bar` nor `pie` changed this run, so this is run-to-run movement, and it is larger than the ~0.01 seen on high-confidence answers: low-confidence answers appear to jitter more. One more move of the same size and the demo would show a "weak match" chip on a chart that is the *correct* choice given the guard withheld the pie. That is the honest reading of a 0.6 threshold, but it is worth deciding on purpose: either accept that guard-forced fallbacks can read as weak, or have the UI say why the better form was withheld.

**In the demo.** All three dashboard panels are still right, with one margin worth recording. "Which channel is biggest" still picks the plain `bar` (0.90) but `stacked_bar` closed from 0.84 to 0.87 — the stronger composition claim earned it back some ground on a ranking intent, so the margin is now 3 points, not 6. "Where do region and channel combine best" shows `grouped_bar`/`heatmap` at 0.98 with the stacked form *also* at 0.98: a dead heat, and the same ambiguity as `region_category_grid` — "combine best" reads as composition or as cell magnitude, and both readings are fair. The Identifier-trap example is unaffected (`bar` 0.89, cache hit).

### Where this stops

The two-dimension trio is done. Every pair that was tuned across Runs 5–8 was tuned on a stated perceptual principle (common baseline vs not; share vs ranking; cell level vs composition), and each pass converted the case it targeted without a wording-driven regression surviving to the next run. Further description passes would be fitting to this set. What remains is set work — the `region_category_grid` key, more owner-written cases — and the threshold question above.

Thresholds unchanged (`STRONG` 0.6, `WEAK` 0.3, `ID_NOUL` 0.5). Lowest accepted top pick: **0.63** (`negative_profit_trap`, guard-forced); next lowest 0.80.
