# Eval results

Every scored **live** run of demo 05, newest last. Written by `scripts/score.py --append`, which
only accepts a run it started itself (`--run`), in live mode, with every scored test covered by a
new invocation, every stored-failure row written by that invocation (`jev_invocation_id`,
`jev_mode`) and no dbt errors. A yardstick entry judges every state it scores (0% cached,
`--fresh`). A SIMULATED (demo-mode) run is never written here, and never quoted as a result
anywhere.

Each entry has demo 04's columns (defects, Jev and regex precision/recall, hard negatives
flagged) plus what is specific to Databricks, written by `score.py`: the warehouse, the pack token
budget, requests, retries and 429s, actual tokens, the estimated-to-actual token ratio, the Jev
cost, the Jev span in seconds (the summary line's "s Jev", the span of the packs' timestamps) and
the once-per-row counters, the dbt invocation, the cached share and, when judgments were cached,
the invocations they came from (states, requests, tokens, cost, Jev span of each). Warehouse DBUs (from `system.billing.usage`, once that schema is
enabled) and the dbt wall time are not written by `score.py`; they are added to the entry by hand.

Gate, yardstick run (unchanged from demo 04): live, no errors, Jev precision >= 0.85 and recall
>= 0.85 on every test, Jev F1 above the regex baseline on every test. Gate, production run:
recall on the loaded planted flips >= 0.85, audited precision >= 0.85, F1 above the lexicon
baseline, 0 errors, the three once-per-row checks, a rerun with 0 requests, and +2,500 rows
loaded judging the new distinct (body, stars) states and nothing else (counts are distinct
states, not rows). The production gate reads **PENDING** until the audit is labelled and
`--rerun` has run.

Wording, threshold or criteria changes to a `jev_expect` block, and any golden-key correction,
are logged here with before/after numbers.

## Reference: demo 04

Demo 04 ran the same four tests on the same data, golden key and regex baselines, on a local
DuckDB with a Python plugin. These are its gated live runs, copied by hand from
`~/Projects/jev-demo-4/docs/eval-results.md` into `eval/demo04_reference.json` (numbers as
printed there). `scripts/score.py` prints demo 05's run next to the `live/pack=64/nested` run.

How to read them:

- Demo 04 prints `N judgments · M unique`. **M is the number of distinct (test, state) pairs**
  (1,057); N (1,300) counts rows, repeats included. Demo 05's "N judgments" counts distinct
  (test, state) pairs with a successful judgment, so demo 05's judgment count is comparable with demo 04's
  unique count (1,057), not with its 1,300.
- Demo 04 does not print F1. The F1 column is derived here from the printed, 2-decimal precision
  and recall, so it can be off by a rounding step.
- `live/pack=1` sent one request per state (the recording pack in demo 04); `pack=32` and
  `pack=64` used the `nested` layout.
- The comparison uses `live/pack=64/nested` (64 rows per request). Demo 05 cuts packs by estimated
  tokens (budget 48k, cap 256 rows), about 120–256 rows per pack on these tests, so request counts
  are not like for like; the accuracy columns are.

### live/pack=1 (logged 2026-09-24T21:12:55Z)

Demo 04: 1,300 judgments · 1,057 unique (distinct test/state pairs) · 1,057 requests · 53.9 s · $0.017

| test | defects | Jev P | Jev R | Jev F1 (derived) | Jev hard-neg | regex P | regex R | regex F1 (derived) | regex hard-neg |
|---|---|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 0.65 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 0.56 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 0.55 | 8 |
| tickets_body_has_no_pii | 14 | 1.00 | 1.00 | 1.00 | 0 | 0.48 | 0.86 | 0.62 | 13 |

### live/pack=32/nested (logged 2026-09-26T15:15:25Z)

Demo 04: 1,300 judgments · 1,057 unique (distinct test/state pairs) · 35 requests · 2.0 s · $0.006

