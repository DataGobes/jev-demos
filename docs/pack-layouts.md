# Pack layouts: batching rows into one Jev request without losing accuracy

*2026-09-26, extended 2026-09-28 with pack sizes up to 1024 · live `jev-latest` runs only · code:
`src/jevdbt/packing.py`, `scripts/pack_bench.py`*

## Question

At pack=1 every row is its own Jev request: 1,057 requests and ~54 s for this project, bounded by the
1,200 rpm limit. That's fine for a demo and impractical in production. Can several rows share a
request without losing accuracy? The original packed layout could not: returns recall fell from 1.00
at pack=1 to 0.58 at pack=8 (see the 2026-09-24 runs in [eval-results.md](eval-results.md)).

## How Jev reads a request

Jev ingests the `state` once and judges every question against it independently. That leaves two
places a packed record can live, and they fail in different ways.

**In the shared state** (`rows`, the original packed layout):

```json
{
  "state": {"rows": {"r000": {"comment": "...", "reason_code": "late"}, "r001": {...}, ...}},
  "questions": {
    "r001": {"type": "noul", "instructions": "Judge ONLY the record in `rows.r001`, ignoring all other rows. The customer's `rows.r001.comment` describes ..."}
  }
}
```

Every other row is a distractor, and the model has to *bind* each row's fields together: this
`comment` goes with that `reason_code`. Jev's own jaggedness notes list both as failure modes
("indirection" and "large state full of irrelevant detail"). Probabilities are pushed down, and more
so as the pack grows.

**Inside the question's own structured `instructions`** (`nested`, the new default):

```json
{
  "state": "",
  "questions": {
    "r001": {
      "type": "noul",
      "instructions": {
        "record": {"comment": "...", "reason_code": "late"},
        "question": "The customer's `record.comment` describes a different main reason for the return than `record.reason_code` ..."
      },
      "criteria": {"true": "...", "false": "..."}
    }
  }
}
```

This is the per-candidate pattern from the TypeSafe Noul docs. A question can't see any other
question's record, so the answer does not depend on pack size. The price is a small fixed calibration
offset, caused by the record sitting in the question instead of the state.

## Method

`scripts/pack_bench.py` calls Jev directly, without dbt, on the same 1,057 unique states and questions
the four `jev_expect` tests send. All runs are live and uncached. It saves every row's probability to
`eval/pack_bench/<style>_p<pack>_<tag>.json`, and `pack_bench.py report` regenerates the table below
from those files.

- **drift**: mean |Δp| against a `single` (pack=1) run, over all rows of all four tests.
- **flips**: rows that land on the other side of their test's threshold compared with pack=1.
- **Noise floor**: two identical `single` runs differ by drift 0.005 (max 0.06) with 0 flips. Drift
  near 0.005 means the layout does not change the model's judgment.

## Results

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

Reviews held 1.00/1.00 in every layout. Every layout kept AUC ≥ 0.995 on every test, so defects
always ranked above clean rows. Packing moves calibration (where probabilities sit relative to the
thresholds), not ranking.

## Findings

