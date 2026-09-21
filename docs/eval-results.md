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
