# Demo 06 — Jev vs LLMs through `ai_query`, as dbt semantic tests on Databricks

Date: 2026-10-01 · Status: design approved in brainstorming, spec under review · Repo:
`~/Projects/jev-demo-6` · Publishes to `jev-demos` as `06-jev-vs-ai-query/` (working name).

## 1. Purpose

Benchmark TypeSafe's Jev against LLMs served inside Databricks (`ai_query` on pay-per-token
Foundation Model endpoints) on three domains, using one dbt test, `jev_expect`, with a swappable
judge. It follows demo 05 and the LinkedIn thread with Hugo Lu (should the model be served by the
warehouse?): the same sentence, four judges, one `--vars` flag, scored against ground truth, with
measured cost.

Success: for each dataset × judge, precision / recall / F1 against ground truth, cost, requests and
wall time, from logged live runs, within the budgets in §6. No judge "wins" by a gate; the headline
comparisons are pre-registered (§7).

Out of scope: an LLM audit of the keys (Claude is a competitor), a Databricks bundle job, prompt
tuning per judge, models outside the three tiers in §3.

## 2. Datasets, tests and ground truth

| | Ticket triage | Duplicates (data quality) | Databricks sample data |
|---|---|---|---|
| Source | Banking77 (PolyAI), CC BY 4.0, 13,083 queries, 77 intents | Abt-Buy entity-matching benchmark (fallback: Amazon-Google) | `samples.wanderbricks.reviews` (99,793 rows, 15 distinct comments, 205 distinct (comment, rating) states) |
| dbt model | `stg_banking_queries` (query, intent) | `stg_product_pairs` (left, right: two product records per row) | `stg_wanderbricks_reviews` (comment, rating, review_rows): natural states + seeded planted ratings |
| `jev_expect` sentence | The customer's `query` is not about its labelled `intent` | `left` and `right` describe the same product | The review `comment` clearly contradicts its `rating` |
| Ground truth | planted intent swaps, seeded | the dataset's own match labels | the user labels the 15 comments' polarity; a fixed rule derives contradiction per (comment, rating) state, natural or planted |
| Benchmark sample | 2,000 test-split queries, 150 swaps: 75 random, 75 near-miss (same intent family, e.g. `card_arrival` → `card_delivery_estimate`); reported separately | the full test split (≈1,900 pairs, ≈200 matches; exact counts from the spike) | every natural state (205, the control) + the planted states (≈40) |
| Jev at scale | all 13,083 queries (swaps at the same rates) | all labelled pairs | same as sample |
| Baseline | keyword overlap between query and intent name | token-Jaccard ≥ threshold (threshold fixed on the train split) | none (the rule is exact) |

- Near-miss families are defined by the intent name's leading token(s) (`card_*`, `top_up_*`,
  `transfer_*`, …); the family table is committed and fixed before any run.
- wanderbricks contradiction rule (fixed before any run): negative comment and rating ≥ 4.0, or
  positive comment and rating ≤ 2.0, is a contradiction; neutral/mixed comments and 2.0 < rating
  < 4.0 are not.
- *Amended 2026-10-01 (wanderbricks, user decision "flips + control"):* a query on 2026-10-01
  showed the natural data has **no contradictions**: the 5 negative comments are always rated
  1.0–2.4, the 5 lukewarm 2.5–3.9, the 5 glowing 4.0–5.0 (99,793 rows = 205 distinct states). The
  test therefore gets seeded planted ratings on top of the natural states, which stay in as
  negatives: per comment, by its natural rating band (seed 42), a low-band comment gets 3 ratings
  from 4.0–5.0, a high-band comment 3 from 1.0–2.0, a mid-band comment 2 (one from 1.0–2.0, one from
  4.0–5.0: hard negatives if labelled neutral); never a natural state. Planted states carry
  `review_rows = 0`, are keyed by comment hash (no text committed: `eval/wanderbricks_flips.csv`,
  seed `bench/seeds/wanderbricks_flips.csv`) and are fixed before any run. Ground truth is still
  the 15 polarity labels + the rule, applied to every state. Scored two ways: F1 over all states
  (headline 1) and, as a control, the false-alarm rate on the natural states (flags on natural
  states the rule calls clean, Wilson 95%). Facts about the source data (counts and rating bands
  from a query) may be quoted as data facts; they are not judge results.
