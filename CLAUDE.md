# CLAUDE.md

Semantic dbt tests on Databricks: four `jev_expect` tests, written as English sentences in
`jaffle_shop/models/staging/schema.yml` (plus one on ~100k real product reviews), judged by
TypeSafe's Jev model through a Unity Catalog Python function (`jev_demo.jev.noul_pack`), scored
against a hidden answer key and a regex baseline. Demo 04 (`~/Projects/jev-demo-4`, read-only)
is the predecessor and the yardstick. Spec:
`docs/superpowers/specs/2026-09-30-jev-dbt-databricks-design.md` (the authority; amendments are
dated inside it).

## Commands
- Sync: `uv sync`
- Host and warehouse for dbt (no tokens printed): `eval "$(uv run python scripts/jev_env.py)"`
  (production warehouse: `--warehouse jev-demo-5-prod`)
- Platform DDL, print only: `uv run python scripts/deploy.py` · apply to the dev warehouse
  (standing OK, see below): `uv run python scripts/deploy.py --apply [--only noul_pack noul_pack_demo]` ·
  production schema + volume (confirm-first): `uv run python scripts/deploy.py --production --apply`
- dbt: always through `scripts/dbtw.py` (adds `--profiles-dir . --target dev` and a short-lived
  token from the logged-in CLI profile; runs in `jaffle_shop/`):
  - demo mode (SIMULATED, no Jev call): `JEV_MODE=demo uv run python scripts/dbtw.py build --exclude tag:production tag:production_baseline`
  - yardstick, live: `uv run python scripts/dbtw.py build --exclude tag:production tag:production_baseline`
  - production, live: `uv run python scripts/dbtw.py build --vars '{production: true}' --select +tag:production tag:production_baseline`
- Judging happens only when the `jev_expect` tests are selected (`build --select +tag:semantic`);
  `dbt run`, `dbt retry` (dbt leaves `selected_resources` empty) or a build that excludes them never
  calls Jev (the hook reads `selected_resources`); rerun `dbt build --select +tag:semantic`.
- Tests: `uv run pytest -q` (offline) · integration on the dev warehouse, demo mode only:
  `uv run pytest -m databricks -q`
- Lint: `uv run ruff check`
- Views: `uv run python scripts/show.py tests|rows|score|function`
- Scorecard: `uv run python scripts/score.py` (what is stored) · a fresh live run, appended to
  `docs/eval-results.md`: `uv run python scripts/score.py --run --fresh --mode live --append`
  (`--append` needs `--run`) · production: `uv run python scripts/score.py --production --run --rerun --mode live --append`
- Production data: `scripts/fetch_reviews.py` (`--source`, `--upload`, `--upload-part2`;
  `--download` only after the user said yes), `scripts/audit_sample.py` (blind audit CSV)
- Bundle (dbt inside Databricks, serverless notebook job): `databricks bundle validate` is fine;
  `databricks bundle deploy` / `databricks bundle run jev_semantic_tests` are confirm-first
- Recording: `scripts/record.sh [--cold] [--notebook] [--no-production] [--no-captions]` · smoke test, demo mode only,
  never live: `yes '' | JEV_MODE=demo TYPE_DELAY=0 scripts/record.sh`

## Rules
- Never read, print or log `.env`, secrets, tokens or the TypeSafe key. The key lives only in the
  UC secret `jev_demo.jev.typesafe_api_key`, which **the user** creates; Claude only references it
  by name. Never put the key in a command, file, environment variable or chat.
- Never use a personal access token. dbt gets a short-lived token from the CLI profile
  (`scripts/dbtw.py`, env var `DBT_ENV_SECRET_DATABRICKS_TOKEN`, which dbt scrubs from logs); the
  notebook uses the SDK's notebook auth. Do not switch to a PAT, even if auth breaks: report it.
- No workspace host, warehouse id, storage account or tenant in any committed file. They come
  from the environment (`scripts/jev_env.py`) or are looked up by name.
- A `SIMULATED` run (`JEV_MODE=demo`) must always show `SIMULATED` and must never be reported,
  screenshotted or written to `docs/eval-results.md` as a result. Numbers in the README,
  changelog and posts come from logged live runs only.
- Never edit `scripts/pools/*.toml`, `eval/golden_defects.csv` or the regex baselines in
  `jaffle_shop/tests/baseline/` and `jaffle_shop/tests/production_baseline/` to make Jev win. If a test fails
  the gate: question wording or `threshold` first (log before/after in `docs/eval-results.md`),
  a golden-key correction only if the key is demonstrably wrong (log it), else drop or reframe the
  test and say so.
- Changing `fails_if`, `criteria` or `threshold` on any `jev_expect` block changes model
  behaviour: rerun `uv run python scripts/score.py --run --fresh --mode live --append` (live) and
  let it append the numbers before trusting or recording the result.
- `jaffle_shop/macros/jev_question.sql` is the single place for the question JSON, the state
  expression and the cache key. The hook and the test both use it; never duplicate them.
- The function body modules (`src/jevdbx/noul_pack.py`, `demo_pack.py`) are embedded verbatim into
  `CREATE FUNCTION ... AS $$ ... $$`: no `from __future__` imports, no `$$` inside, stdlib only.
  After changing one, `deploy.py --apply --only <function>` (a test checks the body round-trips).
- Databricks SQL does not escape a quote by doubling it: `'don''t'` reads as two literals
  (`dont`). Inside a SQL literal write `\'`. Porting DuckDB SQL: `''` becomes `\'`.
- Seeds load through `jevdbx.dbt_cli` (run dbt via `scripts/dbtw.py`, never bare `dbt`): plain
  dbt-core reads the surname "Null" (customer 477, a golden hard negative) as NULL.
- Never modify demo 04 (`~/Projects/jev-demo-4`); read it only.

## Confirm-first vs standing OK
- Standing OK (user, 2026-09-30): any query on the 2X-Small dev warehouse `jev-demo-5`,
  including `deploy.py --apply` for the `jev_demo.jev` objects and demo-mode dbt and integration runs.
- Ask first, every time: live Jev runs (TypeSafe billing), `deploy.py --production --apply` and the
  production volume upload, creating a warehouse (`jev-demo-5-prod`), any download
  (`fetch_reviews.py --download`), `databricks bundle deploy` / `bundle run` (creates a job),
  reading `system.billing`, dropping schemas (`jev_demo.spike`).
- The user creates the UC secret and labels the audit sample. Claude does neither.
