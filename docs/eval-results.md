# Eval results

Every scored run, newest last. Written by `scripts/score.py --append`. Gate: live, no errors,
Jev precision ≥ 0.85 and recall ≥ 0.85 on every test, and Jev F1 > regex-baseline F1 on every test.
Wording/threshold changes are logged here with before/after numbers.

## 2026-09-24T20:35:43Z · live/pack=1

Jev · 1,300 judgments · 19% cached · 1,057 requests · 139.0 s · $0.017 · LIVE jev-latest pack=1

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

## 2026-09-24T20:36:01Z · live/pack=8

Jev · 1,300 judgments · 19% cached · 135 requests · 20.6 s · $0.008 · LIVE jev-latest pack=8

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 0.58 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 1.00 | 1.00 | 0 | 0.48 | 0.86 | 13 |

**Gate: FAIL** — returns_comment_matches_reason_code: Jev recall 0.58 < 0.85

- `customers_full_name_is_a_person`: hard negatives flagged = [406], defects missed = [174]
- `returns_comment_matches_reason_code`: hard negatives flagged = [], defects missed = [44, 48, 111, 144, 145]
- `reviews_body_matches_stars`: hard negatives flagged = [], defects missed = []
- `tickets_body_has_no_pii`: hard negatives flagged = [], defects missed = []

## 2026-09-24T20:36:25Z · live/pack=4

Jev · 1,300 judgments · 19% cached · 266 requests · 39.1 s · $0.010 · LIVE jev-latest pack=4

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 0.75 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 1.00 | 1.00 | 0 | 0.48 | 0.86 | 13 |

**Gate: FAIL** — returns_comment_matches_reason_code: Jev recall 0.75 < 0.85

- `customers_full_name_is_a_person`: hard negatives flagged = [406], defects missed = [174]
- `returns_comment_matches_reason_code`: hard negatives flagged = [], defects missed = [48, 144, 181]
- `reviews_body_matches_stars`: hard negatives flagged = [], defects missed = []
- `tickets_body_has_no_pii`: hard negatives flagged = [], defects missed = []

## 2026-09-24T20:37:35Z · live/pack=1

Jev · 1,300 judgments · 19% cached · 1,057 requests · 157.0 s · $0.017 · LIVE jev-latest pack=1

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 1.00 | 1.00 | 0 | 0.48 | 0.86 | 13 |

**Gate: PASS**

- `customers_full_name_is_a_person`: hard negatives flagged = [406], defects missed = [174]
- `returns_comment_matches_reason_code`: hard negatives flagged = [], defects missed = []
- `reviews_body_matches_stars`: hard negatives flagged = [], defects missed = []
- `tickets_body_has_no_pii`: hard negatives flagged = [], defects missed = []

## Gate conclusion (2026-09-24, controller)

- **Recording pack: 1.** pack=1 passed the gate twice (cold, then with cache): Jev precision/recall
  ≥ 0.93 on every test, beating the regex baseline on F1 everywhere.
- **Packing hurts the two-column test.** Returns (comment vs `reason_code`) recall falls with pack
  size: 1.00 at pack=1, 0.75 at pack=4 (missed 48, 144, 181), 0.58 at pack=8. The other three tests
  held steady. Packing trades speed (157 s → 39 s → 21 s) for accuracy on exactly the judgment that
  relates two fields, so it stays off by default.
- **Run-to-run variance:** tickets precision 0.93 in the first pack=1 run, 1.00 in the second —
  one hard negative sits near the 0.5 threshold. Quote the range, not the best run.
- **The two remaining errors are honest ones:** Jev misses `Pietje Puk` (a Dutch placeholder name —
  culturally specific) and flags `Anna Test` (p=0.90; Test is a real surname). No wording, threshold,
  data or answer-key changes were made; the starting wording from the plan passed as written.
- "cached" in the summary line counts every judgment not sent to the API, so it includes duplicate
  texts within one run (the seeds reuse some clean texts), not only sqlite cache hits.

## Correction (2026-09-24)

