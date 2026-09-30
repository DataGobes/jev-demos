# Eval results

Every scored **live** run of demo 05, newest last. Written by `scripts/score.py --append`, which
only accepts a run it started itself (`--run`), in live mode, with every scored test covered by a
new invocation and no dbt errors. A SIMULATED (demo-mode) run is never written here, and never
quoted as a result anywhere.

Each entry has demo 04's columns (defects, Jev and regex precision/recall, hard negatives
flagged) plus what is specific to Databricks, written by `score.py`: the warehouse, the pack token
budget, requests, retries and 429s, actual tokens, the estimated-to-actual token ratio, the Jev
cost, the Jev span in seconds (the summary line's "s Jev", the span of the packs' timestamps) and
the once-per-row counters. Warehouse DBUs (from `system.billing.usage`, once that schema is
enabled) and the dbt wall time are not written by `score.py`; they are added to the entry by hand.

Gate, yardstick run (unchanged from demo 04): live, no errors, Jev precision >= 0.85 and recall
>= 0.85 on every test, Jev F1 above the regex baseline on every test. Gate, production run:
recall on planted flips >= 0.85, audited precision >= 0.85, F1 above the lexicon baseline,
0 errors, the three once-per-row checks, a rerun with 0 requests and +5,000 new rows judging
exactly 5,000. The production gate reads **PENDING** until the audit is labelled and `--rerun`
has run.

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

No live demo 05 run has been made yet. `score.py --append` adds entries below this line, newest
last. The first entries will be the yardstick run
(`scripts/score.py --run --fresh --mode live --append`) and then the production run
(`scripts/score.py --production --run --rerun --mode live --append`).