| test | defects | Jev P | Jev R | Jev F1 (derived) | Jev hard-neg | regex P | regex R | regex F1 (derived) | regex hard-neg |
|---|---|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.92 | 0.94 | 1 | 0.71 | 0.60 | 0.65 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 0.56 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 0.55 | 8 |
| tickets_body_has_no_pii | 14 | 0.93 | 1.00 | 0.96 | 1 | 0.48 | 0.86 | 0.62 | 13 |

### live/pack=64/nested (logged 2026-09-26T15:15:33Z)

Demo 04: 1,300 judgments · 1,057 unique (distinct test/state pairs) · 18 requests · 1.2 s · $0.006

| test | defects | Jev P | Jev R | Jev F1 (derived) | Jev hard-neg | regex P | regex R | regex F1 (derived) | regex hard-neg |
|---|---|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 0.65 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 0.56 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 0.55 | 8 |
| tickets_body_has_no_pii | 14 | 0.93 | 1.00 | 0.96 | 1 | 0.48 | 0.86 | 0.62 | 13 |

## Runs

`score.py --append` adds entries below this line, newest last. The first entry is the yardstick run
(`scripts/score.py --run --fresh --mode live --append`), then the production run in four steps:
(a) part 1, `scripts/score.py --production --run --fresh --mode live --append` (PENDING);
(b) the audit labels; (c) part 2, `scripts/score.py --production --run --mode live --increment
--append` (`increment: N new distinct states judged (M rows loaded)`); (d) the rerun check,
`scripts/score.py --production --run --rerun --mode live --append` (PASS or FAIL). The recording
prints the last production entry (`scripts/show.py production`).

## 2026-10-01T03:54:19Z · live/budget=48k

Jev · 1,057 judgments · 0% cached · 6 requests · 0 retries (0× 429) · 8.7 s Jev · $0.006 · LIVE jev-1.13.0 budget=48k

- invocation 6973d4ec-61ee-46ed-a5fa-dbe621e38318
- warehouse jev-demo-5 · budget 48,000 tokens · 6 requests · 0 retries (0× 429) · 146,994 tokens · Jev cost $0.006174 · est/actual tokens 1.25
- once-per-row OK: 1,057 inserted = 1,057 missing · packs sum 1,057 (+0 too long) · 0 duplicate keys · 0 errors
- cached 0% (0 of 1,057 states from earlier invocations; 1,057 judged in this run)

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.92 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 0.92 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 0.93 | 1.00 | 1 | 0.48 | 0.86 | 13 |

**Gate: PASS**

- `customers_full_name_is_a_person`: hard negatives flagged = [406], defects missed = [174, 379]
- `returns_comment_matches_reason_code`: hard negatives flagged = [], defects missed = [144]
- `reviews_body_matches_stars`: hard negatives flagged = [], defects missed = []
- `tickets_body_has_no_pii`: hard negatives flagged = [131], defects missed = []

## 2026-10-01T04:10:59Z · live/budget=48k

Jev · 1,057 judgments · 0% cached · 6 requests · 0 retries (0× 429) · 9.5 s Jev · $0.006 · LIVE jev-1.13.0 budget=48k

- invocation cc2b0646-d666-47c4-883d-a726e60e7205
- warehouse jev-demo-5 · budget 48,000 tokens · 6 requests · 0 retries (0× 429) · 146,994 tokens · Jev cost $0.006174 · est/actual tokens 1.25
- once-per-row OK: 1,057 inserted = 1,057 missing · packs sum 1,057 (+0 too long) · 0 duplicate keys · 0 errors
- cached 0% (0 of 1,057 states from earlier invocations; 1,057 judged in this run)

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 0.93 | 1.00 | 1 | 0.48 | 0.86 | 13 |

**Gate: PASS**

- `customers_full_name_is_a_person`: hard negatives flagged = [406], defects missed = [174]
- `returns_comment_matches_reason_code`: hard negatives flagged = [], defects missed = []
- `reviews_body_matches_stars`: hard negatives flagged = [], defects missed = []
- `tickets_body_has_no_pii`: hard negatives flagged = [131], defects missed = []

## 2026-10-01T04:12:17Z · live/budget=48k

