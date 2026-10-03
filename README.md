# Demo 06: Jev vs LLMs through `ai_query`, as one dbt test

One dbt test, `jev_expect`, and one flag, `--vars '{judge: <name>}'`, that decides who judges it:
TypeSafe's Jev (a function called from the dbt post-hook) or an LLM served inside Databricks
(`ai_query` on a pay-per-token Foundation Model endpoint). The test sentences are identical for
every judge. Each judge is scored against ground truth for precision, recall and F1, with cost,
requests and wall time per judge.

It follows demo 05 (`jev_expect` with Jev only) and a LinkedIn thread with Hugo Lu on whether the
model should be served by the warehouse. This repo asks what that costs and what it buys, on three
datasets, with a fixed sample, frozen prompts and a spend cap.

Status: the live runs were made on 2026-10-03. Results are summarised below and in
[FINDINGS.md](FINDINGS.md), from the log in `docs/eval-results.md`.

## What it shows

```
uv run python scripts/dbtw.py build --vars '{judge: jev}'                                --select +tag:semantic
uv run python scripts/dbtw.py build --vars '{judge: databricks-gpt-oss-20b}'             --select +tag:semantic
uv run python scripts/dbtw.py build --vars '{judge: databricks-meta-llama-3-3-70b-instruct}' --select +tag:semantic
uv run python scripts/dbtw.py build --vars '{judge: databricks-claude-opus-4-8}'         --select +tag:semantic
```

| judge (`judge` var) | how it is called | tier |
|---|---|---|
| `jev` (default) | `jev_demo.jev.noul_pack`: states packed by estimated tokens (48k budget, 256-row cap) | n/a |
| `databricks-gpt-oss-20b` | `ai_query`, one row per call | small |
| `databricks-meta-llama-3-3-70b-instruct` | `ai_query`, one row per call | mid |
| `databricks-claude-opus-4-8` | `ai_query`, one row per call (default temperature) | frontier, pilot only |

Over a table, `ai_query` in this workspace rejects Opus 5, Opus 5.5 and the Sonnet 5.x endpoints
with "not supported for batch inference", so the frontier judge is `databricks-claude-opus-4-8`
(a dated amendment to the pre-registration). It rejects `temperature`, so it runs at its default.
Its full pass would cost about $20, over the $15 cap, so it was run on the 50-row pilot only.
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
  failOnError => false)`. Temperature is 0; gpt-oss-20b also gets `reasoning_effort` low; Opus 4.8
  rejects `temperature` and gets no `modelParameters`. The
  response schema is `{decision: boolean, probability: double}`.
- **One prompt source.** `bench/macros/jev_question.sql` is the only place that reads `fails_if`,
  `context` and `criteria`. It renders the question JSON for Jev and a plain prompt for the LLMs
  from the same parts, and builds the state expression and the cache key. A test checks that both
  renderings carry the same sentence, criteria and fields.
- **Per-judge cache.** Judgments go into `jev_demo.bench.judgments`; the key hashes the judge, test
  and state, so each judge judges each distinct state once. `--fresh` deletes one judge's rows for
  the given mode (`live` or `demo`), across all tests.
- **Errors are loud.** `ai_query` returns `result` and `errorMessage`. Failed rows are stored as
  errors, counted in the run summary and the eval log (`unjudged`), and never treated as a pass or
  a fail: the scorer scores judged rows only. More than 1% unjudged rows in any test is not a
  result; a rerun fills them (errored rows are not cached as successes, so only those are called
  again). Inserted must equal missing, with no duplicate keys, for every judge.
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

uv run python scripts/score.py --preregister     # once, before the pilot (pins a frozen digest)
uv run python scripts/score.py --run --judge <judge> --scope pilot --pass 0 \
    --mode live --append                         # the pilot: billed for LLM judges
uv run python scripts/score.py --measure --append # after the pilot: wait for usage (~2 h), then
                                                 # replace estimated cost with measured cost
uv run python scripts/score.py --run --judge <judge> --scope <sample|full> --pass <n> \
    --mode live --append [--fresh]               # a live pass; --fresh deletes the judge's live
                                                 # rows first (pass 2: run-to-run noise)
uv run python scripts/score.py --usage           # endpoint usage so far, by served entity
uv run python scripts/score.py --compare         # side analyses once every judge has a live pass
uv run python scripts/show.py tests              # the three sentences
uv run python scripts/show.py board [--pass N] [--scope sample|full]  # default pass 1, sample
```

dbt is only called through `scripts/dbtw.py`, which runs it in `bench/`. Live Jev runs, real
`ai_query` calls, downloads, uploads and creating the schema are all confirm-first.

## Budgets and how cost is measured

- **LLM cap: $15 in total**, enforced by `scripts/score.py`. Before each LLM pass it projects
  the cost of every row in scope (tokens per row times rows times the price), and refuses to start
  if logged spend so far plus 1.15 times that projection passes the cap. A live LLM run must
  `--append`, and always ends in a log entry: the result, or a `refused` entry that keeps its spend
  in the guard (estimated at no less than the projection until `--measure` replaces it).
