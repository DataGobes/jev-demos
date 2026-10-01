# jev-demo-5 — semantic dbt tests on Databricks

Demo 04 ran four `jev_expect` dbt tests, plain English sentences in `schema.yml`, on a local
DuckDB through a Python plugin. This demo takes the same tests to a production-like Databricks
setup. The Jev call is a **Unity Catalog Python function**, the TypeSafe key is a **UC secret**
that only that function can read, and a dbt user sees no difference: the same `jev_expect` blocks,
the same flagged rows with a probability `jev_p`, ordinary dbt tests underneath.

Fifth in the Jev demo series (Cringe-o-Meter, semsql, VISUALIZE, dbt semantic tests). A demo
repo, not a package.

Two runs:

- the **yardstick run**: demo 04's exact data, golden answer key and regex baselines, so the
  numbers compare directly with demo 04;
- the **production run**: a planned sample of 50,000 real product reviews (Amazon Fine Food Reviews) with planted
  star flips, on a production-sized serverless warehouse.

## The test, as written

Unchanged from demo 04 (the sentences, `context`, thresholds and `criteria` are byte-for-byte the
same, and a test checks it):

```yaml
- name: comment
  data_tests:
    - not_null
    - jev_expect:
        name: returns_comment_matches_reason_code
        arguments:
          fails_if: "The customer's `comment` describes a different main reason for the return than `reason_code` (damaged, wrong_item, late, changed_mind, other)."
          context: [reason_code]
          threshold: 0.8
          criteria:
            "true": "The stated main reason plainly belongs to another code"
            "false": "Consistent with the code, or too vague to tell; code 'other' fits anything unusual"
        config: {severity: warn, store_failures: true, tags: [semantic]}
```

The semantic tests run at `severity: warn`: a probabilistic judgment flags rows for someone to
review, it does not stop a pipeline. Flagged rows are stored in
`jev_demo.jaffle_shop_dbt_test__audit` with their `jev_p`.

## How it works

```text
dbt build
 ├─ model M builds → post-hook jev_judge():
 │     tests = jev_expect tests attached to M (none → no-op)
 │     one INSERT INTO jev_demo.jev.judgments per test:
 │       states  = SELECT DISTINCT <state> FROM M WHERE <column> IS NOT NULL
 │       misses  = states LEFT ANTI JOIN judgments (this question, successful rows) ON key
 │       packs   = misses cut by estimated tokens (budget 48k) and a row cap (256)
 │       called  = jev_demo.jev.noul_pack(records, question, model)   -- one call per pack
 │       rows    = exploded back to one row per key, with the pack metadata
 └─ jev_expect test on M → SELECT M.*, j.p AS jev_p FROM M JOIN judgments j ON j.key = <key>
                          WHERE j.p >= threshold
```

- **The function.** `jev_demo.jev.noul_pack(records ARRAY<STRING>, question STRING, model STRING)`
  is a Python UDF (`SECRETS (...)`, stdlib `urllib` only). Its body is the module
  `src/jevdbx/noul_pack.py`, embedded verbatim by `scripts/deploy.py`, so pytest tests the code
  that runs. It retries 429/5xx with jittered backoff (`retry-after` is a floor, capped at 60 s)
  and never puts the key, headers or request in any output. `noul_pack_demo` is the SIMULATED
  twin: same shape, hash values, no network, no secret.
- **The judgments table is the cache and the ledger.** A successful row (`p IS NOT NULL`) is never
  judged again; the key is a hash of model, mode, layout, question and state. Error and unjudged
  rows stay for audit. The hook and the test build the question, state and key from one macro
  (`jaffle_shop/macros/jev_question.sql`), so they cannot drift.
- **Packing.** Rows go to Jev in `nested` packs (each row carries its own question, shared state
  empty), cut by estimated tokens under the 64k-per-request limit. `REPARTITION(4)` caps the packs
  in flight per statement.
- **One evaluation per row.** The hook counts missing states before its INSERT and rows inserted
  after it; the summary checks that inserted = missing, that the packs' rows sum to the rows
  inserted, and that no key appears twice. A violation fails the run. The physical plan shows a
  single `PhotonScalarUDF` after the pack aggregation.