1. **Pack size is free when records sit in their own questions.** `inline` at pack 1 vs pack 64 differs
   by drift 0.0048, the same as the noise floor, and `nested` stays that stable up to 256 rows per
   request (see [How far packing goes](#how-far-packing-goes-pack-size-and-the-token-ceiling)).
   With records in state, returns recall collapses as the pack grows (1.00 → 0.67 → 0.42), with a
   systematic downward shift of about −0.07 on the two tests that need the most reading (customers,
   returns).
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
5. **Packing also saves tokens.** A pack=1 request averages ~380 input tokens for records of ~30 tokens,
   so most of it is per-request overhead. Batching removes that overhead: 403k → 150k tokens.

## Decision

Packed runs use `pack_style: nested` with an empty shared state. It is the default; override it in
`profiles.yml` or with `JEV_PACK_STYLE`. pack=1 is still the plain one-record-per-request layout, so
the recorded demo numbers are unchanged.

The official gated dbt runs at pack=32 and pack=64 both pass (see `live/pack=32/nested` and
`live/pack=64/nested` in [eval-results.md](eval-results.md)):

| | pack=1 | pack=32 nested | pack=64 nested |
|---|---|---|---|
| requests | 1,057 | 35 | 18 |
| wall time (dbt) | ~54 s | 2.0 s | 1.2 s |
| cost | $0.017 | $0.006 | $0.006 |
| gate | PASS | PASS | PASS |

`nested` was chosen over `inline` for its lower drift (0.011 vs 0.013), because it is closest on the
one flipped benchmark row (ticket 131: 0.53 vs 0.65), and because it works with any column names
(`inline` can't carry a column called `question`). It costs about 6% more tokens. No questions,
thresholds, golden key or baseline were changed.

## How far packing goes: pack size and the token ceiling

*Added 2026-09-28.* Is there a point where more rows per request start to cost accuracy? And what
actually limits the pack size?

**There is no limit on the number of questions.** A one-off live probe sent requests of tiny `nested`
questions (`{"record": {"n": i}, "question": "\`record.n\` is an even number"}`) with an empty state.
Every size from 128 to 1,700 questions per request was accepted (1,700 questions = 62k input tokens).
2,048 questions (about 74k tokens) was rejected with `400 {"error_type": "max_tokens_exceeded"}`. The
ceiling is the documented 64k tokens per request, not a question count. These probe requests aren't
saved in `eval/pack_bench/`, because they aren't a benchmark of the demo's tests.

**The demo's tests, with `nested` and an empty state, at larger packs.** The scorer packs each test
separately, and the largest test has 500 unique rows. So from pack 512 up, every test goes out as a
single request, and pack 512 and 1024 are the same run.

| rows per request | requests | tokens | wall (benchmark) | customers P / R | returns P / R | reviews P / R | tickets P / R | drift vs pack=64 |
|---|---|---|---|---|---|---|---|---|
| 64 | 18 | 150k | 2.1 s | 0.96 / 0.96 | 1.00 / 1.00 | 1.00 / 1.00 | 0.93 / 1.00 | — |
| 128 | 10 | 148k | 1.6 s | 0.96 / 0.96 | 1.00 / 1.00 | 1.00 / 1.00 | 0.93 / 1.00 | 0.0052 |
| 256 | 5 | 147k | 1.7 s | 0.96 / 0.96 | 1.00 / 1.00 | 1.00 / 1.00 | 0.93 / 1.00 | 0.0053 |
| 512 = 1024 | 4 | 79k | 1.4 s | **failed**: all 500 rows, `max_tokens_exceeded` | 1.00 / 1.00 | 1.00 / 1.00 | 0.93 / 1.00 | 0.0037 (3 tests) |

- **Up to 256 rows per request, pack size makes no measurable difference.** Drift against pack 64 stays
  at the noise floor (0.0049), and every pass/fail decision is identical. That includes the one known
  difference from pack=1, ticket 131.
- **A whole test in one request is fine when it fits.** At pack ≥ 512, returns (139 rows), tickets (177)
  and reviews (241) each went out as a single request and scored exactly as at pack 64.
- **The only failure is the token ceiling.** 500 customer rows in one request exceed 64k tokens. The API
  rejects the whole request, all 500 rows come back without a value, and the run reports errors. It
  never passes silently. In this project a `nested` row costs about 140 tokens, because each question
  repeats the question text and criteria next to its record. So roughly 450 short rows fit in one
  request, and fewer when the texts are long.
- **Returns diminish past about 64 rows.** From 64 to 256, requests fall 18 → 5, but tokens barely move
  (150k → 147k) and wall time only drops about 2.1 → 1.7 s.

## Reproducing

```bash
uv run python scripts/pack_bench.py run --style single --pack 1 --tag a
uv run python scripts/pack_bench.py run --style nested --pack 32 --tag sEmpty
uv run python scripts/pack_bench.py run --style nested --pack 256 --tag sEmpty
uv run python scripts/pack_bench.py report
```

Two things to know when reading the saved runs:

- The `inline_*_a` and `nested_*_a` files were made while the shared state was still the
  "Data-quality check…" note. Runs tagged `sEmpty` use the empty state that is now the default. Pass
  `--shared '<json>'` to try another shared state.
- `flat`, `anchored` and the question-first variant were tried during the investigation and then
  removed from `packing.py`. Their saved runs stay in `eval/pack_bench/` as evidence, but the
  benchmark can no longer produce new ones.

## Open item

Packs are cut by row count. A pack that goes over Jev's per-request budget (64k tokens across the state
and all questions; 32k for the state plus the longest question) fails as a whole. That is exactly what
happens to the 500-row customers request above. Accuracy doesn't limit the pack size; tokens do. So a
production setup should cut packs by an estimated token budget as well as a row cap, and put a row
that is too long on its own into a request by itself.
