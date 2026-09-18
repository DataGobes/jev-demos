# semsql

Semantic SQL in DuckDB: plain-English judgments become typed SQL columns, powered by
[TypeSafe](https://typesafe.ai) Jev. Ask for anger, urgency, refund intent, or a
free-form question directly in a `WHERE` or `SELECT` clause — no separate NLP pipeline.

```sql
SELECT id, body, jev_score(body, 'anger') AS anger
FROM reviews
WHERE jev_noul(body, 'The customer is asking for their money back') > 0.8
ORDER BY anger DESC LIMIT 10;
```

While the query runs, a live panel shows rows scored, rows/s, requests, input tokens,
cost, and cache hits. Change the English, re-run, get a new answer.

## Install & run

```bash
uv sync
export TYPESAFE_API_KEY=...        # omit to run in demo mode
uv run semsql gen --rows 10000     # load synthetic reviews
uv run semsql                      # REPL
```

`uv run semsql -c "SELECT count(*) FROM reviews"` runs one statement and exits.
Global flags: `--db`, `--pack`, `--concurrency`, `--rpm`, `--demo`/`--live`,
`--no-cache`, `--cache-path`, `--model`.

## SQL functions

| Function | Returns | Meaning |
| --- | --- | --- |
| `jev_noul(text, question)` | DOUBLE 0..1 | probability the statement/question holds for the text |
| `jev_score(text, rubric)` | DOUBLE 0..n-1 | position on a named rubric from `rubrics.toml` |
| `jev_score_levels(text, instructions, levels VARCHAR[])` | DOUBLE | ad-hoc rubric, no rubrics.toml entry needed |
| `jev_choice(text, instructions, options VARCHAR[])` | VARCHAR | chosen option |

NULL text returns NULL. The question/rubric/levels/options arguments must be constant
per query chunk — semsql groups rows by that value and scores each group together.

## Rubrics describe situations, not degrees

A good rubric level reads like a scene, not a number: "Open hostility: insults,
all-caps shouting, or explicit threats" — not "very angry (4/5)". Concrete situations
give Jev something to pattern-match against; bare intensity words don't. Edit or add
rubrics in `src/semsql/rubrics.toml`:

```toml
[anger]
instructions = "How angry does the writer of this text sound?"
levels = [
    "Neutral or pleasant tone; no sign of frustration or complaint.",
    "Mild frustration or disappointment is stated, but the writer stays polite.",
    "Clear irritation: blunt language, complaints repeated, or a terse demand.",
    "Open hostility: insults, all-caps shouting, swearing, or explicit threats.",
]
```

## Performance and cost

- Jev input tokens cost **$0.042 / 1M tokens**; output is free.
- The API allows **1,200 requests/min**, so `--pack 1` (one row per request, the
  accuracy-safe default) tops out around **20 rows/s**.
- `--pack N` packs N rows into one request to push past that ceiling, at the risk of
  cross-row interference. Don't just claim a pack size is safe — measure it:
  `uv run semsql eval-pack --sample 200 --pack 16` scores a sample at pack=1 and
  pack=16 (uncached, needs a live backend) and reports mean absolute difference,
  max difference, and flip rate at the 0.5 and 0.8 thresholds, so the throughput
  number in a demo is defensible.
- The cache is content-addressed by `(model, question, text)`. Re-running the same
  query costs nothing: 0 requests, $0.0000, all cache hits. Clear it with
  `.cache clear` in the REPL or `--no-cache` to disable it.
- **Put expensive UDF predicates after cheap filters.** `jev_*` calls are the
  slowest, priciest part of a query — filter with ordinary SQL first, then judge only
  what's left:

  ```sql
  WITH candidates AS (
      SELECT * FROM reviews WHERE stars <= 2
  )
  SELECT id, body, jev_score(body, 'anger') AS anger
  FROM candidates
  WHERE jev_noul(body, 'asking for a refund') > 0.8;
  ```

## Demo mode

Without `TYPESAFE_API_KEY`, semsql runs on `DemoBackend`: a deterministic, offline
heuristic that never calls the network. It's clearly labeled everywhere — a bold
`SIMULATED — no TYPESAFE_API_KEY, judgments are fake` badge in the live panel and the
REPL banner — so a demo-mode recording can never pass for the real thing. Force it
explicitly with `--demo`, or force the real backend with `--live` (errors immediately
if the API key isn't set).

## Recording script

1. Load the data:
   ```sql
   -- semsql gen --rows 10000
   ```
2. Keyword baseline (misses semantic refund intent):
   ```sql
   SELECT count(*) FROM reviews WHERE body ILIKE '%refund%';
   ```
3. Semantic query with a cheap pre-filter, live panel visible:
   ```sql
   WITH candidates AS (SELECT * FROM reviews WHERE stars <= 2)
   SELECT id, body, jev_score(body, 'anger') AS anger
   FROM candidates
   WHERE jev_noul(body, 'The customer is asking for their money back') > 0.8
   ORDER BY anger DESC LIMIT 10;
   ```
4. Edit the English and re-run:
   ```sql
   WITH candidates AS (SELECT * FROM reviews WHERE stars <= 2)
   SELECT id, body, jev_score(body, 'anger') AS anger
   FROM candidates
   WHERE jev_noul(body, 'The customer is threatening to leave for a competitor') > 0.8
   ORDER BY anger DESC LIMIT 10;
   ```
5. Re-run step 3 again — all cache hits, 0 requests, $0.0000.
