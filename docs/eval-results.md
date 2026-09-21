# Golden-set eval results (Gate 2)

**Date:** 2026-09-21 · **Model:** `jev-latest` · **SDK:** typesafe-sdk 0.7.1 · **max questions/request:** 72
**Golden set:** the 10 seed cases in `src/jevviz/golden.toml` (owner chose to run the gate on the seed set; extending to ~30 is still open).
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