- **When it judges.** The hook judges only the `jev_expect` tests that are selected in the
  invocation (dbt's `selected_resources`): `dbt build --select +tag:semantic`. A plain `dbt run`,
  or a build that excludes the tests, builds the models and never calls Jev. `dbt retry` does not
  judge either (dbt leaves `selected_resources` empty on a retry): rerun
  `dbt build --select +tag:semantic`.
- **Never a silent pass.** If a tested row has no successful judgment (the sentence changed and
  only `dbt test` ran, a pack failed), the test returns it with `jev_p = NULL`, so it shows up as a
  failing row. After a `dbt build` the summary line also counts it (`· U unjudged`); `dbt test`
  prints no summary line (the summary reads the judging hook's ledger, and only a build judges).
- **Provenance on every flagged row.** Each stored-failure row carries `jev_mode` (live|demo) and
  `jev_invocation_id`. In a `dbt build` the tests and the judging hook share the invocation, so
  `scripts/score.py` and `scripts/show.py` refuse to present stored failures from another
  invocation or mode under a run's LIVE provenance.
- **LIVE or SIMULATED.** Every summary line says which. `JEV_MODE=demo` uses the demo function.

The summary line, after every build:

```
Jev · <N> judgments · <X>% cached · <R> requests · <r> retries (<t>× 429) · <s> s Jev · $<c> · LIVE jev-1.13.0 budget=48k
Jev · once-per-row OK · LIVE: <n> inserted = <n> missing · packs sum <n> (+<o> too long) · 0 duplicate keys
```

"N judgments" counts distinct (test, state) pairs with a successful judgment. Demo 04 called the
same quantity "unique" (it printed `1,300 judgments · 1,057 unique`), so compare demo 05's
judgments with demo 04's unique count.

## Prerequisites

1. **A Databricks workspace** on Premium with Unity Catalog, serverless SQL warehouses, and the
   Databricks CLI logged in (`databricks auth login --profile jev-demo-5`). The profile name is
   the only workspace detail the repo uses; host and warehouse path come from the profile
   (`scripts/jev_env.py`).
2. **A catalog on storage you control.** The demo uses the catalog `jev_demo`. If the metastore's
   root storage is unusable in your workspace, create a Unity Catalog storage credential and
   external location and a catalog with its own managed location (`CREATE CATALOG jev_demo
   MANAGED LOCATION '...'`), rather than relying on the metastore root.
3. **The preview "Enable networking for isolated workloads in Serverless SQL Warehouses"** (workspace
   admin, Previews). A UC Python function can reach `api.typesafe.ai` from a serverless SQL
   warehouse only with it on; without it the function fails on the network call.
4. **A serverless SQL warehouse** named `jev-demo-5` (2X-Small is enough for the yardstick run;
   the production run uses a larger one, see below).
5. **The platform objects**, and then the secret:

   ```bash
   uv sync
   eval "$(uv run python scripts/jev_env.py)"
   uv run python scripts/deploy.py                      # print the DDL first
   uv run python scripts/deploy.py --apply --only schema judgments hook_runs requests noul_pack_demo
   ```

   Create the TypeSafe key as a Unity Catalog secret **yourself**, from your own shell. The key
   never appears in a command line (where `ps` could show it), a file or your shell history: `read
   -s` takes it without echo, `jq` builds the request body from the environment, and the CLI reads
   that body from standard input. Nothing in this repo reads or stores it.

   ```bash
   read -rs TS_KEY && export TS_KEY
   jq -n '{name: "typesafe_api_key", catalog_name: "jev_demo", schema_name: "jev", value: env.TS_KEY}' \
     | databricks secrets-uc create-secret --json @/dev/stdin -p jev-demo-5 > /dev/null
   unset TS_KEY
   ```

   (`--json @/dev/stdin` is read by the CLI as a file; `> /dev/null` keeps the response off the
   screen.) Then deploy the live function, which references the secret by name:

   ```bash
   uv run python scripts/deploy.py --apply --only noul_pack
   ```

   The first thing to run after deploying it: one 2-row call of the function on the dev warehouse,
   printing its values, tokens, model and error (never the key). It is a live Jev call, billed by
   TypeSafe, so run it deliberately:

   ```bash
   uv run python scripts/deploy.py --smoke          # LIVE: one call of noul_pack
   uv run python scripts/deploy.py --smoke --demo   # the same call of noul_pack_demo (SIMULATED)
   ```

   (`deploy.py --apply` with no `--only` runs everything in that order; the last statement fails
   if the secret does not exist yet.) Whoever runs dbt needs `EXECUTE` on the functions and
   `SELECT`/`MODIFY` on the judgments tables; only the function's owner needs `READ SECRET`.

## Run it

dbt always goes through `scripts/dbtw.py`: it fills in `--profiles-dir . --target dev`, and gives
dbt a short-lived token from your logged-in CLI profile (environment variable
`DBT_ENV_SECRET_DATABRICKS_TOKEN`, scrubbed from dbt's logs, never printed, never a personal access
token). It also keeps the seed surname "Null" as text, as in demo 04; plain dbt-core would make it
NULL.

```bash
uv run python scripts/dbtw.py seed
# standard tests and the regex baselines (the semantic tests are tagged `semantic`); no Jev call
uv run python scripts/dbtw.py build --exclude tag:semantic
# the four jev_expect tests: models first (the post-hook judges), then the tests
uv run python scripts/dbtw.py build --select +tag:semantic
uv run python scripts/show.py rows        # flagged rows with their probability
uv run python scripts/score.py            # scorecard: Jev vs regex baseline, and vs demo 04
```

The default mode is live, which calls Jev and is billed by TypeSafe. With `JEV_MODE=demo`
everything runs against the SIMULATED function and says so on screen. A simulated number is a
wiring check and is never a result:

```bash
JEV_MODE=demo uv run python scripts/dbtw.py build --select +tag:semantic
```

### dbt inside Databricks

The same build can run as a serverless notebook job, deployed as a Databricks Asset Bundle
(`databricks.yml`, `notebooks/jev_semantic_tests.py`). The notebook installs the pinned
dbt-databricks, runs `dbt build` for the chosen `mode` (demo|live) and `selection`
(yardstick|production) against the SQL warehouse, then shows the summary and the flagged rows.
It authenticates with the notebook's own short-lived credential.

`action=results` (default `build`) makes no Jev call and runs no dbt. It reads the ledger
(`jev_demo.jev.hook_runs`) and shows, labelled LIVE, every live run that judged the rows on record
(a rerun judges nothing; N counts distinct states, not rows) with its states, requests, retries
and 429s, input tokens, Jev cost and span, a total, each run's entry of `docs/eval-results.md`
verbatim, and the failing rows of the latest live run when every stored row is that run's. Use it
to show a logged result on camera without judging. `mode` is ignored; with no live run it says so.

```bash
databricks bundle validate
databricks bundle deploy          # creates the job
databricks bundle run jev_semantic_tests --params mode=demo,selection=yardstick
databricks bundle run jev_semantic_tests --params action=results,selection=yardstick   # no Jev call
```

### Scoring

`scripts/score.py` reads the stored failures, joins them against the hidden
`eval/golden_defects.csv`, and prints precision/recall/F1 for Jev vs the regex baseline, plus
provenance (mode, model, requests, tokens, retries, 429s) from the ledger. `--run` builds first
and needs an explicit `--mode live|demo`. `--append` (needs `--run`, live only) adds the run to
`docs/eval-results.md`; a simulated run is refused, and so is a yardstick run with any cached
state (a yardstick entry judges every state in the run it scores: `--fresh`).

```bash
uv run python scripts/score.py --run --fresh --mode live --append    # live: billed by TypeSafe
```

The comparison with demo 04 uses its `live/pack=64/nested` run (64 rows per request). Demo 05
cuts packs by estimated tokens instead (budget 48k, cap 256 rows), about 120–256 rows per pack on
these tests, so the request counts are not like for like; the accuracy columns are.

## The production run

A planned sample of 50,000 real product reviews with planted rating flips, judged by the same review sentence
(`reviews_body_matches_stars`, same `fails_if`, `context`, threshold and `criteria`).

Dataset: Amazon Fine Food Reviews, SNAP / Stanford. J. McAuley and J. Leskovec, *From amateurs to
connoisseurs: modeling the evolution of user expertise through online reviews*, WWW 2013.
The SNAP page states no licence and asks for the citation; SNAP's Kaggle upload lists CC0. The
data is downloaded locally and never committed. `scripts/fetch_reviews.py` keeps only id, score,
summary and text (user ids and profile names are dropped), samples 50,000 with seed 42, plants
flips on ~3% of the non-3-star rows (1↔5, 2↔4), and splits 47,500 + 2,500. The data files are
gitignored; only `eval/production_flips.csv` (ids and stars, no text) is committed.

The source file, measured (a fact about the data, not a Jev result): 568,454 reviews; review text
length mean 475 / median 346 chars.

**ESTIMATE, not a result** (offline estimate, 2026-10-01; no Jev call was made): 50,000 sampled
rows → 46,511 distinct states; estimated 10.8–11.1M input tokens ≈ $0.45–0.47 (±15%), 0 rows over
the per-row token limit. The cost of the run is the logged one, once it has been made.

1. Download and sample: `uv run python scripts/fetch_reviews.py --download --out data/` (or
   `--source` for a file you already have). `<br />` tags become newlines and HTML entities are
   unescaped (markup artifacts of the source, the same for Jev and the baseline).
2. `uv run python scripts/deploy.py --production --apply`, then
   `uv run python scripts/fetch_reviews.py --out data/ --source data/finefoods.txt.gz --upload`
   (part 1, 47,500 rows).
3. A larger serverless warehouse (for the recorded run, `jev-demo-5-prod`, Small), then
   `eval "$(uv run python scripts/jev_env.py --warehouse jev-demo-5-prod)"`.
4. Judge part 1 and log it (the billed run is the scored one):
   `uv run python scripts/score.py --production --run --fresh --mode live --append`. It builds with
   `--vars '{production: true, jev_max_concurrency: 2}' --select +tag:production tag:production_baseline`.
   Recall counts only the planted flips that are loaded (`planted flips loaded: X of Y`). The gate
   reads PENDING: the audit and the rerun are still missing.
5. Audit: `uv run python scripts/audit_sample.py` writes ~100 flagged-but-unplanted reviews
   (text and stars only, no score) to `data/production_audit.csv`. You label each `real` (text
   and stars disagree) or `ok`, without seeing Jev's probability. Precision is extrapolated from
   that sample with a 95% Wilson interval; raw precision against the planted flips is reported
   too.
6. The increment: `uv run python scripts/fetch_reviews.py --out data/ --upload-part2` (+2,500
   rows), then `uv run python scripts/score.py --production --run --mode live --increment --append`.
   Only the new distinct (body, stars) states are judged, nothing else; the entry logs
   `increment: N new distinct states judged (M rows loaded)`. N can be below 2,500: reviews repeat
   texts, and a state already judged is a cache hit.
7. The rerun check: `uv run python scripts/score.py --production --run --rerun --mode live --append`
   builds once (nothing new to judge) and again, and requires the second build to make 0 requests.
   With the audit labelled, this entry reads PASS or FAIL.

Every entry records the dbt invocation, the cached share and, when judgments were cached, the
invocations they came from, each with its states, requests, tokens, cost and Jev span, so the
last entry also carries the cost of the billed runs.

Production builds pass `jev_max_concurrency: 2` (two packs in flight per statement instead of
four). TypeSafe allows 250k tokens/s, and a handful of 48k-token packs finishing within the same
second can exceed it. The retry path (429 and backoff) is tested offline but has never been
exercised live, so the first 50,000-row run keeps fewer packs in flight rather than relying on
it.

## Results

No numbers here yet: the live runs have not been made. Scored live runs are appended to
[`docs/eval-results.md`](docs/eval-results.md), next to demo 04's logged numbers for the same four
tests. Only numbers from logged live runs appear in this repo; SIMULATED output is never quoted.

## Production notes

- **Function owner.** The function runs with its owner's rights, and anyone who calls it can
  spend the owner's secret. The owner should be a service principal or a group, not a person.
  Callers need `EXECUTE`; nobody else needs `READ SECRET`.
- **No global pacer.** TypeSafe allows 1,200 requests/min and 250k tokens/s (64k tokens per
  request), adjusting dynamically. There is no pacer across executors. `REPARTITION(n)` caps the
  packs in flight per statement (`jev_max_concurrency`: 4, 2 for the production run), but dbt runs 4 threads, so up to 4 hooks run at once (up to
  `4 × n` packs). The coordination is the server's 429 and the in-function backoff
  (`retry-after` honoured as a floor, capped at 60 s). Each run reports its retries and 429s.
- **Concurrent hooks.** Two hooks appending to the same Delta table conflict
  (`DELTA_CONCURRENT_APPEND.ROW_LEVEL_CHANGES`) if their cache reads scan the whole table. Each
  hook reads only its own question's rows, so they do not.
- **Residual task-retry gap.** A Spark task that is retried after its first attempt already
  reached Jev bills twice and is invisible from inside the function. The per-run check is
  external: the ledger's token total (`jev_demo.jev.requests`) against the TypeSafe usage page
  for that day, logged next to the run in `docs/eval-results.md`.
- **A pack can exceed 64k tokens** in one edge case: a bucket's last row with an estimate between
  ~16k and 30k tokens (rows above 30k are not sent at all). The API then rejects that pack; its
  rows are stored unjudged (`p = NULL`, with the error) and reported as unjudged in the summary.
  Loud, not silent. Real rows are far smaller (the 16k-token mark is ~50k characters).
- **Cost.** Jev: input tokens × $0.042 per million (`src/jevdbx/pricing.py`,
  [docs.typesafe.ai/models](https://docs.typesafe.ai/models)). Warehouse DBUs from
  `system.billing.usage` once that schema is enabled. Query overhead (13–27 s per statement,
  measured in the spike, spec §3) dominates wall time, not Jev.
- **Model pinned** to `jev-1.13.0` (dbt var `jev_model`), not the `jev-latest` alias; it is part of
  the cache key.

## Recording

`scripts/record.sh [--cold] [--notebook] [--results] [--no-production] [--no-captions]` types out each beat and
waits for a keypress: the standard build on Databricks, the `jev_expect` blocks, the Jev function (`DESCRIBE FUNCTION
EXTENDED`), the semantic build with its summary line, the flagged rows, the scorecard, and the
production run with its rerun. With `--notebook`, beats 4 and 7 print how to run the bundle
job instead of running dbt locally (nothing is deployed by the script; beat 1 still runs dbt
locally, and `--cold` is ignored with a notice). `--results` implies `--notebook` and prints the
`action=results` run instead: the logged live run is shown without judging on camera. Captions, a title card and an end card are built
in.

Record right after a scored run (`score.py --run --append`, live), and without `--cold`: the
accuracy numbers on screen (flagged rows, scorecard) are then the logged run's, and beat 4 shows a
fully cached rerun. Beat 7 prints the last logged production entry of `docs/eval-results.md`
verbatim (`scripts/show.py production`: planted flips, audited precision, cost and throughput of
the billed runs), then runs the production build once more on camera, only to show 0 requests;
that rerun's own cost line is $0 because nothing is judged. `--cold` judges every state again on camera, a new live run (billed) whose
numbers are not in `docs/eval-results.md` until it is scored and appended; use it only for a take
you will log the same way.

Terminal size: 90 columns x 30 rows, a large font.

Smoke-test in demo mode only, never live (the output says SIMULATED):

```bash
yes '' | JEV_MODE=demo TYPE_DELAY=0 scripts/record.sh
```

## Pins

Python 3.13, uv, `dbt-databricks==1.12.5` (which caps dbt-core below 1.12.4, so dbt-core 1.12.3;
demo 04 used 1.12.5), `databricks-sdk`. dbt Fusion is not used. Tests: `uv run pytest -q`
(offline), `uv run pytest -m databricks -q` (demo mode on the dev warehouse), `uv run ruff check`.