- No LLM audit. Rows that all four judges flag but the key calls clean are listed as "possible key
  errors" for the user to label by hand if they choose; raw scores never change because of them.
- Licences and exact sizes are verified in Spike S1 before any download is requested.

## 3. Judges

| judge (dbt var) | path | tier |
|---|---|---|
| `jev` (default) | `jev_demo.jev.noul_pack`, packs by estimated tokens (48k budget, 256-row cap), nested layout | — |
| `databricks-gpt-oss-20b` | `ai_query`, one row per call | small |
| `databricks-meta-llama-3-3-70b-instruct` | `ai_query`, one row per call | mid |
| `databricks-claude-sonnet-5-5` | `ai_query`, one row per call | frontier |

Each judge is used natively (Jev packs, `ai_query` is row-wise); the scorecard shows requests, wall
time and cost per judge so the difference is visible.

## 4. Architecture

- **One switch.** `dbt build --vars '{judge: <name>}' --select +tag:semantic`. The project-level
  post-hook `jev_judge()` branches on `judge`: the Jev path is demo 05's, unchanged; the LLM path is
  one set-based statement over the missing states:
  `ai_query('<endpoint>', <prompt>, responseFormat => '<schema>', modelParameters =>
  named_struct('temperature', 0.0 [, reasoning effort low for gpt-oss]), failOnError => false)`.
  Response schema: `{decision: boolean, probability: double}`.
