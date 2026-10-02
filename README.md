# Demo 06: Jev vs LLMs through `ai_query`, as one dbt test

One dbt test, `jev_expect`, and one flag, `--vars '{judge: <name>}'`, that decides who judges it:
TypeSafe's Jev (a function called from the dbt post-hook) or an LLM served inside Databricks
(`ai_query` on a pay-per-token Foundation Model endpoint). The test sentences are identical for
every judge. Each judge is scored against ground truth for precision, recall and F1, with cost,
requests and wall time per judge.

It follows demo 05 (`jev_expect` with Jev only) and a LinkedIn thread with Hugo Lu on whether the
model should be served by the warehouse. This repo asks what that costs and what it buys, on three
datasets, with a fixed sample, frozen prompts and a spend cap.

Status: the code, data keys and tests are in place. The live runs have not been made, so there are
no results yet (see Results).

## What it shows

```
uv run python scripts/dbtw.py build --vars '{judge: jev}'                                --select +tag:semantic
uv run python scripts/dbtw.py build --vars '{judge: databricks-gpt-oss-20b}'             --select +tag:semantic
uv run python scripts/dbtw.py build --vars '{judge: databricks-meta-llama-3-3-70b-instruct}' --select +tag:semantic
uv run python scripts/dbtw.py build --vars '{judge: databricks-claude-opus-5}'           --select +tag:semantic
```

| judge (`judge` var) | how it is called | tier |
|---|---|---|
| `jev` (default) | `jev_demo.jev.noul_pack`: states packed by estimated tokens (48k budget, 256-row cap) | n/a |
| `databricks-gpt-oss-20b` | `ai_query`, one row per call | small |
| `databricks-meta-llama-3-3-70b-instruct` | `ai_query`, one row per call | mid |
| `databricks-claude-opus-5` | `ai_query`, one row per call | frontier |

