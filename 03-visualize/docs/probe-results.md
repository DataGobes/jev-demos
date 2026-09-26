# Probe results: Jev question-count limits

**Date:** 2026-09-21
**Model string:** `jev-latest` (default passed by `JevBackend.__init__`)
**SDK version:** `typesafe-sdk` 0.7.1
**Script:** `scripts/probe_questions.py` (throwaway)

## Method

Ran `uv run python scripts/probe_questions.py` three times, a few seconds apart,
against the live TypeSafe API with a real key loaded via `load_dotenv()`. Each
run issues one `judge()` call per n in `(1, 24, 48, 72, 144)`, with a fixed
STATE payload and score-question set as specified in the task brief.

## Raw output

### Run 1

```
n=   1  answered=   1      739 ms  tokens=482  error=None
n=  24  answered=  24      270 ms  tokens=3398  error=None
n=  48  answered=  48      252 ms  tokens=6450  error=None
n=  72  answered=  72      306 ms  tokens=9502  error=None
n= 144  answered= 144      468 ms  tokens=18702  error=None
```

### Run 2

```
n=   1  answered=   1      628 ms  tokens=482  error=None
n=  24  answered=  24      267 ms  tokens=3398  error=None
n=  48  answered=  48      328 ms  tokens=6450  error=None
n=  72  answered=  72      310 ms  tokens=9502  error=None
n= 144  answered= 144      625 ms  tokens=18702  error=None
```

### Run 3

```
n=   1  answered=   1      649 ms  tokens=482  error=None
n=  24  answered=  24      221 ms  tokens=3398  error=None
n=  48  answered=  48      277 ms  tokens=6450  error=None
n=  72  answered=  72      293 ms  tokens=9502  error=None
n= 144  answered= 144      629 ms  tokens=18702  error=None
```

## Per-n median latency (of the 3 runs)

| n   | latencies (ms)      | median (ms) | input_tokens | answered == n (all 3 runs) | errors |
|-----|----------------------|-------------|---------------|------------------------------|--------|
| 1   | 739, 628, 649         | 649         | 482           | yes                          | none   |
| 24  | 270, 267, 221         | 267         | 3398          | yes                          | none   |
| 48  | 252, 328, 277         | 277         | 6450          | yes                          | none   |
| 72  | 306, 310, 293         | 306         | 9502          | yes                          | none   |
| 144 | 468, 625, 629         | 625         | 18702         | yes                          | none   |

`input_tokens` was identical across all 3 runs for a given n (the SDK reports
tokens for a deterministic prompt), so only one value is listed per n.

## Errors

None. No run at any n produced a non-`None` `error` field, and no exception
was raised (the script's per-n `try/except Exception` fallback path was never
triggered).

## Latency vs. question count

Latency does **not** grow linearly with n across the full range tested.
n=1 has the highest latency of the small-n group (median 649 ms) — consistent
with fixed per-request overhead (e.g. connection setup) dominating at low
question counts. From n=24 through n=72, median latency stays roughly flat
(267–306 ms), i.e. tripling the question count (24 -> 72) did not noticeably
increase latency. Only at n=144 does latency rise sharply, to a median of
625 ms — roughly double the n=24–72 plateau, for a 2–6x increase in question
count. So the shape is: high fixed cost at n=1, a flat plateau through
n=24–72, then a step up at n=144 — not a single linear relationship over the
whole range. This matters for a later batching decision: for the n=24–72
range, latency cost of batching more questions into one request is close to
free; the jump only appears once the batch reaches roughly 144 questions.

## Decision

All five n values (1, 24, 48, 72, 144) answered every question with no error
in all three runs. 144 is the largest n tested, so per the brief's rule (the
largest n that answered every question with no error in all three runs):

```
MAX_QUESTIONS_PER_REQUEST = 144
```

Note: this only confirms the tested ceiling of 144; it does not establish
where the true upper limit lies above 144, since no larger n was probed.
