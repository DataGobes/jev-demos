# Jev semantic dbt tests — design

Date: 2026-09-24 · Status: approved in chat, executing autonomously · Repo: `~/Projects/jev-demo-4`

## 1. What this is

A LinkedIn screen-recording demo, fourth in the Jev series (Cringe-o-Meter, semsql, VISUALIZE).
An extended **jaffle_shop** dbt project where every standard dbt test passes, then four
`jev_expect` tests — written as English sentences in `schema.yml` — catch rows that are
structurally valid but semantically wrong. Each flagged row carries a probability. A scorecard
compares Jev against a hand-written regex/keyword baseline on a hidden answer key.

Deliverable: a public demo repo and a repeatable terminal recording. Not a package (no PyPI,
no dbt hub). Code is laid out so the plugin + macro could be extracted later, nothing more.

## 2. Decisions taken in the brainstorm

| Decision | Choice |
|---|---|
| Deliverable | Story first: demo repo + recording |
| Warehouse | DuckDB, local |
| dbt | **dbt-core 1.12.5 + dbt-duckdb 1.11.0** (latest stable, 2026-09-15 / 2026-08-07). The machine's global `dbt` is dbt Fusion 2.0 preview, which cannot load Python adapter plugins; dbt-core 2.0 is rc8 and also Fusion-based. Revisit when 2.0 is stable. |
| Other pins | duckdb 1.5.5, typesafe-sdk 0.7.1, pyarrow, numpy, python-dotenv; Python 3.13; uv |
| Mechanism | Approach A: dbt-duckdb plugin registers a Python UDF; a generic SQL test macro calls it |
| Dataset | Classic jaffle_shop + returns, reviews, tickets |
| Tests | code-vs-text mismatch, stars-vs-sentiment, junk customer names, PII in ticket text |

A spike (scratchpad, 2026-09-24) confirmed on these pins: plugin `configure_connection` can
register an Arrow UDF; a generic test with `arguments:` compiles and fails correctly;
`store_failures` persists the `jev_p` column; an `on-run-end` macro can `run_query("select jev_stats()")`
and log it; a `name:` key gives the test a readable name. It also found that DuckDB inlines the
CTE and evaluates the UDF twice (projection + filter) — hence `as materialized` below.

## 3. Repo layout

```
jev-demo-4/
  pyproject.toml     uv project, package `jevdbt` under src/
  .env               TYPESAFE_API_KEY (gitignored; never read or printed)
  src/jevdbt/
    plugin.py        dbt-duckdb Plugin: initialize(config) builds Scorer; configure_connection registers UDFs
    udf.py           jev_noul(state VARCHAR, question VARCHAR) -> DOUBLE (Arrow); jev_stats() -> VARCHAR
    questions.py     Question(instructions, criteria) parsed from the macro's JSON; key() for caching
    scorer.py        dedupe, sqlite cache, pack N rows/request, concurrency + rpm pacing (port of semsql engine)
    backend.py       JevBackend (typesafe-sdk, Noul) | DemoBackend (deterministic, SIMULATED)
    cache.py         sqlite (model, question, state) -> float
    stats.py         thread-safe counters + summary line formatting
  jaffle_shop/       dbt project (dbt_project.yml, profiles.yml, seeds/, models/, macros/, tests/baseline/)
  scripts/
    make_seeds.py    deterministic seed + golden-key generator (seed=42) from text pools
    pools/*.toml     authored text pools, each entry tagged clean | defect | hard_negative
    score.py         precision/recall per test from stored failures vs the golden key; Jev vs baseline
    record.sh        typewriter runner for the recording, keypress between beats
  eval/golden_defects.csv   answer key — deliberately NOT a seed, never enters the warehouse
  docs/eval-results.md      every live scoring run, appended with date, pack, model, numbers
  tests/             pytest
```

The same module-level `Scorer`/`Stats` singleton serves all dbt threads (dbt runs in one process;
the spike confirmed one PID).

## 4. The `jev_expect` generic test

YAML (dbt 1.12 form — custom args under `arguments:`):

```yaml
- name: comment
  data_tests:
    - jev_expect:
        name: returns_comment_matches_reason_code
        arguments:
          fails_if: "The comment describes a different reason for the return than `reason_code`"
          context: [reason_code]
          threshold: 0.8
          criteria:
            "true": "The customer's stated reason plainly belongs to another code"
            "false": "Consistent with the code, or too vague to tell"
        config: {severity: error, store_failures: true, tags: [semantic]}
```

