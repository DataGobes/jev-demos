# CLAUDE.md

Semantic dbt tests demo: four `jev_expect` tests, written as English sentences in
`jaffle_shop/models/staging/schema.yml`, call TypeSafe's Jev model through a dbt-duckdb plugin
to catch structurally-valid-but-semantically-wrong rows, scored against a hidden answer key and
a regex baseline. Spec: `docs/superpowers/specs/2026-09-24-jev-dbt-semantic-tests-design.md`.

## Commands
- Sync: `uv sync`
- Seeds (deterministic, seed=42): `uv run python scripts/make_seeds.py`
- dbt, demo mode (offline, no key needed): `cd jaffle_shop && JEV_MODE=demo uv run dbt build --profiles-dir . --exclude tag:semantic && JEV_MODE=demo uv run dbt test --profiles-dir . --select tag:semantic`
- dbt, live (needs `.env` with `TYPESAFE_API_KEY`): `cd jaffle_shop && uv run dbt build --profiles-dir . --exclude tag:semantic && uv run dbt test --profiles-dir . --select tag:semantic`
- Tests: `uv run pytest -q` · fast only (skip the end-to-end dbt build): `uv run pytest -q -m "not slow"`
- Lint: `uv run ruff check`
- Failure viewer: `uv run python scripts/show_failures.py`
- Scorecard: `uv run python scripts/score.py` · fresh live run appended to `docs/eval-results.md`: `uv run python scripts/score.py --run --fresh --mode live --append`
- Recording: `scripts/record.sh [--cold] [--pack N] [--no-captions]` (captions, title and end card built in) · smoke-test in demo mode only, never live: `yes '' | JEV_MODE=demo DOTENV_DISABLE=1 TYPE_DELAY=0 scripts/record.sh`

## Rules
- Never read, print, or log `.env` or `TYPESAFE_API_KEY`. The key stays inside the plugin process.
- Always use the project's own dbt: `uv run dbt`, or `source .venv/bin/activate` first. Never the
  machine's global `dbt` binary — that's dbt Fusion, which cannot load the Python adapter plugin
  this project depends on (see README "Why dbt-core, not Fusion").
- The `judged` CTE in `jaffle_shop/macros/jev_expect.sql` must stay `as materialized`, and
  `jev_noul` must stay registered with `side_effects=True`. Both are required together — DuckDB
  otherwise evaluates the UDF twice (once in the projection, once pushed into the scan filter),
  double-billing every judgment. Removing either one breaks "one evaluation per row" silently;
  there's no test that catches it by itself, only the judgment-count-equals-row-count assertion
  in the slow dbt-integration test.
- A `SIMULATED` run (no `TYPESAFE_API_KEY`, or `JEV_MODE=demo`) must always show `SIMULATED` in
  the summary line and must never be reported, screenshotted, or written to
  `docs/eval-results.md` as if it were a real number.
- Never edit `scripts/pools/*.toml`, `eval/golden_defects.csv`, or `jaffle_shop/tests/baseline/`
  to make Jev win. The golden key and baseline are the yardstick; if a test fails the gate, fix
  question wording or `threshold` first (log before/after in `docs/eval-results.md`), then
  consider a golden-key correction only if the key is demonstrably wrong (log it), else drop or
  reframe the test and say so.
- Changing `fails_if`, `criteria`, or `threshold` on any `jev_expect` block changes model
  behaviour: rerun `uv run python scripts/score.py --run --fresh --append` (live, from the repo
  root) and let it append the new numbers to `docs/eval-results.md` before trusting or recording
  the result.
