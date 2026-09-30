# Jev semantic dbt tests on dbt-databricks + Unity Catalog — design

Date: 2026-09-30 · Status: approved in chat (sections 1–3), executing · Repo: `~/Projects/jev-demo-5`
Predecessor: demo 04, `~/Projects/jev-demo-4` (published as `04-dbt-semantic-tests/`).

## 1. What this is

Demo 04 ran four `jev_expect` semantic tests on a local DuckDB jaffle_shop through a Python plugin
inside the dbt process. Demo 05 takes the same tests to a production-like Databricks setup:

- The Jev call is a **Unity Catalog Python function** (`jev_demo.jev.noul_pack`): governed,
  permissioned, callable from SQL. The TypeSafe key is a **UC secret** that only the function reads.
  The key never leaves Databricks: no `.env` with the key, and whoever runs dbt never holds it.
- For a dbt user nothing changes: the same `jev_expect` blocks in `schema.yml` as demo 04
  (`name`, `arguments: fails_if / context / threshold / criteria`, `config: severity /
  store_failures / tags`). Tests stay ordinary dbt tests: a SELECT returning failing rows, which
  `store_failures` writes.
- Two runs:
  - the **yardstick run**, on demo 04's exact data, golden key and regex baselines, so the numbers
    are directly comparable;
  - the **production run**, on ~100k real product reviews (Amazon Fine Food Reviews) with planted
    star flips, on a production-sized serverless warehouse.

Deliverable: a public demo repo and a repeatable terminal recording (same shape as demo 04), later
imported into `jev-demos` as `05-dbt-databricks/`. It is not a package.

## 2. Decisions taken in the brainstorm