No Sonnet endpoint works with `ai_query` in this workspace (spike S2: "not supported for batch
inference"), so the frontier judge is `databricks-claude-opus-5`, with one pass instead of two.
Each judge is used the way it is built to be used (Jev packs many rows per request, `ai_query` is
row-wise), and the scorecard shows requests, wall time and cost so the difference is visible.

## The three tests

The sentences live in `bench/models/staging/schema.yml`, one `jev_expect` per dataset:

| test | table | sentence (`fails_if`) |
|---|---|---|
| `banking_query_not_about_intent` | `stg_banking_queries` | The customer's `query` is not about its labelled `intent`. |
| `pairs_describe_same_product` | `stg_product_pairs` | `left_record` and `right_record` describe the same product (same brand and model; ignore price and wording). |
| `wanderbricks_comment_contradicts_rating` | `stg_wanderbricks_reviews` | The review `comment` clearly contradicts its `rating` (1.0 = very bad, 5.0 = excellent). |

All three use `threshold: 0.8` and `severity: warn`. The Jev path flags `p >= threshold`, as demo 05
does; an LLM flags when it answers `decision = true`.

## Datasets, sources and licences

| | Banking77 | Abt-Buy | wanderbricks |
|---|---|---|---|
| Used for | ticket triage | duplicate detection | Databricks sample data |
| Source | PolyAI task-specific datasets | DeepMatcher Textual split of Abt-Buy | `samples.wanderbricks.reviews` in the Databricks `samples` catalog |
| Size | 10,003 train + 3,080 test = 13,083 queries, 77 intents | 9,575 labelled pairs, 1,028 matches; test split 1,916 pairs, 206 matches | 99,793 rows, 15 distinct comments, 205 distinct (comment, rating) states |
| Benchmark sample | 2,000 test queries | the whole test split | all 205 natural states plus planted ratings |
| Ground truth | seeded intent swaps | the dataset's own match labels | 15 polarity labels plus a fixed rule |
| Baseline | keyword overlap between query and intent name | token-Jaccard, threshold fit on the train split | none (the rule is exact) |

**Banking77.** Licence CC BY 4.0. Casanueva et al. 2020, *Efficient Intent Detection with Dual
Sentence Encoders*. Source files are listed in `eval/sources.toml`.

**Abt-Buy.** DeepMatcher Textual split (Mudgal et al., SIGMOD 2018) of the Abt-Buy dataset from the
Leipzig benchmark datasets for entity resolution (Rahm group, dbs.uni-leipzig.de); Köpcke, Thor,
Rahm, VLDB 2010. The source page says "Creative Commons" and does not name a variant, so only pair
ids and labels are committed here, never record text.

**wanderbricks.** The `samples.wanderbricks` data that Databricks ships in the `samples` catalog;
no row text is committed.

How the ground truth is built:

- **Banking77.** 150 swaps seeded (seed 42) into the 2,000-query sample, 7.5%: 75 random and 75
  near-miss, where a near-miss moves the label inside its intent family (for example `card_arrival`
  to `card_delivery_estimate`). Families come from the intent name's leading tokens and are fixed in
  `eval/intent_families.csv`. Recall is reported separately for the two kinds.
- **Abt-Buy.** The test split as labelled. The Jaccard threshold is in `eval/abt_buy_jaccard.txt`.
- **wanderbricks.** The natural data has no contradictions: the 5 negative comments are rated
  1.0 to 2.4, the 5 lukewarm ones 2.5 to 3.9, the 5 glowing ones 4.0 to 5.0. So the test table also
  holds planted ratings (seed 42, never a natural state, `review_rows = 0`), keyed by a hash of the
  comment. The rule, fixed before any run: a negative comment with rating 4.0 or more, or a positive
  comment with rating 2.0 or less, is a contradiction; neutral or mixed comments and ratings
  strictly between 2.0 and 4.0 are not. The 205 natural states are kept as a control: the
  false-alarm rate on them is reported with a Wilson 95% interval.
- Jev also runs at scale: all 13,083 Banking77 queries (swaps at the same rates) and all labelled
  Abt-Buy pairs.

The keys, swap list, family table and baselines are never edited to make a judge win. Rows that
every judge flags but the key calls clean are listed as possible key errors for a manual look; they
do not change any raw score. There is no LLM audit of the keys.

## How it works

- **One post-hook, two paths.** `jev_judge()` (macros in `bench/macros/`) runs after each model and
  judges the states of its selected `jev_expect` tests that have no successful judgment yet. With
  `judge: jev` it makes one `INSERT ... SELECT` that calls `noul_pack` once per pack. With any
  other judge it makes one set-based statement over the missing states calling
  `ai_query(<endpoint>, <prompt>, responseFormat => <schema>, modelParameters => named_struct(...),
  failOnError => false)`. Temperature is 0; gpt-oss-20b also gets `reasoning_effort` low. The
  response schema is `{decision: boolean, probability: double}`.
- **One prompt source.** `bench/macros/jev_question.sql` is the only place that reads `fails_if`,
  `context` and `criteria`. It renders the question JSON for Jev and a plain prompt for the LLMs
  from the same parts, and builds the state expression and the cache key. A test checks that both
  renderings carry the same sentence, criteria and fields.
- **Per-judge cache.** Judgments go into `jev_demo.bench.judgments`; the key hashes the judge, test
  and state, so each judge judges each distinct state once. `--fresh` deletes one judge's rows for
  the selected tests only.
- **Errors are loud.** `ai_query` returns `result` and `errorMessage`. Failed rows are stored as
  errors, counted in the run summary and the eval log, and never treated as a pass or a fail.
  Inserted must equal missing, with no duplicate keys, for every judge.
- **SIMULATED mode.** `JEV_MODE=demo` swaps in `noul_pack_demo` for Jev and a deterministic
  hash-based SQL stand-in (`jev_demo.bench.llm_demo()`) for the LLMs. Output is labelled
  `SIMULATED` and is never logged or quoted as a result; the scorer refuses to append it.

## Prerequisites

- A Databricks workspace with the dev warehouse and CLI profile from demo 05
  (`~/Projects/jev-demo-5`, read only). No host, warehouse id, storage account or tenant is stored in
  this repo; an identifier scan runs in the tests.
- From demo 05, referenced and not recreated: the functions `jev_demo.jev.noul_pack` and
  `noul_pack_demo`, and the Unity Catalog secret holding the TypeSafe key.
- New here: the schema `jev_demo.bench` (judgments, hook runs, dbt models, stored failures,
  `llm_demo`) and its volume for downloaded data. Creating them is a confirm-first step
  (`scripts/deploy.py --apply`).
- Access to the pay-per-token endpoints named above, and read access to `system.serving.endpoint_usage`
  for cost measurement.
- Python 3.13 and `uv`. dbt runs locally through `scripts/dbtw.py` with a short-lived CLI-profile
  token, never a personal access token.

## Run it

```
uv sync
uv run pytest -q                        # offline tests
uv run pytest -m databricks -q          # integration, SIMULATED, dev warehouse
uv run ruff check

uv run python scripts/fetch_data.py --download   # Banking77 + Abt-Buy to data/ (confirm-first)
uv run python scripts/fetch_data.py --upload     # to the volume (confirm-first)
uv run python scripts/deploy.py                  # print the platform DDL
uv run python scripts/deploy.py --apply          # apply it (confirm-first the first time)

uv run python scripts/score.py --preregister     # once, before pass 1
uv run python scripts/score.py --run --judge <judge> --scope <pilot|sample|full> --pass <n> \
    --mode live --append                         # a live pass: billed for LLM judges
uv run python scripts/score.py --usage           # endpoint usage so far, by served entity
uv run python scripts/score.py --measure --append # replace estimated cost with measured cost
uv run python scripts/score.py --compare         # side analyses once every judge has a live pass
uv run python scripts/show.py tests              # the three sentences
uv run python scripts/show.py board              # latest logged pass per judge
```

dbt is only called through `scripts/dbtw.py`, which runs it in `bench/`. Live Jev runs, real
`ai_query` calls, downloads, uploads and creating the schema are all confirm-first.

## Budgets and how cost is measured

- **LLM cap: $15 in total**, enforced by `scripts/score.py`. Before each LLM pass it projects
  cost as spend so far plus tokens per row times remaining rows times the price, and refuses to
  start if that passes the cap.
- **Prices** (`src/jevdbx/budget.py`, Azure Premium at $0.070 per DBU, checked 2026-10-01) in $ per
  1M input / output tokens: gpt-oss-20b 0.07 / 0.30; llama-3.3-70b 0.50 / 1.50. The
  claude-opus-5 price, about 5 / 25, is an ESTIMATE until verified before the pilot gate.
- **Estimates until measured.** Tokens per row start as assumptions in `budget.py` and are replaced
  by the pilot's measured tokens per row. Every cost line in the log says `measured` or `estimated`.
- **Measured cost.** `system.serving.endpoint_usage` is read and attributed to a run by time
  window (the run's hook window plus or minus 5 seconds), because `served_entities` has no rows for
  these endpoints. A window counts only if exactly one served entity was used in it. Usage lags
  by about two hours, so `score.py --measure` fills it in afterwards. If usage cannot be read, the
  cost stays a labelled estimate.
- **Jev cost** comes from the TypeSafe credit ledger, as in demo 05.
- **Run plan.** Pilot (50 rows per dataset per judge), pass 1 (shared sample, all four judges),
  pass 2 (`--fresh` rerun for run-to-run noise: Jev and the two open models only, not Opus), then
  Jev at scale. Each step is confirm-first.

## Fairness rules

- Prompts and test sentences are frozen at pre-registration. Changing one afterwards means
  rerunning every judge and logging before and after; a prompt is never tuned for one judge.
  `jev_prompt_version` is part of the cache key.
- The same sentence, criteria and record fields go to every judge, at temperature 0.
- Before pass 1, `docs/eval-results.md` records the frozen prompts and wording, the swap seed and
  family table, the sample definitions and the headline comparisons:
  1. per dataset, F1 of Jev against each LLM at decision level, with Wilson 95% intervals for
     precision and recall (wanderbricks also reports the false-alarm rate on natural states);
  2. per dataset, cost per 1,000 rows and wall time per judge;
  3. Banking77 recall on random against near-miss swaps, per judge.
- Side analyses are reported apart from the headline: calibration (Brier score, reliability
  table), each LLM thresholded like Jev, an agreement matrix, and possible key errors.
- Only live runs started by the scorer are logged, one entry per (pass, judge). SIMULATED runs are
  refused.

## Results

No numbers yet: the live runs have not been made.

Results will come only from `docs/eval-results.md`, the log that `scripts/score.py --run --append`
writes. Costs there are labelled measured or estimated.

## Pins

- Jev model `jev-1.13.0`, prompt version `p1` (both in the cache key).
- Endpoints: `databricks-gpt-oss-20b`, `databricks-meta-llama-3-3-70b-instruct`,
  `databricks-claude-opus-5`.
- `dbt-databricks==1.12.5`; Python 3.13 or later; dependencies locked in `uv.lock`.
- Design spec with dated amendments: `docs/superpowers/specs/2026-10-01-jev-vs-ai-query-design.md`;
  plan: `docs/superpowers/plans/2026-10-01-jev-vs-ai-query.md`.
