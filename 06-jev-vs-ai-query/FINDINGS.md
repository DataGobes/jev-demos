# Findings: Jev vs LLMs through `ai_query`

Every number here comes from a logged live run in `docs/eval-results.md` (pass 1 on 2026-10-03
unless noted). Costs are labelled the way the log labels them. Nothing here comes from SIMULATED
output.

## Setup in one paragraph

One dbt test (`jev_expect`) per dataset, the same sentence for every judge, decided by
`--vars '{judge: …}'`. The judges are Jev (`jev-1.13.0`, packed, flags at `p >= 0.8`),
`databricks-gpt-oss-20b` and `databricks-meta-llama-3-3-70b-instruct` through `ai_query` at
temperature 0, and `databricks-claude-opus-4-8` as the frontier judge (pilot only, see below).
Pass 1 is a shared sample of 4,161 rows: 2,000 Banking77 queries with 150 planted label swaps, the
1,916-pair Abt-Buy test split (206 matches), and 245 wanderbricks review states (205 natural plus 40
planted ratings, 31 contradictions).

## Headline 1: F1 per dataset (pass 1, same rows for every judge)

| judge | Banking77 | Abt-Buy | wanderbricks |
|---|---|---|---|
| Jev | 0.56 (P 0.85, R 0.41) | **0.86** (P 0.94, R 0.79) | **0.98** (P 1.00, R 0.97) |
| gpt-oss-20b | **0.67** (P 0.56, R 0.83) | **0.86** (P 0.80, R 0.95) | 0.91 (P 0.84, R 1.00) |
| Llama 3.3 70B | 0.50 (P 0.52, R 0.48) | 0.69 (P 0.54, R 0.98) | 0.74 (P 0.60, R 0.97) |
| baseline | 0.33 (keyword overlap) | 0.34 (token Jaccard) | none (the rule is exact) |

- **There's no single winner.** gpt-oss-20b wins Banking77, Jev and gpt-oss-20b tie on Abt-Buy, and
  Jev wins wanderbricks. Llama 3.3 70B is last everywhere, behind a model less than a third its size.
- **Jev is precise, and the LLMs catch more.** Jev's precision is 0.85 to 1.00 on all three datasets.
  The LLMs flag more freely: their recall is higher and their precision lower. Jev flags only at
  `p >= 0.8` (the test's threshold, as in demo 05), while an LLM flags whenever it answers
  `decision = true`. That threshold costs Jev recall on Banking77.
- **False alarms on clean data (wanderbricks control, 205 natural states):** Jev 0/205 (95% CI
  0.00–0.02), gpt-oss-20b 6/205 (0.01–0.06), Llama 19/205 (0.06–0.14).
- Every judge beats the dataset's simple baseline by a wide margin.

## Headline 3: subtle errors are where judges split (Banking77 recall by swap kind)

| judge | random swaps (75) | near-miss swaps (75) |
|---|---|---|
| Jev | 0.59 (0.47–0.69) | 0.24 (0.16–0.35) |
| gpt-oss-20b | 0.95 (0.87–0.98) | 0.72 (0.61–0.81) |
| Llama 3.3 70B | 0.68 (0.57–0.77) | 0.28 (0.19–0.39) |

A near-miss moves a label to a sibling intent (for example `card_arrival` to
`card_delivery_estimate`). gpt-oss-20b catches most of them. Jev and Llama catch about a quarter.
Jev at full scale reads the same way: 0.60 random against 0.20 near-miss, over 491 swaps each.

## Headline 2: cost and time (pass 1, 4,006 rows judged)

| judge | requests | wall time | cost | per 1,000 rows |
|---|---|---|---|---|
| Jev | 25 | 19.4 s | $0.029 (ledger) | $0.007 |
| gpt-oss-20b | 4,006 | 56.9 s | $0.183 (measured*) | $0.046 |
| Llama 3.3 70B | 4,006 | 141.3 s | $0.653 (measured*) | $0.163 |
| Opus 4.8 (pilot, 150 rows) | 150 | 16.4 s | $0.754 (measured*) | $5.03 |

- Jev packs states into 25 requests where `ai_query` makes one call per row. It's 3× faster than
  gpt-oss-20b and 7× faster than Llama on the same rows, and 6× and 23× cheaper.
- **Jev at full scale (pass 3):** it judged all 13,083 Banking77 queries and all 9,575 labelled
  Abt-Buy pairs. That was 18,674 new judgments in 120 requests and 25.5 s of wall time for $0.132
  (ledger), with F1 0.55, 0.88 and 0.98.
- \*Measured, with a caveat: `system.serving.endpoint_usage` logged only about a third of
  `ai_query`'s requests (1,350 of 4,006 for gpt-oss-20b in pass 1, 39 of 150 for the Opus pilot),
  and that was still true 7 hours later. Each logged request is a single row, so the logged mean
  tokens per request is multiplied by the rows judged. The log states the coverage next to every
  such cost.

## Reproducibility

Pass 2 reran Jev, gpt-oss-20b and Llama from scratch (`--fresh`, nothing cached): Jev 0.56 / 0.86 /
0.98, gpt-oss-20b 0.66 / 0.87 / 0.93, Llama 0.50 / 0.70 / 0.70. All but one F1 moved by 0.02 or
less; Llama on wanderbricks moved by 0.04. Jev's scores did not move at all.

## The frontier judge: Opus 4.8, pilot only

- The plan was `databricks-claude-opus-5`. In this workspace `ai_query` over a table rejects Opus 5,
  Opus 5.5 and Sonnet 5.5 with "not supported for batch inference". The earlier probe passed only
  because it used inline rows. `databricks-claude-opus-4-8` works, so it replaced Opus 5 in a dated
  amendment to the pre-registration, and every pilot was rerun after it.
- Opus 4.8 rejects the `temperature` parameter, so it runs at its default. The other LLMs run at 0.
- On the 50-row pilot per dataset it scored F1 0.67 / 1.00 / 1.00, caught 2 of 2 near-miss swaps and
  raised 0 of 40 false alarms. With 3, 7 and 9 positives per dataset the intervals are wide (for
  example, Banking77 recall 0.44–1.00), so this is a hint, not a result.
- Its measured cost (about 730 input and 55 output tokens per row at $5 / $25 per 1M tokens) puts a
  full pass at about $20, over the $15 cap. The user chose to skip it.

## Caveats

- **Who labelled the ground truth.** The 15 wanderbricks comment polarities were labelled by Claude
  at the user's request: 6 positive, 5 negative, 4 neutral. The Banking77 swaps are planted (seed
  42). The Abt-Buy labels are the dataset's own.
- **Thresholds differ by design.** Jev is thresholded at 0.8 and the LLMs answer yes or no. A lower Jev
  threshold would trade precision for recall. The side analysis that thresholds each judge the same
  way needs a full pass from every judge, so it was not run.
- **One workspace, one day.** The results cover one Azure Databricks workspace, the endpoints served there on
  2026-10-03 and one sample per dataset.
- **LLM spend.** Total measured LLM spend is $2.56 of the $15 cap. That includes the refused Opus 5
  attempt, which settled at $0 because nothing was served.