Jev · 1,057 judgments · 0% cached · 6 requests · 0 retries (0× 429) · 9.1 s Jev · $0.006 · LIVE jev-1.13.0 budget=48k

- invocation 24133bcf-4760-4f99-9116-11a09c86e4b8
- warehouse jev-demo-5 · budget 48,000 tokens · 6 requests · 0 retries (0× 429) · 146,994 tokens · Jev cost $0.006174 · est/actual tokens 1.25
- once-per-row OK: 1,057 inserted = 1,057 missing · packs sum 1,057 (+0 too long) · 0 duplicate keys · 0 errors
- cached 0% (0 of 1,057 states from earlier invocations; 1,057 judged in this run)

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 0.93 | 1.00 | 1 | 0.48 | 0.86 | 13 |

**Gate: PASS**

- `customers_full_name_is_a_person`: hard negatives flagged = [406], defects missed = [174]
- `returns_comment_matches_reason_code`: hard negatives flagged = [], defects missed = []
- `reviews_body_matches_stars`: hard negatives flagged = [], defects missed = []
- `tickets_body_has_no_pii`: hard negatives flagged = [131], defects missed = []

## 2026-10-01T04:13:37Z · live/budget=48k

Jev · 1,057 judgments · 0% cached · 6 requests · 0 retries (0× 429) · 9.4 s Jev · $0.006 · LIVE jev-1.13.0 budget=48k

- invocation 5a1fa0a8-bec8-4d94-9bf8-7e6f3467529d
- warehouse jev-demo-5 · budget 48,000 tokens · 6 requests · 0 retries (0× 429) · 146,994 tokens · Jev cost $0.006174 · est/actual tokens 1.25
- once-per-row OK: 1,057 inserted = 1,057 missing · packs sum 1,057 (+0 too long) · 0 duplicate keys · 0 errors
- cached 0% (0 of 1,057 states from earlier invocations; 1,057 judged in this run)

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 0.93 | 1.00 | 1 | 0.48 | 0.86 | 13 |

**Gate: PASS**

- `customers_full_name_is_a_person`: hard negatives flagged = [406], defects missed = [174]
- `returns_comment_matches_reason_code`: hard negatives flagged = [], defects missed = []
- `reviews_body_matches_stars`: hard negatives flagged = [], defects missed = []
- `tickets_body_has_no_pii`: hard negatives flagged = [131], defects missed = []

## Run-to-run noise (2026-10-01, four fresh live runs)

The four yardstick runs above (03:54, 04:10, 04:12, 04:13 UTC) are identical apart from Jev's
own run-to-run variation: same data, questions, thresholds, layout and budget, `--fresh` each time.
Every run passed the gate with 6 requests, 0 retries and once-per-row OK. Before each `--fresh`
run deleted the previous judgments, the per-state probabilities were saved, so the same 1,057
states can be compared across the four runs.

| test | states | mean SD of p | 95th pct range | max range | pass/fail flips |
|---|---|---|---|---|---|
| customers_full_name_is_a_person | 500 | 0.0052 | 0.02 | 0.06 | 1 (id 379) |
| returns_comment_matches_reason_code | 139 | 0.0063 | 0.05 | 0.12 | 1 (id 144) |
| reviews_body_matches_stars | 241 | 0.0025 | 0.02 | 0.05 | 0 |
| tickets_body_has_no_pii | 177 | 0.0019 | 0.02 | 0.05 | 0 |

- Overall: mean SD 0.0042 and median range 0.01 across the four runs, the same order as demo 04's
  layout drift (0.0049).
- Only two rows changed their pass/fail decision, both golden defects sitting on the threshold:
  customer 379 (p = 0.69, 0.74, 0.75, 0.74 vs threshold 0.7) and return 144 (0.79, 0.83, 0.83, 0.82
  vs 0.8). The first run had both just below; runs 2–4 match demo 04's pack=64 numbers exactly
  (customers R 0.96, returns R 1.00). Customer 174 is missed in every run (a stable miss, not noise).
- So recall on these tests moves by one row (≈0.04 on customers, ≈0.08 on returns) between
  identical runs; precision did not move. A single run's recall is reliable to about one row.