The summary-line seconds in the four runs above (`139.0 s`, `20.6 s`, `39.1 s`, `157.0 s`) were
wrong: `jev_noul` added each call's own duration to one shared counter, and dbt runs 4 worker
threads, so overlapping calls were summed instead of measuring wall time. dbt's own measured wall
times for those same four runs (`jaffle_shop/logs/dbt.log`, "Finished running ... data tests in
... seconds") were:

- live/pack=1 (run 1): 54.21 s (reported as 139.0 s)
- live/pack=8: 7.30 s (reported as 20.6 s)
- live/pack=4: 13.97 s (reported as 39.1 s)
- live/pack=1 (run 2): 54.16 s (reported as 157.0 s)

Separately, the "Gate conclusion" section's description of the two pack=1 runs as "cold, then with
cache" is wrong: both pack=1 runs show 1,057 requests each, i.e. both were fresh/uncached
invocations — two independent cold runs, not a cold run followed by a cached rerun. The same
section's "157 s → 39 s → 21 s" packing-speed claim is wrong for the same summed-time reason; the
correct dbt-measured figures are 54 s → 14 s → 7 s (pack=1 → pack=4 → pack=8).

These corrections do not change any precision/recall/F1 figures, golden-key labels, or the gate
result — only the reported timing and the cold/cached description of the two pack=1 runs. The
underlying bug (summing instead of spanning) is fixed in `src/jevdbt/stats.py`; future runs report
dbt-agreeing wall time.

## 2026-09-24T21:12:55Z · live/pack=1

Jev · 1,300 judgments · 1,057 unique · 0% cached · 1,057 requests · 53.9 s · $0.017 · LIVE jev-latest pack=1

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 1.00 | 1.00 | 0 | 0.48 | 0.86 | 13 |

**Gate: PASS**

- `customers_full_name_is_a_person`: hard negatives flagged = [406], defects missed = [174]
- `returns_comment_matches_reason_code`: hard negatives flagged = [], defects missed = []
- `reviews_body_matches_stars`: hard negatives flagged = [], defects missed = []
- `tickets_body_has_no_pii`: hard negatives flagged = [], defects missed = []

## 2026-09-26T15:15:25Z · live/pack=32/nested

Jev · 1,300 judgments · 1,057 unique · 0% cached · 35 requests · 2.0 s · $0.006 · LIVE jev-latest pack=32/nested

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.92 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 0.93 | 1.00 | 1 | 0.48 | 0.86 | 13 |

**Gate: PASS**

- `customers_full_name_is_a_person`: hard negatives flagged = [406], defects missed = [174, 379]
- `returns_comment_matches_reason_code`: hard negatives flagged = [], defects missed = []
- `reviews_body_matches_stars`: hard negatives flagged = [], defects missed = []
- `tickets_body_has_no_pii`: hard negatives flagged = [131], defects missed = []

## 2026-09-26T15:15:33Z · live/pack=64/nested

Jev · 1,300 judgments · 1,057 unique · 0% cached · 18 requests · 1.2 s · $0.006 · LIVE jev-latest pack=64/nested

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

## Pack layouts (2026-09-26)

**Question:** pack=1 means one request per row, which is too slow and too request-heavy for
production (1,057 requests, ~54 s, bounded by the 1,200 rpm limit). Can several rows share a request
without losing accuracy? The original packed layout could not: returns recall fell to 0.58 at pack=8.

**How Jev reads a request:** it ingests the `state` once and judges every question against it
independently. That leaves two places a packed record can live, and they fail differently:

- **In the shared state** (`rows`: `{"rows": {"r000": {...}, ...}}`, question "Judge ONLY
  `rows.r000` ..."). Every other row is a distractor, and the model has to *bind* each row's fields
  together. Jev's own jaggedness notes list both as failure modes ("indirection", "large state full
  of irrelevant detail"). Probabilities are pushed **down**, and more so as the pack grows.
- **In the question's own structured `instructions`** (`nested`:
  `{"record": {...}, "question": "... \`record.comment\` ..."}`, the per-candidate pattern from
  the TypeSafe Noul docs). A question can't see any other question's record, so the answer does
  **not depend on pack size**. The price is a small fixed calibration offset, caused by the record
  sitting in the question instead of the state.

**Method:** `scripts/pack_bench.py` calls Jev directly on the same 1,057 unique states and questions
the dbt tests send, all live and uncached. It saves every row's probability to `eval/pack_bench/`, and
`pack_bench.py report` regenerates the full table. "drift" is the mean |Δp| against a `single` (pack=1)
run. "flips" counts rows that land on the other side of their threshold compared with pack=1.
**Noise floor:** two identical `single` runs differ by drift 0.005 (max 0.06), with 0 flips.

| layout | pack | requests | tokens | returns R | tickets P | customers R | flips (all 4 tests) | drift |
|---|---|---|---|---|---|---|---|---|
| single | 1 | 1,057 | 403k | 1.00 | 1.00 | 0.96 | 0 (noise run) | 0.005 |
| rows (old packed default) | 8 | 135 | 201k | 0.67 | 1.00 | 0.96 | 4 | 0.038 |
| rows | 32 | 35 | 175k | **0.42** | 1.00 | 0.92 | 9 | 0.045 |
| flat (`r000_comment` keys in state) | 8 / 32 | 135 / 35 | 179k / 154k | 0.83 / 0.67 | 1.00 | 0.96 / 0.92 | 2 / 6 | 0.026 / 0.038 |
| anchored (rows state + record in question) | 8 / 32 | 135 / 35 | 213k / 187k | 1.00 / 1.00 | 1.00 | 0.96 / 0.92 | 0 / 1 | 0.033 / 0.039 |
| inline, "Data-quality check…" note as state | 1 / 8 / 32 | | | 0.83–0.92 | 0.82–0.88 | 0.92–0.96 | 4 | 0.020 |
| inline, question key first, empty state | 32 | 35 | 146k | 1.00 | 1.00 | 0.96 | 0 | **0.043** |
| inline, empty state | 1 / 32 / 32 / 64 | 1,057 / 35 / 35 / 18 | 411k / 146k / 146k / 142k | 1.00 | 0.93 | 0.96 | 1 | 0.013 |
| **nested, empty state** | 32 / 64 | 35 / 18 | 155k / 150k | 1.00 | 0.93 | 0.96 | 1 | **0.011–0.012** |

**Findings**

1. **Pack size is free when records sit in their own questions.** `inline` at pack 1 vs pack 64 differs
   by drift 0.0048, the same as the noise floor. With records in state, returns recall collapses as the
   pack grows (1.00 → 0.67 → 0.42), with a systematic downward shift of about −0.07 on the two tests that
   need the most reading.
2. **The shared state is never neutral.** An innocuous "Data-quality check…" note as the shared state
   pushed borderline PII hard negatives over 0.5 (ticket 131: 0.47 → 0.77) and cost returns recall.
   "Records from a company database." added a new false positive. An empty state (`""` and `{}` give
   identical results) is the most faithful to pack=1.
3. **Key order matters, and matching thresholds can hide drift.** Putting the question before the
   record gave 0 flips on this dataset, but drift of 0.043: clean customer names rose by +0.08 on
   average. That's a different calibration that happens to line up with these thresholds, not a
   faithful one. Record first, question last keeps every per-label shift within ±0.03.
4. **What remains is a small fixed offset.** `nested` differs from pack=1 on one row in the benchmark
   runs: ticket 131 ("Saw the number 0301234567 on your website…"), 0.47 → 0.53. This hard negative was
   already flagged in the first official pack=1 run. In the official pack=32 dbt run, customer 379
   ("Klant Klant", pack=1 p = 0.79–0.80, `nested` 0.71–0.75) also dipped just under its 0.7 threshold.
   Both are borderline rows where a −0.05 to +0.06 shift decides the outcome.

**Decision:** packed runs use `pack_style: nested` (the new default; `JEV_PACK_STYLE` overrides it)
with an empty shared state. pack=1 is still the plain one-record-per-request layout, so the recording
numbers above are unchanged. The official gated dbt runs at pack=32 and pack=64 just above both pass, at about
**30–60× fewer requests, 2.7× fewer tokens and ~$0.006 instead of $0.017**. `nested` was chosen over
`inline` for its lower drift (0.011 vs 0.013) and because it works with any column names (`inline`
cannot carry a column called `question`), at about 6% more tokens. No questions, thresholds, golden
key or baseline were changed.