- **Prices** (`src/jevdbx/budget.py`, Azure Premium at $0.070 per DBU, checked 2026-10-01) in $ per
  1M input / output tokens: gpt-oss-20b 0.07 / 0.30; llama-3.3-70b 0.50 / 1.50; claude-opus-4-8
  5 / 25 (verified 2026-10-02).
- **Estimates until measured.** Tokens per row start as assumptions in `budget.py` and are replaced
  by the pilot's measured tokens per row. Every cost line in the log says `measured` or `estimated`.
- **Measured cost.** `system.serving.endpoint_usage` is read and attributed to a run by time
  window (the judging build's window, logged as `- window`; for older entries the run's hook window
  plus or minus 5 seconds), because `served_entities` has no rows for these endpoints. A window
  counts only if exactly one served entity was used in it and its requests cover every row judged
  in the run (more than 5% extra is flagged as possible duplicate evaluation). Usage lags by about
  two hours, so `score.py --measure --append` fills it in afterwards. In practice
  `endpoint_usage` logged only about a third of `ai_query`'s requests, still so 7 hours later; after
  6 hours the logged mean per request is scaled to every judged row, and the entry states the
  coverage. A refused run with no usage at all settles at $0. If usage cannot be read, the
  cost stays a labelled estimate. Every entry also logs its token totals (measured or estimated).
- **Jev cost** is pack tokens × the list price ($0.042 per 1M tokens), as in demo 05.
- **Run plan, as run.** Pilot (50 rows per dataset per judge), pass 1 (shared sample: Jev and the
  two open models; Opus 4.8 stopped at the pilot on cost), pass 2 (`--fresh` rerun for run-to-run
  noise, the same three judges), then Jev at scale. Total measured LLM spend: $2.56.

## Fairness rules

- Prompts and test sentences are frozen at pre-registration. Changing one afterwards means
  rerunning every judge and logging before and after; a prompt is never tuned for one judge.
  `jev_prompt_version` is part of the cache key.
- The same sentence, criteria and record fields go to every judge, at temperature 0 (Opus 4.8
  rejects the parameter and runs at its default).
- Before the pilot, `docs/eval-results.md` records the frozen prompts and wording, the swap seed and
  family table, the sample definitions, a frozen digest (sha256 of `git ls-files -s` over
  `bench/macros`, `bench/models`, `bench/seeds`, `bench/tests`, `bench/dbt_project.yml` and `eval`),
  the 1% unjudged tolerance, the 1.15 budget margin and the headline comparisons:
  1. per dataset, F1 of Jev against each LLM at decision level, with Wilson 95% intervals for
     precision and recall (wanderbricks also reports the false-alarm rate on natural states);
  2. per dataset, cost per 1,000 rows and wall time per judge;
  3. Banking77 recall on random against near-miss swaps, per judge.
- Side analyses are reported apart from the headline: calibration (Brier score, reliability
  table), each LLM thresholded like Jev, an agreement matrix, and possible key errors.
- Only live runs started by the scorer are logged, one entry per (pass, judge). SIMULATED runs are
  refused. A live append is refused without the pre-registration, or when the frozen paths are
  dirty or no longer match its digest.

## Results

From `docs/eval-results.md` (pass 1, 2026-10-03, the same 4,161 rows for every judge); details,
intervals and caveats in [FINDINGS.md](FINDINGS.md).

| judge | Banking77 F1 | Abt-Buy F1 | wanderbricks F1 | requests | wall time | cost per 1,000 rows |
|---|---|---|---|---|---|---|
| Jev | 0.56 | **0.86** | **0.98** | 25 | 19.4 s | $0.007 (ledger) |
| gpt-oss-20b | **0.67** | **0.86** | 0.91 | 4,006 | 56.9 s | $0.046 (measured\*) |
| Llama 3.3 70B | 0.50 | 0.69 | 0.74 | 4,006 | 141.3 s | $0.163 (measured\*) |
| Opus 4.8, 50-row pilot only | 0.67 | 1.00 | 1.00 | 150 | 16.4 s | $5.03 (measured\*) |
| baseline | 0.33 | 0.34 | n/a | | | |

- Jev is the most precise judge (0.85 to 1.00) and never raised a false alarm on the 205 clean
  wanderbricks states; gpt-oss-20b catches far more of the subtle Banking77 near-miss swaps (0.72
  against Jev's 0.24).
- Pass 2 (fresh) reproduced every F1 within 0.02, except Llama on wanderbricks (0.04).
- Jev at full scale: 18,674 new judgments over all 13,083 Banking77 queries and 9,575 Abt-Buy pairs
  in 120 requests, 25.5 s and $0.132.
- \*`endpoint_usage` logged about a third of the requests; cost is the logged mean per request
  times the rows judged (see Budgets).
- The wanderbricks polarity labels were made by Claude at the user's request.

## Pins

- Jev model `jev-1.13.0`, prompt version `p1` (both in the cache key).
- Endpoints: `databricks-gpt-oss-20b`, `databricks-meta-llama-3-3-70b-instruct`,
  `databricks-claude-opus-4-8`.
- `dbt-databricks==1.12.5`; Python 3.13 or later; dependencies locked in `uv.lock`.
- Design spec with dated amendments: `docs/superpowers/specs/2026-10-01-jev-vs-ai-query-design.md`;
  plan: `docs/superpowers/plans/2026-10-01-jev-vs-ai-query.md`.