- **One prompt source.** `jev_question.sql` remains the single place that reads `fails_if`,
  `context` and `criteria` and builds the state expression and cache key. It renders two forms from
  the same parts: the question JSON for Jev and a plain prompt for LLMs (instruction, criteria
  true/false descriptions, the record's fields, the answer format). A test asserts both renderings
  contain the same sentence, criteria and fields.
- **Decisions.** Jev: `p > threshold` of the test. LLM: `decision = true` (headline). The LLM
  `probability` is stored for side analyses (§7).
- **Cache.** `jev_demo.bench.judgments` gains `judge`; key = hash(judge, test, state). Each judge
  judges each distinct state once; `--fresh` deletes one judge's rows for the selected tests only.
- **Errors are loud.** `failOnError => false` returns a per-row error; errored rows are stored as
  errors, counted in the run summary and the eval log, never treated as pass or fail. Demo 05's
  once-per-row checks (inserted = missing, no duplicate keys) apply to every judge.
- **SIMULATED mode** (`JEV_MODE=demo`): Jev → `noul_pack_demo`; LLM → `jev_demo.bench.llm_demo()`, a
  deterministic hash-based SQL stand-in returning the same struct. Always shows `SIMULATED`, never
  logged or quoted as a result.

## 5. Platform

- Workspace, CLI profile and dev warehouse as demo 05 (`jev-demo-5`, 2X-Small). No workspace host,
  warehouse id, storage account or tenant in any committed file (identifier-scan test carried
  over).
- Reused: `jev_demo.jev.noul_pack`, `noul_pack_demo`, UC secret `jev_demo.jev.typesafe_api_key`
  (no new secret).
- New (confirm-first once): schema `jev_demo.bench` (judgments, hook_runs, dbt models, stored
  failures, `llm_demo`), volume `jev_demo.bench.raw` for downloaded data.
- Data: Banking77 and Abt-Buy are downloaded locally and uploaded to the volume (each step
  confirm-first), never committed. Committed: the swap list (query id, original and swapped intent;
  CC BY 4.0 with attribution), the near-miss family table, Abt-Buy pair ids and labels, the 15
  wanderbricks polarity labels and the planted ratings, keyed by a hash of the comment (not its text).
- dbt runs locally through `scripts/dbtw.py` (short-lived CLI-profile token, never a PAT).

## 6. Runs and budgets

Every step below is confirm-first, with a cost estimate.

| step | what | budget |
|---|---|---|
| S1 spike | licences, sizes and schemas of the three datasets (no download beyond metadata) | $0 |
| S2 spike | 3 rows per LLM endpoint: structured output, `temperature 0`, gpt-oss low reasoning effort accepted; `system.serving.endpoint_usage` readable (first read confirm-first) | ≈ $0.01 LLM |
| P pilot | 50 rows per dataset per judge; measured tokens/row replace the estimates | ≈ $0.10 LLM |
| 1 | pass 1: shared sample, all four judges | est. ≈ $5.50–6.30 LLM, ≈ $0.05 Jev |
| 2 | pass 2: `--fresh` rerun of pass 1 (run-to-run noise) | same as pass 1 |
| 3 | Jev at scale (§2) | est. ≈ $0.25 Jev |

- **LLM cap: $15 total** (Databricks pay-per-token, Azure subscription). Before each LLM pass the
  runner projects cost = measured spend so far (from `system.serving.endpoint_usage` × published DBU
  rate × $0.070/DBU) + pilot tokens/row × remaining rows × rate, and refuses to start above the cap.
- **Jev** (TypeSafe credit, ≈ $3.20 left): tracked from the ledger as in demo 05; total estimate
  ≈ $0.35.
- Prices (Azure Premium, $0.070/DBU, checked 2026-10-01): gpt-oss-20b $0.07 / $0.30 per 1M
  input / output tokens; llama-3.3-70b $0.50 / $1.50; claude-sonnet-5-5 $2.00 / $10.00 (+10% with
  regional processing). Re-checked before pass 1. All estimates in this table are labelled
  estimates until replaced by measured numbers.
- If `endpoint_usage` is unavailable, LLM cost is a tokenizer estimate, labelled as such everywhere
  it appears.

## 7. Scoring and pre-registration

- Before pass 1, `docs/eval-results.md` records: the frozen prompts and test wording, the swap seed
  and family table, the sample definitions, and the headline comparisons:
  1. per dataset, F1 of Jev vs each LLM (decision level), with Wilson 95% intervals for P and R;
     for wanderbricks also the false-alarm rate on the natural states (the control);
  2. per dataset, cost per 1,000 rows and wall time per judge;
  3. Banking77 recall on random vs near-miss swaps, per judge.
- Fairness: changing a prompt or sentence after pass 1 means rerunning all judges and logging
  before/after; never tuning one judge.
- Scorecard per dataset × judge: P, R, F1 (Wilson intervals), errors, requests, tokens, cost
  (measured / estimated label), wall time; baseline row.
- Side analyses (reported separately from the headline): calibration (Brier score, reliability
  table) from probabilities; each LLM thresholded like Jev; an agreement matrix (rows only Jev /
  only LLMs / nobody catches); possible key errors (§2).
- Logging: only live runs started by the scorer are appended, one entry per (pass, judge), with the
  dbt invocation id, endpoint, tokens and cost source. SIMULATED runs are refused.

## 8. Repo layout and tests

- Copied from demo 05 and adapted: `src/jevdbx` (databricks client, deploy, evallog, pricing),
  `scripts/dbtw.py`, `scripts/jev_env.py`, macros `jev_expect`, `jev_judge`, `jev_question`,
  `jev_render`, `jev_summary`, `tests/test_no_workspace_identifiers.py`. dbt project `bench/`.
- New: `scripts/fetch_data.py` (download/upload, confirm-first flags), `scripts/make_keys.py`
  (swap seeding, family table, pair ids), `scripts/score.py` (benchmark scorer), `scripts/show.py`,
  the budget guard (`src/jevdbx/budget.py`).
- Offline tests: single-source prompt rendering; cache key includes the judge; deterministic swap
  seeding and family table; wanderbricks rule; scorer math and Wilson intervals; budget-guard
  arithmetic; identifier scan. Integration (SIMULATED, dev warehouse): both judge paths end to end,
  `failOnError => false` error rows counted, once-per-row checks.

## 9. Publishing

Same flow as demo 05: full-history scan, `git subtree add` into `jev-demos`, README table row,
CHANGELOG entry, README results from logged runs only, local video page (real casts and generated
scenes, including cost-vs-F1 per dataset), LinkedIn post on a Tuesday morning with Jev in the hook
and the repo named at the end.

## 10. Rules (carried from demo 05)

- Never read, print or log `.env`, secrets, tokens or the TypeSafe key; never a PAT.
- Numbers in README, changelog, video and posts come from logged live runs; estimates are labelled.
- Never edit keys, swap lists, family tables or baselines to make a judge win; key corrections only
  when demonstrably wrong, logged.
- Commits use `info@datagobes.dev` (repo-local git config; the global identity is a client email).