Arguments: `fails_if` (required, phrased as the defect so "yes" = failing row), `context`
(list of extra columns, default `[]`), `threshold` (default `0.5`), `criteria` (optional
`{"true", "false"}` dict). dbt's own `where`, `severity`, `warn_if`/`error_if`, `store_failures`,
`tags` apply unchanged.

Compiles to:

```sql
with judged as materialized (
  select *, jev_noul(
      to_json(struct_pack(comment := comment, reason_code := reason_code)),
      '{"instructions": "...", "criteria": {...}}') as jev_p
  from {{ model }}
)
select * from judged where jev_p >= 0.8
```

State is named JSON fields (the judged column first, then context columns). Rows with NULL in
the judged column get `jev_p = NULL` and never fail (not_null owns that). The macro validates
arguments at compile time (`fails_if` non-empty, `0 < threshold <= 1`, `criteria` keys) with
`exceptions.raise_compiler_error`.

## 5. UDF, scorer, backends

- `jev_noul(state, question)`: Arrow UDF. Groups the batch by question string, calls
  `scorer.score_many(states, question)` once per group, returns float64 (NULL for NULL state or
  a failed judgment).
- Scorer (ported from semsql `engine.py`): dedupe identical states, sqlite cache lookup, chunk
  misses into packs of `pack`, run under `asyncio.Semaphore(concurrency)` and an rpm pacer on a
  background loop thread. Default `pack=1`, `concurrency=32`, `rpm=1200` (the API's documented
  ceiling, 1,200 requests/min).
- Packing: `state = {"rows": {"r000": {...}, "r001": {...}}}`, one Noul per row with
  instructions prefixed `Judge ONLY the record in \`rows.r000\`, ignoring all other rows.`;
  column references in the user's instructions are rewritten from `` `x` `` to `` `rows.r000.x` ``.
  pack=1 sends the record itself as state with no prefix.
- Errors: a failed request yields NULL values for that chunk, increments `errors`, and records
  `last_error`; the summary line shows errors in red-worthy text. A test run with any errors is
  never used as a scored or recorded result.
- `JevBackend` uses `AsyncTypeSafeClient.system_one(state, {id: Noul(instructions, criteria)})`.
  Verify the 0.7.1 SDK signature for `criteria` on Noul against the installed package before use.
- `DemoBackend`: deterministic, offline, `simulated=True` (semsql's token-overlap heuristic,
  keyed on the question + state). Selected automatically when `TYPESAFE_API_KEY` is absent, or
  forced by plugin config `mode: demo`.
- Plugin config (profiles.yml `plugins[].config`): `mode: auto|live|demo`, `pack`, `concurrency`,
  `rpm`, `cache_path` (default `.jev_cache.sqlite`), `model` (default `jev-latest`). Env
  overrides `JEV_MODE`, `JEV_PACK`, `JEV_NO_CACHE=1` so the recording and scoring scripts can
  switch without editing YAML. `.env` loaded with python-dotenv from the repo root.

## 6. Run summary

`jev_stats()` returns counters as JSON; macro `jev_summary()` runs `on-run-end` and logs one
line only when judgments > 0:

```
Jev · 1,312 judgments · 38% cached · 164 requests · 7.9 s · $0.004 · LIVE jev-latest pack=8
```

`s` is wall time spent inside `jev_noul` calls. Cost uses the documented per-token price
(constant in `stats.py` with a source link; verify against current TypeSafe pricing docs when
implementing). `SIMULATED` replaces `LIVE` in demo mode; `· N errors` is appended when non-zero.

## 7. Data

Classic jaffle_shop tables plus three text tables, generated by `make_seeds.py` (seed=42).

| Seed | Rows | Planted defects | Hard negatives |
|---|---|---|---|
| `raw_customers` (id, first_name, last_name, email) | 500 | ~25 junk: `test test`, `asdfgh`, `Acme Logistics BV`, email pasted into a name | ~25 real-but-odd: surname `Test`, `Bo Li`, `Xavi`, `O'Neill-Ødegaard` |
| `raw_orders` (classic) | ~1,500 | — | — |
| `raw_returns` (id, order_id, reason_code, comment) | 200 | ~12 comment contradicts code | ~20 ambiguous/blended but consistent |
| `raw_reviews` (id, order_id, stars, body) | 400 | ~24 flipped (5★ "never again", 1★ rave) | ~30 sarcasm matching its low rating, mixed 3★ |
| `raw_tickets` (id, customer_id, subject, body) | 200 | ~14 PII in prose (street address, phone, IBAN, personal email) | ~25 order numbers, the store's address, first name only |

