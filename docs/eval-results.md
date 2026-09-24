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