| Decision | Choice |
|---|---|
| Where Jev runs | UC Python function, `LANGUAGE PYTHON`, `SECRETS (...)`, `ENVIRONMENT (environment_version = '6')`, stdlib `urllib` only |
| Architecture | **B**: UC function + Delta judgments table (cache and ledger). A (inline in the test, no cache) and C (Python job, not callable from SQL) were rejected |
| Where judging happens | project-level **post-hook** `jev_judge()` on models; tests are plain SELECTs over the judgments table |
| Compute | serverless SQL warehouse, PRO. Dev: `jev-demo-5` (2X-Small, the dev warehouse; looked up by name, its id is never committed). Production run: `jev-demo-5-prod` (Small, created when needed) |
| Workspace | an Azure Databricks workspace (Premium), CLI/dbt profile `jev-demo-5`, OAuth U2M; the host comes from the profile and is never committed |
| Catalog | `jev_demo` on the catalog's own managed storage (its own storage credential and external location); never the metastore root, which points at a deleted storage account |
| Key | UC secret `jev_demo.jev.typesafe_api_key`, created by the user; Claude only references it by name |
| Layout | `nested` with empty shared state `""`, record first, question last (demo 04 `docs/pack-layouts.md`) |
| Pack cutting | by estimated tokens (budget 48k) **and** a row cap (256), not by row count alone |
| Model | pinned `jev-1.13.0` (var), not the `jev-latest` alias |
| Deliverable | repo + recording, like demo 04 |
| Production dataset | Amazon Fine Food Reviews (SNAP/Stanford; Kaggle lists CC0), ~100k sampled, planted star flips |
| Audit labels | the **user** labels ~100 flagged-but-unplanted rows, blind to `jev_p` |
| Pins | Python 3.13, uv, `dbt-databricks==1.12.5`, which caps dbt-core below 1.12.4 (so dbt-core 1.12.3, not demo 04's 1.12.5), `databricks-sdk` as resolved. dbt Fusion is not used, as in demo 04 |

## 3. Spike results (2026-09-30, live, in `jev_demo.spike`, throwaway)

| Probe | Result |
|---|---|
| Can a UC Python function call api.typesafe.ai from serverless SQL with a UC secret? | **Yes**, after enabling the workspace preview "Enable networking for isolated workloads in Serverless SQL Warehouses". 2-row pack → [0.03, 0.95], 502 tokens, `jev-1.13.0`, 23 s wall incl. sandbox cold start |
| `EXPLAIN FORMATTED` of the test-shaped query | exactly **one** `ArrowEvalPython` node; the `p >= threshold` filter sits above the explode. No DuckDB-style double evaluation |
| One 256-row customers pack | 34,552 tokens, **0.7 s** in Jev, mean \|Δp\| 0.0074 vs demo 04's saved pack-256 run, max 0.03, 0 threshold flips |
| 10 × 256-row packs, `REPARTITION(10)` | peak **8** concurrent packs on 2X-Small, 346,612 tokens in 1.3 s, **0** 429s, 13.5 s query wall (warm) |

Consequences:
- The function is Arrow-batched (`ArrowEvalPython`): packs in one partition run sequentially, so
  `REPARTITION(n)` is the concurrency knob.
- Query overhead (13–27 s per statement) dominates wall time; Jev time is ~0.7 s per full pack.
- The retry path was not exercised live (no 429 at ~265k tokens/s), so it is proven offline only.
- The sandbox reports an empty hostname and pid 1, so concurrency is measured from call timestamps.

## 4. Repo layout

```
jev-demo-5/
  pyproject.toml            uv project, package `jevdbx` under src/
  src/jevdbx/
    noul_pack.py            the UC function's Python body, a real module (single source of truth)
    demo_values.py          deterministic hash values for SIMULATED mode (port of demo 04 DemoBackend)
    deploy.py               renders CREATE SCHEMA/TABLE/VIEW/FUNCTION SQL from the modules above
    databricks.py           tiny Statement Execution API client (databricks-sdk, profile jev-demo-5)
    pricing.py              PRICE_PER_MTOK_USD with a link to docs.typesafe.ai/models
  jaffle_shop/
    dbt_project.yml         +post-hook jev_judge(); on-run-end jev_summary(); vars
    profiles.yml            dbt-databricks, http_path of the warehouse, auth_type oauth
    macros/jev_expect.sql   the generic test (same arguments and validation as demo 04)
    macros/jev_judge.sql    post-hook: judge missing states for this model's jev_expect tests
    macros/jev_question.sql shared: question JSON, state expression, cache key (used by both)
    macros/jev_summary.sql  on-run-end summary line + once-per-row counters
    models/staging/         copied from demo 04 (SQL ported to Spark where needed)
    models/production/      stg_product_reviews (body, stars) over the production volume/table
    seeds/                  copied from demo 04 (regenerated by make_seeds.py, identical)
    tests/baseline/         demo 04 baselines ported to Spark SQL
  scripts/
    make_seeds.py, pools/   copied from demo 04 (seed=42)
    deploy.py               CLI: prints or (with --apply) runs the platform DDL, confirm-first
    fetch_reviews.py        download (after asking) + sample 100k + strip + plant flips
    audit_sample.py         writes the blind audit CSV (review + stars only)
    score.py                scorecard: yardstick (golden key) and production (flips + audit)
    record.sh, show.py      recording, demo 04 style
  eval/
    golden_defects.csv      copied from demo 04, unchanged
    production_flips.csv    review ids + original/new stars of planted flips (no text)
    production_audit.csv    the user's blind labels
  docs/
    eval-results.md         every scored live run, next to demo 04's numbers
    superpowers/specs, superpowers/plans
  tests/                    pytest
```

## 5. Unity Catalog objects

| Object | Purpose | Created by |
|---|---|---|
| schema `jev_demo.jev` | the "platform" part | `scripts/deploy.py --apply` (confirm-first) |
| function `jev_demo.jev.noul_pack(records ARRAY<STRING>, question STRING, model STRING) RETURNS STRING` | live Jev call, one pack per call, JSON result | deploy |
| function `jev_demo.jev.noul_pack_demo(records ARRAY<STRING>, question STRING, model STRING) RETURNS STRING` | SIMULATED: same contract, hash values, no network, no secret | deploy |
| secret `jev_demo.jev.typesafe_api_key` | the TypeSafe key | **the user** |
| table `jev_demo.jev.judgments` (Delta) | cache + ledger | deploy |
| view `jev_demo.jev.requests` | one row per pack | deploy |
| table `jev_demo.jev.hook_runs` (Delta) | one row per (invocation, test): tested, missing, oversized, inserted, mode, model | deploy |
| schema `jev_demo.jaffle_shop`, `jev_demo.jaffle_shop_dbt_test__audit` | dbt models, stored failures | dbt |
| schema `jev_demo.production` + volume `raw` | production reviews (source files) | deploy (confirm-first) |

`jev_demo.spike` is dropped once `jev_demo.jev` exists (confirm-first).

The function runs with its owner's rights. Callers need `EXECUTE` on it; nobody else needs
`READ SECRET`. Production note (README): the owner should be a service principal or group.

### 5.1 Function contract

Input: `records` = JSON strings (one per row, the state object), `question` = the JSON the macro
builds (`{"instructions": ..., "criteria": {"true": ..., "false": ...}}` with column references
already rewritten to `` `record.<col>` ``). Output: a JSON string

```json
{"values": [0.03, 0.95], "input_tokens": 502, "model": "jev-1.13.0", "error": null,
 "attempts": 1, "retries": [{"attempt": 1, "status": 429, "t": 1790000000.1}],
 "pack_uuid": "…", "started": 1790000000.0, "finished": 1790000000.7}
```

- The request is `{"model": <pinned>, "state": "", "questions": {"r000": {"type": "noul",
  "instructions": {"record": {...}, "question": "..."}, "criteria": {...}}, ...}}`.
- `model` is the third argument, so the dbt var `jev_model` (default `jev-1.13.0`) controls it
  and it is part of the cache key.
- Retries: 429, 529, other 5xx and connection errors/timeouts, up to 6 attempts, jittered
  exponential backoff (1.5 s × 2^(n−1), max 20 s, × U(0.5, 1.5)), honouring `retry-after`.
  4xx other than 429 is not retried.
- On final failure: `values = null`, `error = "HTTP <code>: <body[:300]>"` or the exception type.
  **Never** the request, headers or key. A test asserts the key string never appears in any output.
- The module `src/jevdbx/noul_pack.py` defines `handler(records, question, model, *, get_key,
  urlopen, sleep, now, uuid4)`; the deployed body is the module source plus a two-line shim that
  binds those to `databricks.secrets.get`, `urllib.request.urlopen`, `time.sleep`, `time.time`,
  `uuid.uuid4`. pytest injects fakes.
- `noul_pack_demo` has the same output shape with `model = "demo:<requested model>"`, `input_tokens` estimated as
  demo 04 did (`len(state)//4 + 40` per row), values `hash_unit(question_key, state) ** 6`.

## 6. Data flow

```text
dbt build
 ├─ model M builds → post-hook jev_judge():
 │     tests = jev_expect tests attached to M (from graph.nodes; none → no-op)
 │     one INSERT INTO jev_demo.jev.judgments per test:
 │       states  = SELECT DISTINCT <state expr> FROM M WHERE <column> IS NOT NULL
 │       misses  = states LEFT ANTI JOIN judgments (successful rows) ON key
 │       sized   = est_tokens per row, running sum → pack_id (budget) and row cap
 │       packs   = /*+ REPARTITION(n) */ collect_list(struct(key, state)) GROUP BY pack
 │       called  = <function>(transform(items, x -> x.state), question, model)
 │       rows    = explode back to one row per key with the pack metadata
 └─ jev_expect test on M → SELECT M.*, j.p AS jev_p FROM M JOIN judgments j ON j.key = <key expr>
                          WHERE j.p >= threshold
```

- **Key:** `sha2(concat_ws('\u001f', requested_model, mode, layout, question_json, state), 256)`.
  The state expression, question JSON and key expression come from one macro
  (`jev_question.sql`) shared by the hook and the test, so they cannot drift.
- **Successful rows are the cache:** a key with `p IS NOT NULL` is never judged again. Error rows
  stay in the table (audit) and count as misses next run.
- **Test guard:** if any tested row has no successful judgment for this question, the test
  returns those rows with `jev_p = NULL` and the summary says `N unjudged — run dbt build`.
  That covers "sentence changed, only `dbt test` was run". It never silently passes.
- **Hooks and selection:** `dbt build --select +tag:semantic` builds the tested models (hooks run)
  and then the tests. Models without `jev_expect` tests get a no-op hook (renders to nothing).
- **Concurrency of dbt threads:** hooks of different models append disjoint keys; Delta blind
  appends do not conflict.

### 6.1 Judgments table

```sql
CREATE TABLE IF NOT EXISTS jev_demo.jev.judgments (
  key STRING, test_name STRING, model_name STRING, question STRING, state STRING,
  p DOUBLE, requested_model STRING, answered_model STRING, mode STRING, layout STRING,
  pack_uuid STRING, pack_rows INT, pack_tokens BIGINT, pack_est_tokens BIGINT,
  attempts INT, retry_statuses ARRAY<INT>, error STRING,
  started_at TIMESTAMP, finished_at TIMESTAMP, invocation_id STRING, judged_at TIMESTAMP
) CLUSTER BY (key)
```

`jev_demo.jev.requests` = one row per `pack_uuid` (rows, tokens, est tokens, attempts, error,
timestamps, invocation_id, mode, answered_model).

`jev_demo.jev.hook_runs` (amended 2026-09-30): the hook counts tested and missing states before its
INSERT and inserted rows after it, writes one row per (invocation_id, test_name), and raises if
inserted ≠ missing (every missing state, oversized ones included, gets exactly one row). The
summary line reads `hook_runs` and `requests` for the invocation, so it also works when every row
was cached and nothing was inserted.

## 7. Packing and token budget

- Per-row estimate: `ceil((length(state) + length(question_instructions_and_criteria)) / 3.0)
  + 20`. The spike measured ~3.3 characters per token, so 3.0 overestimates. Each pack logs
  `pack_est_tokens` and actual `pack_tokens`; `eval-results.md` reports the ratio per run.
- Budget `var('jev_pack_token_budget', 48000)` (hard limit 64k), row cap
  `var('jev_pack_max_rows', 256)` (the largest size demo 04 validated for accuracy).
- Assignment: `cum = sum(est) OVER (ORDER BY key)`, `bucket = floor((cum - est) / budget)`, then
  `pack = (bucket, floor((row_number() OVER (PARTITION BY bucket ORDER BY key) - 1) / max_rows))`.
  Starting a row's bucket at `cum - est` puts it where it begins, so a bucket exceeds the budget
  by at most one row; the 16k margin absorbs that.
- A row with `est > var('jev_row_token_limit', 30000)` is not sent: it is inserted with
  `p = NULL, error = 'row exceeds token limit (est N)'` and reported. It is never a silent pass.
- Accuracy: demo 04 showed no measurable change up to 256 rows per request with `nested`/`""`;
  the spike reproduced demo 04's pack-256 values within 0.0074 mean |Δ|.

## 8. Rate limits

TypeSafe: 1,200 requests/min, 250k tokens/s, 64k tokens/request, all "adjusting dynamically".

- Requests will not bind (100k review rows ≈ 600–800 packs). Tokens/s will: 8 concurrent 48k
  packs ≈ 380k tokens/s.
- Layer 1: `REPARTITION(n)`, `n = var('jev_max_concurrency', 4)`, caps concurrent packs.
- Layer 2: in-function retry with backoff on 429/529/5xx (§5.1). Each pack records attempts and
  statuses; the summary shows the number of 429s.
- There is no global pacer across executors. The server's 429 is the coordination signal. The
  spec and README say so; the production run reports whether 429s occurred.

## 9. One evaluation per row

- Structural: a hook runs once per model build. The INSERT evaluates the function once per pack:
  an integration test asserts `EXPLAIN` of the generated INSERT contains exactly one
  `EvalPython` operator.
- Counted per invocation (on-run-end, printed with the summary, failing loudly if violated):
  1. rows inserted = distinct missing states (counted by the hook before the insert, stored in
     `hook_runs`, checked by the hook itself right after the insert),
  2. Σ `pack_rows` over the invocation's packs = rows inserted,
  3. every successful key appears exactly once in `judgments`.
- Residual gap, stated honestly: a Spark task retry whose first attempt already reached Jev is
  invisible from inside the function. External check: `requests` tokens for the production run
  vs the TypeSafe usage page for that day, logged in `eval-results.md` (the user reads the
  TypeSafe page; Claude never logs in there).

## 10. Secrets and SIMULATED mode

- Live mode needs only the UC secret. dbt authenticates to Databricks with OAuth; no token in the
  repo, no `.env` with the TypeSafe key. The workspace host and warehouse HTTP path come from
  environment variables (`DATABRICKS_HOST`, `JEV_HTTP_PATH`), printed by `scripts/jev_env.py` from
  the CLI profile `jev-demo-5` (host and warehouse only, never tokens), so the public repo does
  not name the workspace.
- `JEV_MODE=demo` (dbt var `jev_mode`, default `live`) switches the hook to
  `noul_pack_demo`. Demo rows carry `mode = 'demo'` in the key and the table, so they are never
  served as live cache hits.
- Every summary line shows `LIVE` or `SIMULATED`. `score.py` prints `SIMULATED` on the scorecard
  and refuses `--append` for a simulated run. No simulated number is reported, screenshotted or
  logged as a result.

## 11. Summary line and cost

```
Jev · 1,057 judgments · 0% cached · 5 requests · 0 retries · 1.3 s Jev · $0.006 · LIVE jev-1.13.0 budget=48k
Jev · once-per-row: 1,057 inserted = 1,057 missing · packs sum 1,057 · 0 duplicate keys
```

- `judgments` = tested rows with a successful judgment for this invocation's tests; `cached` = share
  that were not inserted this invocation; `requests` = packs this invocation; `s Jev` = span of
  pack timestamps (wall, not summed).
- Jev cost = input tokens × $0.042 per million (constant in `src/jevdbx/pricing.py`, link to
  docs.typesafe.ai/models).
- Warehouse cost: DBUs from `system.billing.usage` for the warehouse id and the run's time window,
  once the `system.billing` schema is enabled (confirm-first). Logged, not printed on camera.

## 12. Datasets

### 12.1 Yardstick (demo 04 data)

`scripts/make_seeds.py` and `scripts/pools/` copied; the regenerated seeds must be byte-identical
to demo 04's (a test asserts it). `eval/golden_defects.csv` copied unchanged. The four `jev_expect`
blocks are copied verbatim (sentences, context, thresholds, criteria). Staging SQL is ported to
Spark only where the dialect differs (a test compares its row counts and key columns to demo 04).
Note: Spark's `to_json` omits NULL fields where DuckDB wrote `null`; tested and context columns
are non-null in every seed, so states are identical.

### 12.2 Production (Amazon Fine Food Reviews)

- Source: SNAP / Stanford (McAuley & Leskovec, WWW 2013), 568,454 reviews, 1999–2012. Kaggle
  lists it as CC0. Licence confirmed at the source before download; citation in the README.
- `scripts/fetch_reviews.py`: downloads only after the user approves (filename, source, size
  stated), keeps `Id`, `Score`, `Summary`, `Text` (drops `UserId`, `ProfileName`, helpfulness,
  time), samples 100,000 with seed 42, splits 95,000 + 5,000 (incremental proof).
- Planted defects: ~3% of rows with original stars in {1, 2, 4, 5} get flipped across the pole
  (1↔5, 2↔4), seed 42. `eval/production_flips.csv` = `id, original_stars, planted_stars` (no text).
  3-star reviews are never flipped (their mismatch is ambiguous).
- Production models are disabled unless `--vars '{production: true}'`, so yardstick commands
  never touch the volume.
- Loaded as Parquet into volume `jev_demo.production.raw`, exposed by
  `models/production/stg_product_reviews.sql` as `review_id, stars, body` (body = summary +
  text), so the demo 04 reviews sentence applies unchanged:
  `reviews_body_matches_stars` with the same `fails_if`, `context: [stars]`, threshold 0.8 and
  criteria.
- The data files are gitignored (`data/`); only the scripts and the flips key are committed.

## 13. Scoring and gates

### Yardstick run (the gate from demo 04, unchanged)

Live, no errors; Jev precision ≥ 0.85 and recall ≥ 0.85 on every test; Jev F1 > regex baseline
F1 on every test. The scorecard also prints demo 04's logged numbers for the same pack layout
next to this run (requests, wall, cost). Failing the gate: same order as demo 04 (question
wording or threshold first, logged; golden key only if demonstrably wrong, logged; else drop or
reframe). The golden key, pools and baselines are never edited to make Jev win.

### Production run

- Recall on planted flips ≥ 0.85.
- Audited precision ≥ 0.85: flagged rows = planted TPs + audited sample of flagged-but-unplanted
  rows (the user labels ~100, blind to `jev_p`, via `scripts/audit_sample.py`); precision
  extrapolates the sample's "real mismatch" share to all unplanted flags, with a 95% Wilson
  interval. Raw precision against planted flips only is also reported.
- F1 above the demo 04 review lexicon baseline, ported to Spark SQL, not tuned.
- Operational: 0 errors after retries; the three once-per-row checks pass; ledger tokens vs
  TypeSafe bill logged; rerun makes **0** requests; +5,000 new rows judges exactly 5,000.

Every scored live run is appended to `docs/eval-results.md` with date, warehouse, budget,
requests, retries, tokens, Jev cost, DBUs, wall time and the numbers.

## 14. Recording (`scripts/record.sh`, demo 04 style)

1. `dbt build --exclude tag:semantic`: all green, on Databricks. *"Same project. Now on Databricks."*
2. The `jev_expect` blocks in `schema.yml`, identical to demo 04. *"Same sentences."*
3. `DESCRIBE FUNCTION EXTENDED jev_demo.jev.noul_pack`. *"Jev is a governed function; the key never leaves Databricks."*
4. `dbt build --select +tag:semantic`: WARN counts + summary line.
5. Failing rows with `jev_p` (`scripts/show.py`).
6. Scorecard: Jev vs regex baseline, and vs demo 04.
7. Production: 100k real reviews, summary (packs, tokens/s, cost); rerun → 0 requests.

Only numbers from logged live runs appear on screen. `record.sh` has a demo-mode smoke test
(`JEV_MODE=demo`), never used as the recording.

## 15. Testing

TDD with pytest, ruff, uv.

- Offline (default `pytest`): `noul_pack` (request shape, criteria, column rewrite already
  applied, retries on 429 + `retry-after`/529/5xx/timeouts, no retry on 400/401/422, give-up
  shape, key never in any output or exception text, pack_uuid, timestamps); demo values
  (deterministic, shape); deploy SQL rendering (function body round-trips the module source,
  `SECRETS` and `ENVIRONMENT` clauses present, demo function has no `SECRETS`); dbt project
  (`dbt parse` succeeds offline, the four `jev_expect` blocks equal demo 04's, the post-hook and
  vars are set, macro argument validation errors); seeds byte-identical to demo 04; score logic
  (precision/recall/F1, Wilson interval, SIMULATED refusal); fetch/plant logic on a small fixture
  (deterministic, 3-star never flipped, only 1↔5 / 2↔4, PII columns dropped).
- Integration (marker `databricks`, deselected by default, **demo mode only**, run only with the
  user's OK because it costs warehouse time): end-to-end `dbt build` on the dev warehouse; the
  three once-per-row counters; `EXPLAIN` has one `EvalPython`; rerun makes 0 requests; oversized
  row handling; the Spark-ported baselines flag the same rows as demo 04's DuckDB baselines;
  staging models match demo 04's row counts.
- `ruff check` clean.

## 16. Confirm-first operations

Standing OK (user, 2026-09-30): any query on the 2X-Small `jev-demo-5` warehouse, including
deploying `jev_demo.jev` objects and demo-mode integration runs.

Still confirm-first: every **live** Jev run (TypeSafe billing); the production schema/volume
upload and `jev-demo-5-prod`; dropping `jev_demo.spike`; enabling `system.billing`; the dataset
download. The user creates the secret.

## 17. Out of scope

Publishing to jev-demos until asked; Score/Choice variants; grants for other users beyond the
README note; dbt Fusion; a global cross-executor pacer; LinkedIn copy.