About 1,300 judged rows per full semantic run. Sizes were cut from the ~2,500 discussed in
chat because at pack=1 the 1,200 rpm ceiling means ~20 rows/s; ~1,300 rows keeps a pack=1 run
near a minute and a packed run within seconds.

Constraints:
- Every planted defect is structurally valid: `unique`, `not_null`, `accepted_values`,
  `relationships` all pass. `dbt build` excluding `tag:semantic` and `tag:baseline` is fully green.
- Texts come from authored pools (`scripts/pools/*.toml`, written once by a subagent, varied in
  voice, length, typos), not templates. The generator fills names/products/dates so rows do not
  repeat verbatim. Pools are part of the end-of-work review.
- Golden key `eval/golden_defects.csv`: `test_name, table, id, label` (`defect | hard_negative`;
  unlisted rows are clean).

## 8. Baseline and scoring

**Baseline** = what an analytics engineer would hand-write in ~30 minutes, as dbt singular tests
under `jaffle_shop/tests/baseline/` tagged `baseline` with `store_failures: true`:
PII regexes (IBAN, NL/intl phone, email, postcode + house number), per-reason-code keyword
lists, a small sentiment lexicon vs stars, junk-name patterns (repeated tokens, no vowels,
company suffixes, `@`). Written before any live Jev results are seen, and not weakened afterwards.
It runs in the same dbt project, so the post can show "the regex version" side by side.

**`score.py`** reads the stored-failure tables for both tags, joins the golden key, and prints a
per-test table: precision, recall, flagged count, for Jev and baseline; plus which hard negatives
each flagged. `--pack N` and `--mode` flow through env to a fresh `dbt test` run with
`JEV_NO_CACHE=1` when `--fresh`. Every live run appends to `docs/eval-results.md`.

**Gate before recording** (live, no errors): Jev precision ≥ 0.85 and recall ≥ 0.85 on every
test, at the pack size used on camera, and Jev beats the baseline on F1 on every test. If pack>1
fails the gate where pack=1 passes, record at pack=1. If a test fails the gate: first fix
question wording or threshold (logged in eval-results with before/after), then a golden-key
correction only if the key is demonstrably wrong (logged), else drop or reframe the test and
say so. Never edit data to make Jev win.

## 9. Recording

`scripts/record.sh` — typewriter-types each command, waits for a keypress between beats.

1. `dbt build --exclude tag:semantic tag:baseline` → all green. *"Every test green. Ship it?"*
2. `git diff` of `schema.yml` adding the four `jev_expect` blocks. *"Tests written as sentences."*
3. `dbt test --select tag:semantic` → 4 × FAIL n + summary line. *"Structurally valid. Semantically wrong."*
4. `duckdb` query on stored failures — best three rows with `jev_p`. *"Every flag comes with a probability."*
5. `python scripts/score.py` scorecard, Jev vs regex baseline. *"vs. what you'd hand-write."*
6. Optional: rerun 3 → fully cached, sub-second. *"Safe to run in CI."*

Beat 2 needs the repo in a state where the `jev_expect` blocks show as a diff: `record.sh`
works on a scratch copy and applies the blocks as a patch, never touching the committed repo.

Honesty: summary always shows LIVE/SIMULATED; beats 3–5 recorded only after the gate passes;
numbers in the post are the numbers `score.py` printed.

## 10. Testing

pytest, all offline (DemoBackend or a fake backend):
- questions: JSON parse, key stability, criteria round-trip, validation errors.
- scorer: dedupe, cache hit/miss, packing split + order preservation, NULL handling, error → NULL.
- packing: instruction prefix and column-reference rewrite.
- udf: register on a bare duckdb connection, call with grouped questions, NULL state → NULL.
- stats: summary formatting (LIVE/SIMULATED, errors suffix, thousands separators).
- dbt integration (slow marker): `dbt build` of the real project in demo mode in a temp copy —
  standard tests pass, semantic tests produce stored failures with `jev_p`, UDF evaluated once
  per row (judgment count == row count on a cold cache), summary line logged.
- seeds: deterministic output for seed=42; every defect row passes the structural constraints;
  golden key ids exist.
- `ruff check` clean.

## 11. Out of scope

LinkedIn post copy, web UI, packaging/publishing, Score/Choice test variants, per-row warn
bands, entity resolution (next demo), the Jev-vs-frontier-LLM benchmark (jev-demo-2 hand-off).
