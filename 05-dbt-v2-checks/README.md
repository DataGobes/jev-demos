# dbt v2 checks × an LLM judge

Can dbt v2's native **checks** call a custom or external function, so that a check can ask an
LLM judge (Jev, by TypeSafe) whether a column's description matches the column?

**Short answer: not in a way you can ship.** A check is a SQL query that dbt runs at parse
time, on its own in-memory DuckDB, over parse-safe metadata. You can put Jinja macros and
DuckDB macros in it. You cannot make one per-row call to anything outside DuckDB with stock
extensions, and the check never sees a model's SQL or inferred column types anyway. So the
judge runs next to dbt instead: a small CLI that reads the dbt information schema Parquet and
reports failures the way a check does (0 rows = pass).

The evidence, with every source line and command: **[FINDINGS.md](FINDINGS.md)**.

## What's here

| Path | What it is |
|---|---|
| `project/` | a 4-model DuckDB dbt project. Most column descriptions are accurate, four are deliberately wrong, one is subtly wrong, one is missing |
| `project/checks/` | native checks: a trivial one (`columns_have_descriptions`) and the mock judge written two ways, as a Jinja macro and as a DuckDB macro |
| `src/desc_judge/` | the fallback: `Judge` interface, `MockJudge`, a verdict cache, change detection, and the `desc-judge` CLI |
| `probes/` | what DuckDB 1.5.4 (the engine dbt pins for checks) accepts when SQL arrives the way dbt sends a check |
| `tests/` | the fallback's tests, including parity between the SQL and Python versions of the mock judge |

The judge is a **mock**: a deterministic keyword rule, not Jev and not an LLM. Nothing here
calls an external API. Its verdicts show that the pipeline works; they say nothing about Jev's
accuracy.

## Run it

```bash
uv sync
uv run pytest -q          # tests the fallback on an information schema built from project/
uv run ruff check

# Against a real dbt v2 run (dbt v2 must be installed, see FINDINGS.md §0):
cd project
dbt check   --profiles-dir .
dbt compile --profiles-dir . --generate-info-schema --static-analysis strict   # strict, or compiled_code is NULL
cd .. && uv run desc-judge --info-schema project/target/info_schema/v1

# Every dbt step FINDINGS.md quotes, logged to probes/logs/ (includes the probe checks):
DBT=dbt probes/run_dbt_evidence.sh
```

`desc-judge` options that matter in CI:

- `--state <baseline info_schema/v1>`: judge only columns whose name, type, description or SQL
  differ from the baseline (e.g. main's). This is a column-level `state:modified`; dbt's own
  one ignores description edits.
- `--cache <file>` (default `.desc_judge_cache.json`): verdicts keyed on
  `(judge id, sha256(name, type, description, sql))`. An unchanged column is never judged twice.
- `--select <unique_id> ...`, `--warn`, `--format json`. Exit code 1 when a row fails.

## Swapping the mock for Jev

Write one class in `src/desc_judge/judges.py` with an `id` and a batched
`judge(items) -> list[Verdict]`, and add it to `JUDGES`. The cache, change detection and
reporting don't know which judge they are talking to, and the judge id is part of the cache
key, so Jev never reuses a mock verdict.
