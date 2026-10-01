# Demo 06 — Jev vs LLMs through `ai_query` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One dbt test, `jev_expect`, judged by Jev or by three `ai_query` LLMs (switch: `--vars '{judge: …}'`), on Banking77 triage, Abt-Buy duplicate pairs and `samples.wanderbricks.reviews`, scored against ground truth with measured cost.

**Architecture:** Demo 05's judging post-hook and Delta cache, copied and extended with a `judge` var: the Jev path packs rows into `jev_demo.jev.noul_pack` (unchanged), the LLM path is one set-based `ai_query(...)` per test with a JSON-schema response `{decision, probability}`. The question, prompt, state and cache key come from one macro file. A Python scorer reads the dbt stored failures plus the judgments table, computes P/R/F1 with Wilson intervals, guards the $15 LLM budget and appends logged live runs to `docs/eval-results.md`.

**Tech Stack:** Python 3.13, uv, dbt-core via `dbt-databricks==1.12.5`, `databricks-sdk`, Databricks SQL (serverless 2X-Small warehouse `jev-demo-5`), Unity Catalog, `ai_query`, pytest, ruff, `dbt-duckdb==1.11.0` (offline macro rendering only).

**Spec:** `docs/superpowers/specs/2026-10-01-jev-vs-ai-query-design.md` (read it with this plan).

## Global Constraints

- Repo `~/Projects/jev-demo-6`; git `user.email` is `info@datagobes.dev` (repo-local; never commit with the global identity).
- Never read, print or log `.env`, secrets, tokens or the TypeSafe key. No PAT, ever: dbt gets a short-lived token from the CLI profile (`scripts/dbtw.py`).
- No workspace host, warehouse id, storage account or tenant in any committed file (`tests/test_no_workspace_identifiers.py`).
- Confirm-first, every time, with a cost estimate: live Jev runs, any `ai_query` call against a real endpoint, downloads, uploads, creating schema `jev_demo.bench` or volume `jev_demo.bench.raw`, first read of `system.serving.*`. Standing OK: other queries on the 2X-Small warehouse `jev-demo-5`.
- SIMULATED (`JEV_MODE=demo`) output is never logged or quoted as a result. Numbers in docs come from logged live runs; estimates are labelled.
- LLM cap: **$15** total (Databricks pay-per-token, $0.070/DBU). Jev: ≈ $0.35 estimated of ≈ $3.20 TypeSafe credit.
- Judges: `jev` (default), `databricks-gpt-oss-20b`, `databricks-meta-llama-3-3-70b-instruct`, `databricks-claude-opus-5`. Temperature 0 for every LLM.
- Reused, never redeployed: `jev_demo.jev.noul_pack`, `jev_demo.jev.noul_pack_demo`, UC secret `jev_demo.jev.typesafe_api_key`. Never modify `~/Projects/jev-demo-5` (read only).
- Databricks SQL: `''` is not a quote escape; write `\'` and double backslashes (`jev_sql_string`, `sql_string`).
- Never edit keys, swap lists, family tables or baselines to make a judge win.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File map

| path | responsibility |
|---|---|
| `pyproject.toml`, `CLAUDE.md`, `README.md` | project, rules, run instructions |
| `src/jevdbx/databricks.py`, `dbt_cli.py`, `pricing.py` | copied from demo 05 verbatim (SQL client, dbt entry, Jev price) |
| `src/jevdbx/deploy.py` | DDL for schema `jev_demo.bench`: judgments, hook_runs, requests view, `llm_demo`, raw volume |
| `src/jevdbx/keys.py` | ground-truth construction: intent families, swaps, samples, Jaccard, wanderbricks rule |
| `src/jevdbx/metrics.py` | P/R/F1, Wilson, Brier, reliability, agreement |
| `src/jevdbx/budget.py` | LLM prices, usage SQL, projection, $15 guard |
| `src/jevdbx/evallog.py` | eval-log entry formatting and spend parsing |
| `scripts/dbtw.py`, `scripts/jev_env.py` | dbt wrapper and env exports (copied, adapted) |
| `scripts/probe_endpoints.py` | spike S2: 3-row `ai_query` probe per endpoint |
| `scripts/deploy.py` | print/apply platform DDL |
| `scripts/fetch_data.py` | download sources, write parquet, upload to the volume |
| `scripts/make_keys.py` | write committed keys and dbt seeds |
| `scripts/score.py` | build + score + budget guard + eval-log append + pre-registration |
| `scripts/show.py` | terminal views for the video |
| `bench/` | dbt project: macros, models, seeds, baselines |
| `eval/` | committed ground truth and `sources.toml` |
| `tests/` | offline tests; `tests/integration/` SIMULATED tests on the dev warehouse |

---

### Task 1: Repo scaffold, copied modules, identifier scan

**Files:**
- Create: `pyproject.toml`, `CLAUDE.md`, `src/jevdbx/__init__.py`, `scripts/dbtw.py`, `scripts/jev_env.py`, `tests/__init__.py`, `tests/test_no_workspace_identifiers.py`, `tests/test_dbtw.py`
- Copy verbatim from `~/Projects/jev-demo-5`: `src/jevdbx/databricks.py`, `src/jevdbx/dbt_cli.py`, `src/jevdbx/pricing.py`, `tests/test_databricks_client.py`

**Interfaces:**
- Produces: `jevdbx.databricks.Sql(profile=None, warehouse=None).run(sql) -> Result(state, columns, rows, error)`, `Result.scalar()`, `dbt_env()`; `scripts/dbtw.py` runs dbt in `bench/` (`build_command(argv) -> list[str]`, `PROJECT_DIR`); `jevdbx.pricing.PRICE_PER_MTOK_USD`, `cost_usd(tokens)`.

- [ ] **Step 1: Copy the verbatim files and write `pyproject.toml`**

```bash
cd ~/Projects/jev-demo-6
mkdir -p src/jevdbx scripts tests/integration bench eval docs
D5=~/Projects/jev-demo-5
cp $D5/src/jevdbx/databricks.py $D5/src/jevdbx/dbt_cli.py $D5/src/jevdbx/pricing.py src/jevdbx/
cp $D5/tests/test_databricks_client.py tests/
cp $D5/scripts/jev_env.py scripts/
printf '"""Jev vs LLMs through ai_query, as dbt semantic tests on Databricks (demo 06)."""\n' > src/jevdbx/__init__.py
touch tests/__init__.py tests/integration/__init__.py
```

`pyproject.toml`:

```toml
[project]
name = "jevdbx"
version = "0.1.0"
description = "Jev vs LLMs (ai_query) as dbt semantic tests on Databricks (demo 06)"
requires-python = ">=3.13"
dependencies = [
    "dbt-databricks==1.12.5",
    "databricks-sdk",
    "pyarrow>=21",
    "rich>=14",
    "pyyaml>=6",
]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.12", "dbt-duckdb==1.11.0", "duckdb>=1.5"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/jevdbx"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: runs dbt (offline render target)",
    "databricks: talks to the Databricks workspace (SIMULATED mode only); run with -m databricks",
]
addopts = "-m 'not databricks'"

[tool.ruff]
line-length = 100
src = ["src", "scripts"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 2: Write `scripts/dbtw.py` (demo 05's, project dir `bench/`)**

```python
"""Run dbt in bench/ authenticated with a short-lived token from the Databricks CLI profile.

    uv run python scripts/dbtw.py build --vars '{judge: jev}' --select +tag:semantic
    # -> dbt build ... --profiles-dir . --target dev

The token and the environment are never printed.
"""

import os
import subprocess
import sys
from pathlib import Path

from jevdbx.databricks import dbt_env

PROJECT_DIR = Path(__file__).resolve().parents[1] / "bench"


def build_command(argv: list[str]) -> list[str]:
    """dbt arguments with `--profiles-dir .` and `--target dev` added unless already given."""
    args = list(argv)
    if not any(a == "--profiles-dir" or a.startswith("--profiles-dir=") for a in args):
        args += ["--profiles-dir", "."]
    if not any(a in ("--target", "-t") or a.startswith("--target=") for a in args):
        args += ["--target", "dev"]
    return args


def dbt_executable() -> list[str]:
    return [sys.executable, "-m", "jevdbx.dbt_cli"]


def main(argv=None) -> int:
    args = build_command(sys.argv[1:] if argv is None else argv)
    env = {**os.environ, **dbt_env()}
    return subprocess.run([*dbt_executable(), *args], cwd=PROJECT_DIR, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Write the failing tests**

`tests/test_dbtw.py`:

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("dbtw", ROOT / "scripts" / "dbtw.py")
dbtw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbtw)


def test_adds_profiles_dir_and_target():
    assert dbtw.build_command(["build"]) == ["build", "--profiles-dir", ".", "--target", "dev"]


def test_keeps_explicit_target():
    assert dbtw.build_command(["build", "--target", "render"]) == [
        "build", "--target", "render", "--profiles-dir", "."]


def test_project_dir_is_bench():
    assert dbtw.PROJECT_DIR == ROOT / "bench"
```

`tests/test_no_workspace_identifiers.py`: copy demo 05's file, then change only `ALLOWED` and `SKIP`:

```bash
cp ~/Projects/jev-demo-5/tests/test_no_workspace_identifiers.py tests/
```

```python
# (path, exact matched text): fake values in test fixtures.
ALLOWED = {
    ("tests/test_databricks_client.py", "azuredatabricks" + ".net"),
}
SKIP = re.compile(r"^bench/seeds/.*\.csv$")
```

and in `test_the_scanner_catches_each_pattern` replace the last assertion line with:

```python
    assert findings("tests/test_databricks_client.py", "azuredatabricks" + ".net") == []
```

- [ ] **Step 4: Sync and run the tests**

Run: `uv sync && uv run pytest -q && uv run ruff check`
Expected: all pass (`test_dbtw` 3, identifier scan 2, copied client tests), ruff clean.

- [ ] **Step 5: Write `CLAUDE.md`**

```markdown
# CLAUDE.md

Demo 06: one dbt test, `jev_expect`, judged by Jev or by LLMs through `ai_query`
(`--vars '{judge: …}'`), on Banking77 triage, Abt-Buy duplicate pairs and
`samples.wanderbricks.reviews`. Spec: `docs/superpowers/specs/2026-10-01-jev-vs-ai-query-design.md`;
plan: `docs/superpowers/plans/2026-10-01-jev-vs-ai-query.md`. Demo 05 (`~/Projects/jev-demo-5`) is
read only.

## Commands
- Sync `uv sync` · tests `uv run pytest -q` · integration (SIMULATED, dev warehouse)
  `uv run pytest -m databricks -q` · lint `uv run ruff check`
- dbt only through `uv run python scripts/dbtw.py …` (runs in `bench/`)
- Platform DDL: `uv run python scripts/deploy.py` (print) · `--apply` (confirm-first the first time)
- Score: `uv run python scripts/score.py` (stored) · live pass:
  `uv run python scripts/score.py --run --judge <judge> --scope <pilot|sample|full> --pass <n> --mode live --append`

## Rules
- Never read/print/log `.env`, secrets, tokens or the TypeSafe key; never a PAT.
- No workspace host, warehouse id, storage account or tenant in a committed file.
- Confirm-first: live Jev runs, real `ai_query` calls, downloads, uploads, creating
  `jev_demo.bench` or its volume, first read of `system.serving.*`. Standing OK: other queries on the
  2X-Small warehouse `jev-demo-5`.
- SIMULATED output is never logged or quoted. Numbers come from logged live runs; estimates labelled.
- LLM cap $15 (enforced by `scripts/score.py`); prompts frozen after pre-registration: a change means
  rerunning every judge and logging before/after.
- `bench/macros/jev_question.sql` is the single place for question, prompt, state and key.
- Never edit keys, swap lists, family tables or baselines to make a judge win.
- git `user.email` is repo-local `info@datagobes.dev` (the global one is a client address).
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock CLAUDE.md src scripts tests
git commit -m "chore: scaffold demo 06 from demo 05's client, dbt wrapper and identifier scan

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Spike S1 — data sources, licences, sizes (no data download)

**Files:**
- Create: `eval/sources.toml`
- Modify: `docs/superpowers/specs/2026-10-01-jev-vs-ai-query-design.md` (dated amendment with what S1 found)

**Interfaces:**
- Produces: `eval/sources.toml` with keys `[banking77] train_url test_url licence rows_train rows_test` and `[abt_buy] table_a_url table_b_url train_url valid_url test_url licence pairs_test matches_test`, read by `scripts/fetch_data.py` (Task 8).

- [ ] **Step 1: Check the Banking77 source headers (HEAD only, no body)**

```bash
for f in train test; do curl -sIL "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/$f.csv" | grep -iE '^(HTTP|content-length)'; done
```

Expected: `HTTP/2 200` and a content length for each. If not 200, search the Hugging Face card `PolyAI/banking77` for its file URLs and use those.

- [ ] **Step 2: Read the licences (pages, not data)**

Fetch the Banking77 README (`https://github.com/PolyAI-LDN/task-specific-datasets`) and the Hugging Face card; confirm CC BY 4.0 and the citation (Casanueva et al., 2020). For Abt-Buy, fetch the DeepMatcher datasets page (`https://github.com/anhaidgroup/deepmatcher/blob/master/Datasets.md`) and the Leipzig benchmark page (`https://dbs.uni-leipzig.de/research/projects/benchmark-datasets-for-entity-resolution`); record the stated terms and the exact URLs of the `Textual/Abt-Buy` experiment files (`tableA.csv`, `tableB.csv`, `train.csv`, `valid.csv`, `test.csv`). HEAD-check each URL as in Step 1. If Abt-Buy's terms forbid redistribution of pair ids or its files are unreachable, switch to `Structured/Amazon-Google` (same layout) and record that.

- [ ] **Step 3: Write `eval/sources.toml`** with the verified values (row counts from the dataset pages, marked `# from page`; Task 15 Step 1 checks them against the download):

```toml
[banking77]
train_url = "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/train.csv"
test_url = "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/test.csv"
licence = "CC BY 4.0"
citation = "Casanueva et al. 2020, Efficient Intent Detection with Dual Sentence Encoders"
rows_train = 10003   # from page
rows_test = 3080     # from page

[abt_buy]
# exact URLs and terms as verified in Step 2
```

The `[abt_buy]` table gets the five URLs, `licence`, `citation`, `pairs_test` and `matches_test` exactly as found (no placeholder values may be committed: if a value is unknown, the step is not done).

- [ ] **Step 4: Amend the spec** with a dated `*Amended 2026-10-0X (S1):*` paragraph under §2 naming the chosen entity-matching dataset, its terms and sizes.

- [ ] **Step 5: Commit**

```bash
git add eval/sources.toml docs/superpowers/specs/2026-10-01-jev-vs-ai-query-design.md
git commit -m "docs: S1 data sources, licences and sizes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Spike S2 — `ai_query` probe (confirm-first, ≈ $0.01)

**Files:**
- Create: `scripts/probe_endpoints.py`, `tests/test_probe_endpoints.py`
- Modify: spec (dated amendment with what S2 found)

**Interfaces:**
- Consumes: `jevdbx.databricks.Sql`
- Produces: `probe_sql(endpoint: str, reasoning_low: bool) -> str`; `RESPONSE_FORMAT: str` (the JSON-schema literal reused by Task 6 via `bench/dbt_project.yml` var `jev_llm_response_format`); findings: the field names of the `failOnError => false` struct, whether `reasoning_effort` is accepted, whether `system.serving.endpoint_usage` is readable and its column names.

- [ ] **Step 1: Write the failing test**

```python
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("probe", ROOT / "scripts" / "probe_endpoints.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_response_format_is_a_strict_json_schema():
    rf = json.loads(probe.RESPONSE_FORMAT)
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    props = rf["json_schema"]["schema"]["properties"]
    assert props == {"decision": {"type": "boolean"}, "probability": {"type": "number"}}


def test_probe_sql_calls_ai_query_without_failing_on_error():
    sql = probe.probe_sql("databricks-gpt-oss-20b", reasoning_low=True)
    assert "ai_query('databricks-gpt-oss-20b'" in sql
    assert "failOnError => false" in sql and "'temperature', 0.0" in sql
    assert "'reasoning_effort', 'low'" in sql
    assert "reasoning_effort" not in probe.probe_sql("databricks-claude-sonnet-5-5", False)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_probe_endpoints.py -q`
Expected: FAIL (file not found).

- [ ] **Step 3: Implement `scripts/probe_endpoints.py`**

```python
"""Spike S2: 3 fixed rows through each LLM endpoint with ai_query (confirm-first: billed).

    uv run python scripts/probe_endpoints.py --print            # SQL only, no call
    uv run python scripts/probe_endpoints.py --run              # 3 rows x 3 endpoints
    uv run python scripts/probe_endpoints.py --usage            # columns of system.serving tables
"""

import argparse
import json

from jevdbx.databricks import Sql

ENDPOINTS = ["databricks-gpt-oss-20b", "databricks-meta-llama-3-3-70b-instruct",
             "databricks-claude-sonnet-5-5"]
RESPONSE_FORMAT = json.dumps({
    "type": "json_schema",
    "json_schema": {
        "name": "judgment",
        "schema": {"type": "object",
                   "properties": {"decision": {"type": "boolean"},
                                  "probability": {"type": "number"}},
                   "required": ["decision", "probability"], "additionalProperties": False},
        "strict": True,
    },
})
ROWS = [
    "Statement: the review contradicts its rating.\nrecord = {\"comment\": \"Terrible stay\", \"rating\": 4.8}",
    "Statement: the review contradicts its rating.\nrecord = {\"comment\": \"Lovely place\", \"rating\": 4.9}",
    "Statement: the review contradicts its rating.\nrecord = {\"comment\": \"Lovely place\", \"rating\": 1.2}",
]


def _lit(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def probe_sql(endpoint: str, reasoning_low: bool) -> str:
    params = "'temperature', 0.0" + (", 'reasoning_effort', 'low'" if reasoning_low else "")
    rows = " union all ".join(f"select {_lit(r)} as prompt" for r in ROWS)
    return (f"select prompt, ai_query({_lit(endpoint)}, prompt, "
            f"responseFormat => {_lit(RESPONSE_FORMAT)}, "
            f"modelParameters => named_struct({params}), failOnError => false) as r "
            f"from ({rows})")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--print", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--usage", action="store_true")
    a = ap.parse_args(argv)
    if a.print:
        for e in ENDPOINTS:
            print(probe_sql(e, e.startswith("databricks-gpt-oss")), end="\n\n")
        return
    sql = Sql()
    if a.usage:
        for t in ("endpoint_usage", "served_entities"):
            r = sql.run(f"select column_name, data_type from system.information_schema.columns "
                        f"where table_schema = 'serving' and table_name = '{t}'")
            print(t, r.error or r.rows)
        return
    for e in ENDPOINTS:
        for low in ([True, False] if e.startswith("databricks-gpt-oss") else [False]):
            r = sql.run(probe_sql(e, low))
            print(f"== {e} reasoning_low={low}: {r.state} {r.error or ''}")
            print("   columns:", r.columns)
            for row in r.rows:
                print("  ", row)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_probe_endpoints.py -q`
Expected: PASS (2).

- [ ] **Step 5: Ask the user, then probe (live, billed ≈ $0.01)**

Ask: "Spike S2 sends 3 short rows to each of the three endpoints (4 probe sets: gpt-oss twice, with and without low reasoning effort; ≈ 1–2k tokens in total, est. under $0.01), and reads the column list of `system.serving.endpoint_usage` and `served_entities` (first read of `system.serving`). OK?" Only on yes:

Run: `DATABRICKS_CONFIG_PROFILE=jev-demo-5 uv run python scripts/probe_endpoints.py --run` then `--usage`.
Expected: per endpoint 3 rows; the `r` struct's field names (expected `response`, `errorMessage`); `response` is a JSON string `{"decision": …, "probability": …}`; gpt-oss either accepts `reasoning_effort` or errors on it; the usage table columns (expected `served_entity_id`, `request_time`, `input_token_count`, `output_token_count`).

- [ ] **Step 6: Record the findings** as a dated amendment under spec §4 (struct field names, response shape, reasoning-effort result, usage-table columns and whether it was readable). If the field names differ from `response`/`errorMessage`, write the actual names into the amendment: Task 6 uses the amended names. If `reasoning_effort` errors, Task 6's `jev_llm_reasoning_low` var is the empty list.

- [ ] **Step 7: Commit**

```bash
git add scripts/probe_endpoints.py tests/test_probe_endpoints.py docs/superpowers/specs
git commit -m "spike: S2 ai_query structured output, parameters and usage table

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Platform DDL for `jev_demo.bench`

**Files:**
- Create: `src/jevdbx/deploy.py`, `scripts/deploy.py`, `tests/test_deploy.py`

**Interfaces:**
- Produces: `Target(catalog="jev_demo", schema="bench", function_schema="jev")`, `Target.fq(name)`, `sql_string(value) -> str`, `judgments_table_sql(t)`, `hook_runs_table_sql(t)`, `requests_view_sql(t)`, `llm_demo_function_sql(t)`, `raw_volume_sql(t)`, `platform_statements(t=None) -> list[tuple[str, str]]`. Judgments columns used by later tasks: `key, judge, test_name, model_name, question, state, p, decision, requested_model, answered_model, mode, layout, pack_uuid, pack_rows, pack_tokens, pack_est_tokens, attempts, retry_statuses, error, started_at, finished_at, invocation_id, judged_at`. hook_runs columns: `invocation_id, judge, test_name, model_name, mode, requested_model, tested, missing, oversized, inserted, started_at, finished_at`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from jevdbx import deploy


def test_target_names_and_safety():
    t = deploy.Target()
    assert t.fq("judgments") == "jev_demo.bench.judgments"
    assert t.fn("noul_pack") == "jev_demo.jev.noul_pack"
    with pytest.raises(ValueError):
        deploy.Target(schema="bench; drop")


def test_judgments_has_judge_and_decision():
    sql = deploy.judgments_table_sql(deploy.Target())
    assert sql.startswith("CREATE TABLE IF NOT EXISTS jev_demo.bench.judgments")
    assert "judge STRING" in sql and "decision BOOLEAN" in sql and "CLUSTER BY (key)" in sql


def test_hook_runs_records_judge_and_window():
    sql = deploy.hook_runs_table_sql(deploy.Target())
    assert "judge STRING" in sql and "started_at TIMESTAMP" in sql and "finished_at TIMESTAMP" in sql


def test_llm_demo_is_deterministic_and_has_ai_query_shape():
    sql = deploy.llm_demo_function_sql(deploy.Target())
    assert "jev_demo.bench.llm_demo(endpoint STRING, prompt STRING)" in sql
    assert "RETURNS STRUCT<result: STRING, errorMessage: STRING>" in sql
    assert "sha2(concat(endpoint, prompt), 256)" in sql
    assert "SIMULATED error" in sql   # every 97th prompt errors, to exercise the error path


def test_platform_statements_order():
    labels = [label for label, _ in deploy.platform_statements()]
    assert labels == ["schema", "raw volume", "judgments", "hook_runs", "requests", "llm_demo"]


def test_sql_string_escapes_for_databricks():
    assert deploy.sql_string("don't \\ x") == "'don\\'t \\\\ x'"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_deploy.py -q` → FAIL (`jevdbx.deploy` missing).

- [ ] **Step 3: Implement `src/jevdbx/deploy.py`**

```python
"""Platform DDL for demo 06: schema jev_demo.bench, judgments ledger, hook_runs, requests view,
the SIMULATED LLM stand-in llm_demo, and the raw-data volume. The Jev functions live in
jev_demo.jev (deployed by demo 05) and are only referenced."""

import re
from dataclasses import dataclass

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Target:
    catalog: str = "jev_demo"
    schema: str = "bench"
    function_schema: str = "jev"

    def __post_init__(self):
        for value in (self.catalog, self.schema, self.function_schema):
            if not _IDENT.match(value):
                raise ValueError(f"not a safe identifier: {value!r}")

    def fq(self, name: str) -> str:
        return f"{self.catalog}.{self.schema}.{name}"

    def fn(self, name: str) -> str:
        return f"{self.catalog}.{self.function_schema}.{name}"


def sql_string(value: str) -> str:
    """A Databricks SQL string literal: quotes become \\' and backslashes are doubled."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def judgments_table_sql(t: Target) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {t.fq('judgments')} (
  key STRING, judge STRING, test_name STRING, model_name STRING, question STRING, state STRING,
  p DOUBLE, decision BOOLEAN, requested_model STRING, answered_model STRING, mode STRING,
  layout STRING, pack_uuid STRING, pack_rows INT, pack_tokens BIGINT, pack_est_tokens BIGINT,
  attempts INT, retry_statuses ARRAY<INT>, error STRING,
  started_at TIMESTAMP, finished_at TIMESTAMP, invocation_id STRING, judged_at TIMESTAMP
) CLUSTER BY (key)
COMMENT 'Judgments by Jev and by ai_query LLMs: cache (successful rows) and ledger. jev-demo-6.'"""


def hook_runs_table_sql(t: Target) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {t.fq('hook_runs')} (
  invocation_id STRING, judge STRING, test_name STRING, model_name STRING, mode STRING,
  requested_model STRING, tested BIGINT, missing BIGINT, oversized BIGINT, inserted BIGINT,
  started_at TIMESTAMP, finished_at TIMESTAMP
)
COMMENT 'One row per (dbt invocation, jev_expect test) written by the jev_judge post-hook.'"""


def requests_view_sql(t: Target) -> str:
    return f"""CREATE OR REPLACE VIEW {t.fq('requests')} AS
SELECT pack_uuid,
       any_value(invocation_id) AS invocation_id, any_value(test_name) AS test_name,
       any_value(mode) AS mode, any_value(answered_model) AS answered_model,
       any_value(pack_rows) AS pack_rows, any_value(pack_tokens) AS pack_tokens,
       any_value(pack_est_tokens) AS pack_est_tokens, any_value(attempts) AS attempts,
       any_value(retry_statuses) AS retry_statuses, any_value(error) AS error,
       min(started_at) AS started_at, max(finished_at) AS finished_at, count(*) AS rows_written
FROM {t.fq('judgments')}
WHERE pack_uuid IS NOT NULL
GROUP BY pack_uuid"""


def llm_demo_function_sql(t: Target) -> str:
    """SIMULATED stand-in for ai_query(..., failOnError => false): same return shape, a
    hash-derived probability, no network. Every 97th prompt returns an error."""
    return f"""CREATE OR REPLACE FUNCTION {t.fq('llm_demo')}(endpoint STRING, prompt STRING)
RETURNS STRUCT<result: STRING, errorMessage: STRING>
COMMENT 'SIMULATED stand-in for ai_query: hash values, no network. jev-demo-6.'
RETURN (
  WITH h AS (SELECT sha2(concat(endpoint, prompt), 256) AS d)
  SELECT CASE
    WHEN pmod(conv(substr(d, 9, 8), 16, 10), 97) = 0
      THEN named_struct('result', CAST(NULL AS STRING), 'errorMessage', 'SIMULATED error')
    ELSE named_struct(
      'result', to_json(named_struct(
          'decision', conv(substr(d, 1, 8), 16, 10) / 4294967295.0 > 0.5,
          'probability', round(conv(substr(d, 1, 8), 16, 10) / 4294967295.0, 4))),
      'errorMessage', CAST(NULL AS STRING))
  END FROM h
)"""


def raw_volume_sql(t: Target) -> str:
    return (f"CREATE VOLUME IF NOT EXISTS {t.fq('raw')} "
            "COMMENT 'Parquet files written by scripts/fetch_data.py. jev-demo-6.'")


def platform_statements(t: Target | None = None) -> list[tuple[str, str]]:
    t = t or Target()
    return [
        ("schema", f"CREATE SCHEMA IF NOT EXISTS {t.catalog}.{t.schema} "
                   "COMMENT 'Demo 06: Jev vs LLMs (ai_query) as dbt semantic tests.'"),
        ("raw volume", raw_volume_sql(t)),
        ("judgments", judgments_table_sql(t)),
        ("hook_runs", hook_runs_table_sql(t)),
        ("requests", requests_view_sql(t)),
        ("llm_demo", llm_demo_function_sql(t)),
    ]
```

- [ ] **Step 4: Implement `scripts/deploy.py`**

```python
"""Print (default) or apply the demo 06 platform DDL on the dev warehouse.

    uv run python scripts/deploy.py                 # print only
    uv run python scripts/deploy.py --apply         # confirm-first the first time (creates schema)
    uv run python scripts/deploy.py --apply --only llm_demo requests
"""

import argparse
import sys

from jevdbx.databricks import Sql
from jevdbx.deploy import platform_statements


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    stmts = platform_statements()
    known = {label for label, _ in stmts}
    if a.only and set(a.only) - known:
        print(f"unknown labels: {sorted(set(a.only) - known)}; known: {sorted(known)}")
        return 2
    chosen = [(label, sql) for label, sql in stmts if not a.only or label in a.only]
    if not a.apply:
        for label, sql in chosen:
            print(f"-- {label}\n{sql};\n")
        return 0
    sql = Sql()
    for label, stmt in chosen:
        r = sql.run(stmt)
        print(f"{label}: {r.state} {r.error or ''}")
        if r.state != "SUCCEEDED":
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_deploy.py -q && uv run ruff check` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/jevdbx/deploy.py scripts/deploy.py tests/test_deploy.py
git commit -m "feat(deploy): jev_demo.bench ledger with judge and decision, llm_demo stand-in, raw volume

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: dbt project and the single-source question / prompt / key macros

**Files:**
- Create: `bench/dbt_project.yml`, `bench/profiles.yml`, `bench/macros/jev_question.sql`, `bench/macros/jev_render.sql`, `bench/models/staging/stg_fixture.sql`, `bench/models/staging/schema.yml` (fixture test only, replaced in Task 9), `tests/dbt_helpers.py`, `tests/test_jev_question.py`

**Interfaces:**
- Consumes: S2 findings (Task 3) for `jev_llm_response_format`, `jev_llm_reasoning_low`, struct field names.
- Produces (macros): `jev_mode()`, `jev_relation(name)`, `jev_function()`, `jev_sql_string(s)`, `jev_rewrite(text)`, `jev_question(fails_if, criteria=none) -> json str`, `jev_judge_name()`, `jev_is_llm()`, `jev_judge_model()`, `jev_layout()`, `jev_state_expr(column_name, context=[])`, `jev_key_expr(state_expr, question_json)`, `jev_prompt_expr(question_json, state_expr) -> SQL expr`, `jev_llm_call(prompt_expr) -> SQL expr`. Render macros for tests: `jev_render_question`, `jev_render_key`, `jev_render_prompt`, `jev_render_llm_call`. Python: `tests.dbt_helpers.render(macro, args, env=None, vars=None) -> str`.

- [ ] **Step 1: Write `bench/dbt_project.yml` and `bench/profiles.yml`**

```yaml
name: bench
version: "1.0.0"
profile: bench
model-paths: ["models"]
seed-paths: ["seeds"]
macro-paths: ["macros"]
test-paths: ["tests"]

on-run-end:
  - "{{ jev_summary() }}"

vars:
  jev_catalog: jev_demo
  jev_schema: bench
  jev_function_schema: jev       # noul_pack / noul_pack_demo deployed by demo 05
  jev_mode: live                 # env JEV_MODE=demo (SIMULATED) overrides
  judge: jev                     # or one of jev_llm_endpoints
  jev_model: jev-1.13.0          # pinned; part of the cache key
  jev_prompt_version: p1         # bump only with a logged rerun of every judge
  jev_pack_token_budget: 48000
  jev_pack_max_rows: 256
  jev_row_token_limit: 30000
  jev_max_concurrency: 4
  jev_price_per_mtok_usd: 0.042  # https://docs.typesafe.ai/models
  jev_llm_endpoints:
    - databricks-gpt-oss-20b
    - databricks-meta-llama-3-3-70b-instruct
    - databricks-claude-opus-5
  jev_llm_reasoning_low: [databricks-gpt-oss-20b]   # Task 3 (S2): [] if the endpoint rejects it
  jev_llm_response_format: '{"type": "json_schema", "json_schema": {"name": "judgment", "schema": {"type": "object", "properties": {"decision": {"type": "boolean"}, "probability": {"type": "number"}}, "required": ["decision", "probability"], "additionalProperties": false}, "strict": true}}'
  bench_scope: sample            # pilot | sample | full

models:
  bench:
    +materialized: table
    +post-hook: "{{ jev_judge() }}"
```

`bench/profiles.yml` (same as demo 05's, renamed; `render` is offline DuckDB for pytest):

```yaml
bench:
  target: dev
  outputs:
    dev:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST', 'unset') }}"
      http_path: "{{ env_var('JEV_HTTP_PATH', 'unset') }}"
      token: "{{ env_var('DBT_ENV_SECRET_DATABRICKS_TOKEN', 'unset') }}"
      catalog: jev_demo
      schema: bench
      threads: 4
    render:
      type: duckdb
      path: ":memory:"
      threads: 1
```

- [ ] **Step 2: Write `bench/macros/jev_question.sql`**

Copy demo 05's `jaffle_shop/macros/jev_question.sql`, keep `jev_mode`, `jev_relation`, `jev_sql_string`, `jev_rewrite`, `jev_question`, `jev_state_expr` unchanged, and replace `jev_function` and `jev_key_expr`, then append the new macros:

```sql
{% macro jev_function() %}
  {{ return(var('jev_catalog') ~ '.' ~ var('jev_function_schema') ~ '.'
            ~ ('noul_pack' if jev_mode() == 'live' else 'noul_pack_demo')) }}
{% endmacro %}

{% macro jev_judge_name() %}
  {%- set j = var('judge', 'jev') | string -%}
  {%- if j != 'jev' and j not in var('jev_llm_endpoints') -%}
    {{ exceptions.raise_compiler_error("jev: judge must be 'jev' or one of "
        ~ (var('jev_llm_endpoints') | join(', ')) ~ ", got '" ~ j ~ "'") }}
  {%- endif -%}
  {{ return(j) }}
{% endmacro %}

{% macro jev_is_llm() %}{{ return(jev_judge_name() != 'jev') }}{% endmacro %}

{#- the model id in the cache key and the ledger: Jev's pinned version, or the endpoint name -#}
{% macro jev_judge_model() %}
  {{ return(jev_judge_name() if jev_is_llm() else var('jev_model')) }}
{% endmacro %}

{% macro jev_layout() %}{{ return('row' if jev_is_llm() else 'nested') }}{% endmacro %}

{% macro jev_key_expr(state_expr, question_json) %}
  {{ return("sha2(concat_ws(chr(31), " ~ jev_sql_string(jev_judge_model()) ~ ", "
            ~ jev_sql_string(jev_mode()) ~ ", " ~ jev_sql_string(jev_layout()) ~ ", "
            ~ jev_sql_string(var('jev_prompt_version')) ~ ", " ~ jev_sql_string(question_json)
            ~ ", " ~ state_expr ~ "), 256)") }}
{% endmacro %}

{#- The LLM prompt, built from the same question JSON Jev receives (single source). -#}
{% macro jev_prompt_expr(question_json, state_expr) %}
  {%- set q = fromjson(question_json) -%}
  {%- set head = "You judge one database record against a statement.\nStatement: "
                 ~ q['instructions'] ~ "\n" -%}
  {%- if q.get('criteria') -%}
    {%- set head = head ~ "Answer true when: " ~ q['criteria']['true'] ~ "\n"
                        ~ "Answer false when: " ~ q['criteria']['false'] ~ "\n" -%}
  {%- endif -%}
  {%- set head = head ~ "record = " -%}
  {%- set tail = "\nReturn JSON: \"decision\" is true if the statement holds for the record, "
                 ~ "else false; \"probability\" is your probability (0 to 1) that it holds." -%}
  {{ return("concat(" ~ jev_sql_string(head) ~ ", " ~ state_expr ~ ", " ~ jev_sql_string(tail) ~ ")") }}
{% endmacro %}

{#- One LLM call (live: ai_query; demo: the SIMULATED llm_demo). Returns the
    STRUCT<result STRING, errorMessage STRING> expression (S2: field `result`). -#}
{% macro jev_llm_call(prompt_expr) %}
  {%- set endpoint = jev_judge_name() -%}
  {%- if jev_mode() == 'demo' -%}
    {{ return(jev_relation('llm_demo') ~ "(" ~ jev_sql_string(endpoint) ~ ", " ~ prompt_expr ~ ")") }}
  {%- endif -%}
  {%- set params = "'temperature', 0.0" -%}
  {%- if endpoint in var('jev_llm_reasoning_low') -%}
    {%- set params = params ~ ", 'reasoning_effort', 'low'" -%}
  {%- endif -%}
  {{ return("ai_query(" ~ jev_sql_string(endpoint) ~ ", " ~ prompt_expr
            ~ ", responseFormat => " ~ jev_sql_string(var('jev_llm_response_format'))
            ~ ", modelParameters => named_struct(" ~ params ~ "), failOnError => false)") }}
{% endmacro %}
```

S2 (spec §4 amendment) found the struct fields `result` / `errorMessage`; `llm_demo` (Task 4) and Task 6's `parsed` CTE use `result`.

- [ ] **Step 3: Write `bench/macros/jev_render.sql`** (pytest helpers; offline `render` target)

```sql
{% macro jev_render_question(fails_if, criteria=none) %}
  {{ print('-- BEGIN\n' ~ jev_question(fails_if, criteria) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_key(column_name, context, fails_if, criteria=none) %}
  {%- set q = jev_question(fails_if, criteria) -%}
  {{ print('-- BEGIN\n' ~ jev_key_expr(jev_state_expr(column_name, context), q) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_prompt(column_name, context, fails_if, criteria=none) %}
  {%- set q = jev_question(fails_if, criteria) -%}
  {{ print('-- BEGIN\n' ~ jev_prompt_expr(q, jev_state_expr(column_name, context)) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_llm_call() %}
  {{ print('-- BEGIN\n' ~ jev_llm_call("'P'") ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_state(column_name, context) %}
  {{ print('-- BEGIN\n' ~ jev_state_expr(column_name, context) ~ '\n-- END') }}
{% endmacro %}
```

A placeholder model so the project parses before Task 9 — `bench/models/staging/stg_fixture.sql`:

```sql
select 1 as id, 'x' as body
```

and `bench/models/staging/schema.yml`:

```yaml
version: 2
models:
  - name: stg_fixture
```

- [ ] **Step 4: Write `tests/dbt_helpers.py`**

```python
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
BENCH = ROOT / "bench"


def dbt(*args, env=None) -> subprocess.CompletedProcess:
    """Run dbt offline (DuckDB `render` target) in bench/. JEV_MODE comes only from `env`."""
    full_env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false", **(env or {})}
    if env is None or "JEV_MODE" not in env:
        full_env.pop("JEV_MODE", None)
    return subprocess.run(
        ["uv", "run", "dbt", *args, "--profiles-dir", ".", "--target", "render"],
        cwd=BENCH, capture_output=True, text=True, env=full_env, timeout=300,
    )


def render(macro: str, args: dict, env=None, vars: dict | None = None) -> str:
    """Run a jev_render_* macro; return what it printed between the BEGIN/END markers."""
    extra = ["--vars", json.dumps(vars)] if vars else []
    out = dbt("run-operation", macro, "--args", json.dumps(args), *extra, env=env)
    m = re.search(r"-- BEGIN\n(.*?)\n-- END", out.stdout, re.S)
    assert m, f"no output from {macro}:\n{out.stdout}\n{out.stderr}"
    return m.group(1)
```

- [ ] **Step 5: Write the failing tests** — `tests/test_jev_question.py`

```python
import json

import pytest

from tests.dbt_helpers import render

FAILS_IF = "The customer's `query` is not about its labelled `intent`."
CRITERIA = {"true": "The `query` asks about another topic", "false": "Fits `intent`"}
ARGS = {"column_name": "query", "context": ["intent"], "fails_if": FAILS_IF, "criteria": CRITERIA}
LLM = "databricks-claude-opus-5"


@pytest.mark.slow
def test_prompt_carries_the_same_sentence_and_criteria_as_jev_question():
    q = json.loads(render("jev_render_question", {"fails_if": FAILS_IF, "criteria": CRITERIA}))
    prompt = render("jev_render_prompt", ARGS)
    # the literals in the SQL escape quotes as \' ; compare after unescaping
    flat = prompt.replace("\\'", "'")
    assert q["instructions"] in flat
    assert q["criteria"]["true"] in flat and q["criteria"]["false"] in flat
    assert "to_json(named_struct('query', `query`, 'intent', `intent`))" in prompt
    assert "record.query" in flat  # backticked fields are rewritten exactly as for Jev


@pytest.mark.slow
def test_key_depends_on_judge_layout_and_prompt_version():
    jev = render("jev_render_key", ARGS)
    llm = render("jev_render_key", ARGS, vars={"judge": LLM})
    assert "'jev-1.13.0'" in jev and "'nested'" in jev and "'p1'" in jev
    assert f"'{LLM}'" in llm and "'row'" in llm
    assert jev != llm


@pytest.mark.slow
def test_unknown_judge_is_rejected():
    from tests.dbt_helpers import dbt
    out = dbt("run-operation", "jev_render_llm_call", "--vars", json.dumps({"judge": "gpt-9"}))
    assert out.returncode != 0 and "judge must be 'jev' or one of" in out.stdout


@pytest.mark.slow
def test_llm_call_live_uses_ai_query_with_schema_temperature_and_no_fail():
    call = render("jev_render_llm_call", {}, vars={"judge": "databricks-gpt-oss-20b"})
    assert call.startswith("ai_query('databricks-gpt-oss-20b', 'P'")
    assert "responseFormat => '{\"type\": \"json_schema\"" in call
    assert "named_struct('temperature', 0.0, 'reasoning_effort', 'low')" in call
    assert call.endswith("failOnError => false)")
    sonnet = render("jev_render_llm_call", {}, vars={"judge": LLM})
    assert "reasoning_effort" not in sonnet


@pytest.mark.slow
def test_llm_call_demo_uses_the_simulated_stand_in():
    call = render("jev_render_llm_call", {}, env={"JEV_MODE": "demo"}, vars={"judge": LLM})
    assert call == f"jev_demo.bench.llm_demo('{LLM}', 'P')"
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_jev_question.py -q`
Expected: first run FAILS until the macros exist; after Steps 1–4 all 5 PASS.

- [ ] **Step 7: Commit**

```bash
git add bench tests/dbt_helpers.py tests/test_jev_question.py
git commit -m "feat(dbt): judge switch; one source for question, LLM prompt, state and key

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Judging hook (Jev and LLM paths), the test, the run summary

**Files:**
- Create: `bench/macros/jev_judge.sql`, `bench/macros/jev_expect.sql`, `bench/macros/jev_summary.sql`, `tests/test_jev_judge_sql.py`, `tests/test_jev_expect_sql.py`
- Modify: `bench/macros/jev_render.sql` (add `jev_render_judge`, `jev_render_expect`), `bench/models/staging/schema.yml` (one `jev_expect` on `stg_fixture` for rendering)

**Interfaces:**
- Consumes: Task 5 macros.
- Produces: `jev_judge()` post-hook; `jev_judge_sql(t, relation) -> {"count", "insert", "inserted"}`; test `jev_expect(model, column_name, fails_if, context=[], threshold=0.5, criteria=none)` returning `tested.* , jev_p, jev_decision, jev_judge, jev_mode, jev_invocation_id`; `jev_summary()` on-run-end. Ledger semantics: a successful judgment is `p is not null or decision is not null`; Jev flags `p >= threshold` (demo 05's rule); an LLM flags `decision = true`.

- [ ] **Step 1: Write `bench/macros/jev_judge.sql`**

Start from demo 05's `jaffle_shop/macros/jev_judge.sql` and apply exactly these changes:

1. `jev_tests_for` unchanged.
2. In `jev_judge_sql`, the cache filter becomes judge-aware through the key and success-aware:

```sql
  left anti join (
    select key from {{ judgments }}
    where (p is not null or decision is not null) and question = {{ jev_sql_string(question) }}
  ) done
    on done.key = tested.key
```

3. `count_sql` for an LLM judge counts no oversized rows:

```sql
select (select count(*) from tested) as tested,
       count(*) as missing,
       {{ "count_if(false)" if jev_is_llm() else "count_if(est > " ~ limit ~ ")" }} as oversized
from missing
```

4. The insert column list gains `judge` (after `key`) and `decision` (after `p`); the Jev SELECT emits `{{ jev_sql_string(jev_judge_name()) }}` and `cast(null as boolean)` in those positions, `{{ jev_sql_string(jev_judge_model()) }}` as `requested_model` (was `model_lit`, same value for Jev).
5. When `jev_is_llm()`, `insert_sql` is this instead of the pack SQL:

```sql
insert into {{ judgments }} (
  key, judge, test_name, model_name, question, state, p, decision, requested_model, answered_model,
  mode, layout, pack_uuid, pack_rows, pack_tokens, pack_est_tokens, attempts, retry_statuses,
  error, started_at, finished_at, invocation_id, judged_at
)
{{ common }},
called as (
  select key, state, est, {{ jev_llm_call(jev_prompt_expr(question, 'state')) }} as r
  from missing
),
parsed as (
  select key, state, est, r,
         from_json(r.result, 'decision BOOLEAN, probability DOUBLE') as j
  from called
)
select key, {{ jev_sql_string(jev_judge_name()) }}, {{ jev_sql_string(t.name) }},
       {{ jev_sql_string(t.attached_node.split('.')[-1]) }}, {{ jev_sql_string(question) }}, state,
       case when r.errorMessage is null and j.decision is not null then j.probability end,
       case when r.errorMessage is null then j.decision end,
       {{ jev_sql_string(jev_judge_model()) }}, {{ jev_sql_string(jev_judge_model()) }},
       {{ jev_sql_string(jev_mode()) }}, 'row',
       cast(null as string), cast(null as int), cast(null as bigint), est, 1,
       cast(null as array<int>),
       coalesce(r.errorMessage,
                case when j.decision is null
                     then concat('unparseable response: ', left(coalesce(r.result, ''), 200)) end),
       cast(null as timestamp), cast(null as timestamp),
       {{ jev_sql_string(invocation_id) }}, current_timestamp()
from parsed
```

(The prompt expression references the CTE column `state`: `jev_prompt_expr(question, 'state')`.)

6. In `jev_judge()`, record the window and the judge in `hook_runs`:

```sql
    {%- set started = modules.datetime.datetime.utcnow().isoformat() -%}
    {%- if missing > 0 -%}{%- do run_query(s['insert']) -%}{%- endif -%}
    {%- set finished = modules.datetime.datetime.utcnow().isoformat() -%}
    {%- set inserted = run_query(s['inserted']).columns[0].values()[0] | int -%}
    {%- do run_query("insert into " ~ jev_relation('hook_runs') ~ " values ("
          ~ jev_sql_string(invocation_id) ~ ", " ~ jev_sql_string(jev_judge_name()) ~ ", "
          ~ jev_sql_string(t.name) ~ ", " ~ jev_sql_string(model.name) ~ ", "
          ~ jev_sql_string(jev_mode()) ~ ", " ~ jev_sql_string(jev_judge_model()) ~ ", "
          ~ tested ~ ", " ~ missing ~ ", " ~ oversized ~ ", " ~ inserted ~ ", "
          ~ "timestamp" ~ jev_sql_string(started) ~ ", timestamp" ~ jev_sql_string(finished) ~ ")") -%}
    {%- do log(("Jev" if not jev_is_llm() else "LLM " ~ jev_judge_name()) ~ " · "
              ~ ('SIMULATED' if jev_mode() == 'demo' else 'LIVE') ~ " · " ~ t.name ~ " · "
              ~ tested ~ " tested · " ~ (missing - oversized) ~ " judged now · "
              ~ oversized ~ " too long", info=True) -%}
```

(the `inserted != missing` check stays as in demo 05).

- [ ] **Step 2: Write `bench/macros/jev_expect.sql`**

```sql
{#-
  Semantic test: returns rows the judge flags, plus rows with no successful judgment yet
  (jev_p and jev_decision NULL). Jev flags p >= threshold; an LLM flags decision = true.
  Judgments come from the jev_judge post-hook; the key includes the judge, so each judge's
  judgments are separate. Rows carry the judge, mode and invocation that wrote them.
-#}
{% test jev_expect(model, column_name, fails_if, context=[], threshold=0.5, criteria=none) %}
  {%- if threshold is not number or threshold <= 0 or threshold > 1 -%}
    {{ exceptions.raise_compiler_error("jev_expect: `threshold` must be in (0, 1], got " ~ threshold) }}
  {%- endif -%}
  {%- set question = jev_question(fails_if, criteria) -%}
  {%- set key = jev_key_expr(jev_state_expr(column_name, context), question) -%}

with tested as (
  select *, {{ key }} as __jev_key
  from {{ model }}
  where {{ adapter.quote(column_name) }} is not null
),
judged as (
  select key, p, decision from {{ jev_relation('judgments') }}
  where p is not null or decision is not null
)
select tested.* except (__jev_key), judged.p as jev_p, judged.decision as jev_decision,
       {{ jev_sql_string(jev_judge_name()) }} as jev_judge,
       {{ jev_sql_string(jev_mode()) }} as jev_mode,
       {{ jev_sql_string(invocation_id) }} as jev_invocation_id
from tested
left join judged on judged.key = tested.__jev_key
where judged.key is null
   or ({{ 'judged.decision = true' if jev_is_llm() else 'judged.p >= ' ~ threshold }})
{% endtest %}
```

- [ ] **Step 3: Write `bench/macros/jev_summary.sql`**

Copy demo 05's file (Jev line and once-per-row check unchanged), add to `jev_summary()` before the Jev branch:

```sql
  {%- if jev_is_llm() -%}
    {%- set w = run_query("select coalesce(sum(tested), 0), coalesce(sum(missing), 0),
          coalesce(sum(inserted), 0),
          coalesce((unix_micros(max(finished_at)) - unix_micros(min(started_at))) / 1e6, 0)
        from " ~ jev_relation('hook_runs') ~ " where invocation_id = " ~ inv) -%}
    {%- set e = run_query("select count_if(error is not null), count(*) from "
          ~ jev_relation('judgments') ~ " where invocation_id = " ~ inv) -%}
    {%- set tested = w.columns[0].values()[0] | int -%}
    {%- set missing = w.columns[1].values()[0] | int -%}
    {%- set inserted = w.columns[2].values()[0] | int -%}
    {%- set errors = e.columns[0].values()[0] | int -%}
    {%- set cached = ((tested - missing) * 100 / tested) if tested else 0 -%}
    {%- set label = 'SIMULATED' if jev_mode() == 'demo' else 'LIVE' -%}
    {%- do log("LLM · {} · {:,} judgments · {:.0f}% cached · {:,} calls · {:,} errors · {:.1f} s · {}".format(
          jev_judge_name(), tested - errors, cached, missing, errors, w.columns[3].values()[0] | float,
          label), info=True) -%}
    {%- do log("LLM · once-per-row {} · {}: {:,} inserted = {:,} missing".format(
          'OK' if inserted == missing else 'VIOLATED', label, inserted, missing), info=True) -%}
    {%- if inserted != missing -%}
      {{ exceptions.raise_compiler_error("jev: once-per-row VIOLATED for " ~ jev_judge_name()) }}
    {%- endif -%}
    {{ return('') }}
  {%- endif -%}
```

The duplicate-key check for Jev reads `where p is not null` → change to `where p is not null or decision is not null`.

- [ ] **Step 4: Add render helpers and a fixture test**

Append to `bench/macros/jev_render.sql`:

```sql
{% macro jev_render_judge(model_name) %}
  {%- set node = graph.nodes['model.bench.' ~ model_name] -%}
  {%- set parts = [] -%}
  {%- for t in jev_tests_for(node.unique_id, none) -%}
    {%- set s = jev_judge_sql(t, node.relation_name) -%}
    {%- do parts.append('-- count\n' ~ s['count'] ~ '\n-- insert\n' ~ s['insert'] ~ '\n-- inserted\n' ~ s['inserted']) -%}
  {%- endfor -%}
  {{ print('-- BEGIN\n' ~ (parts | join('\n')) ~ '\n-- END') }}
{% endmacro %}
```

`bench/models/staging/schema.yml`:

```yaml
version: 2
models:
  - name: stg_fixture
    columns:
      - name: body
        data_tests:
          - jev_expect:
              name: fixture_body_is_odd
              arguments:
                fails_if: "The `body` is odd."
                threshold: 0.8
              config: {severity: warn, store_failures: true, tags: [semantic]}
```

- [ ] **Step 5: Write the failing tests** — `tests/test_jev_judge_sql.py`

```python
import re

import pytest

from tests.dbt_helpers import dbt, render

LLM = "databricks-meta-llama-3-3-70b-instruct"


def _sections(text):
    return dict(re.findall(r"-- (\w+)\n(.*?)(?=\n-- \w+\n|\Z)", text, re.S))


@pytest.mark.slow
def test_jev_path_is_demo05s_pack_path_with_judge_column():
    ins = _sections(render("jev_render_judge", {"model_name": "stg_fixture"}))["insert"]
    assert ins.lstrip().startswith("insert into jev_demo.bench.judgments (")
    assert "key, judge, test_name" in ins and "p, decision, requested_model" in ins
    assert "jev_demo.jev.noul_pack(transform(items, x -> x.state)" in ins
    assert "(p is not null or decision is not null)" in ins
    assert "ai_query(" not in ins


@pytest.mark.slow
def test_llm_path_is_one_row_wise_ai_query_statement():
    s = _sections(render("jev_render_judge", {"model_name": "stg_fixture"}, vars={"judge": LLM}))
    ins = s["insert"]
    assert ins.count("ai_query(") == 1 and "noul_pack" not in ins
    assert "from_json(r.result, 'decision BOOLEAN, probability DOUBLE')" in ins
    assert "unparseable response" in ins and "r.errorMessage" in ins
    assert "'row'" in ins and f"'{LLM}'" in ins
    assert "count_if(false) as oversized" in s["count"]


@pytest.mark.slow
def test_llm_demo_path_calls_llm_demo():
    ins = _sections(render("jev_render_judge", {"model_name": "stg_fixture"},
                           env={"JEV_MODE": "demo"}, vars={"judge": LLM}))["insert"]
    assert f"jev_demo.bench.llm_demo('{LLM}', concat(" in ins and "ai_query(" not in ins


@pytest.mark.slow
def test_expect_compiles_with_judge_specific_flag_rule():
    jev = dbt("compile", "--select", "fixture_body_is_odd")
    assert jev.returncode == 0, jev.stdout
    llm = dbt("compile", "--select", "fixture_body_is_odd", "--vars", f"{{judge: {LLM}}}")
    assert llm.returncode == 0, llm.stdout
    assert "judged.p >= 0.8" in jev.stdout and "judged.decision = true" in llm.stdout
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_jev_judge_sql.py tests/test_jev_question.py -q`
Expected: PASS (9).

- [ ] **Step 7: Amend the spec** — under §4 add `*Amended (Task 6):* Jev flags p >= threshold (demo 05's rule, kept for continuity), not p > threshold.`

- [ ] **Step 8: Commit**

```bash
git add bench/macros bench/models tests/test_jev_judge_sql.py docs/superpowers/specs
git commit -m "feat(dbt): LLM judging path through ai_query, judge-aware test and run summary

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Ground truth — keys, families, swaps, samples, Jaccard, wanderbricks rule

**Files:**
- Create: `src/jevdbx/keys.py`, `tests/test_keys.py`

**Interfaces:**
- Produces:
  - `intent_family(intent: str) -> str` (first `_`-token; `top_up_*` → `top_up`, `card_*` → `card`, …; rule: first token, except `top` → first two tokens)
  - `families(intents: Iterable[str]) -> dict[str, list[str]]` (sorted)
  - `@dataclass Swap(query_id: str, in_sample: bool, original_intent: str, labelled_intent: str, swap_type: str)` (`swap_type` ∈ `random`, `near_miss`)
  - `choose_sample(test_ids: list[str], n: int, seed: int) -> list[str]`
  - `plan_swaps(rows: list[tuple[str, str]], sample: set[str], seed: int, n_random: int, n_near: int, full_rate: float) -> list[Swap]` (`rows` = (query_id, intent))
  - `tokens(text: str) -> set[str]`, `jaccard(a: str, b: str) -> float`, `fit_jaccard_threshold(pairs: list[tuple[str, str, int]]) -> float`
  - `comment_hash(text: str) -> str` (sha256 of the UTF-8 text), `state_id(comment: str, rating: float) -> str` (sha256 of `comment + "|" + f"{rating:.1f}"`)
  - `contradiction(polarity: str, rating: float) -> bool` (negative & rating ≥ 4.0, or positive & rating ≤ 2.0)
  - `rating_band(ratings: Iterable[float]) -> str` (`low` if all ≤ 2.4, `high` if all ≥ 4.0, else `mid`)
  - `@dataclass Flip(comment_sha256: str, rating: float, band: str)`; `plan_flips(states: list[tuple[str, float]], seed: int, n_polar: int, n_mid: int) -> list[Flip]` (spec §2 amendment 2026-10-01: seeded planted ratings, opposite band for low/high comments, one low + one high for mid comments, never a natural state)

- [ ] **Step 1: Write the failing tests**

```python
from jevdbx import keys

INTENTS = ["card_arrival", "card_delivery_estimate", "card_linking", "top_up_failed",
           "top_up_limits", "exchange_rate", "age_limit"]


def test_families_group_by_leading_token():
    assert keys.intent_family("card_arrival") == "card"
    assert keys.intent_family("top_up_failed") == "top_up"
    fam = keys.families(INTENTS)
    assert fam["card"] == ["card_arrival", "card_delivery_estimate", "card_linking"]
    assert fam["exchange"] == ["exchange_rate"]


def test_sample_is_deterministic():
    ids = [f"test-{i:05d}" for i in range(100)]
    assert keys.choose_sample(ids, 10, seed=7) == keys.choose_sample(ids, 10, seed=7)
    assert len(set(keys.choose_sample(ids, 10, seed=7))) == 10


def test_plan_swaps_counts_types_and_targets():
    rows = [(f"q{i}", INTENTS[i % len(INTENTS)]) for i in range(400)]
    sample = {f"q{i}" for i in range(200)}
    # seed 7: expected out-of-sample count ~8.6 (sd ~2.9); seed 42 draws 5 by chance
    swaps = keys.plan_swaps(rows, sample, seed=7, n_random=10, n_near=10, full_rate=0.05)
    in_s = [s for s in swaps if s.in_sample]
    assert sum(s.swap_type == "random" for s in in_s) == 10
    assert sum(s.swap_type == "near_miss" for s in in_s) == 10
    for s in swaps:
        assert s.labelled_intent != s.original_intent
        same = keys.intent_family(s.labelled_intent) == keys.intent_family(s.original_intent)
        assert same == (s.swap_type == "near_miss")
    out = [s for s in swaps if not s.in_sample]
    assert 6 <= len(out) <= 14   # ~5% of 200, split between types
    assert swaps == keys.plan_swaps(rows, sample, 7, 10, 10, 0.05)


def test_near_miss_only_from_families_with_siblings():
    # q3 (outside the sample) gives card_arrival a sibling; exchange_rate has none
    rows = [("q1", "exchange_rate"), ("q2", "card_arrival"), ("q3", "card_linking")]
    swaps = keys.plan_swaps(rows, {"q1", "q2"}, seed=1, n_random=0, n_near=1, full_rate=0)
    assert [s.query_id for s in swaps] == ["q2"]


def test_jaccard_and_threshold():
    assert keys.jaccard("Sony TV 40in", "sony tv 40-in") == 1.0
    pairs = [("a b c", "a b c", 1), ("a b c", "a b d", 1), ("a b", "x y", 0), ("a b c d", "a x", 0)]
    t = keys.fit_jaccard_threshold(pairs)
    assert 0.2 < t <= 0.5


def test_wanderbricks_rule_and_ids():
    assert keys.contradiction("negative", 4.0) and keys.contradiction("positive", 2.0)
    assert not keys.contradiction("negative", 3.9) and not keys.contradiction("neutral", 1.0)
    assert keys.state_id("Nice", 4.0) == keys.state_id("Nice", 4.04)
    assert len(keys.comment_hash("Nice")) == 64


def test_rating_band():
    assert keys.rating_band([1.0, 2.4]) == "low"
    assert keys.rating_band([4.0, 5.0]) == "high"
    assert keys.rating_band([2.5, 3.9]) == "mid" and keys.rating_band([2.0, 4.5]) == "mid"


def test_plan_flips_are_seeded_opposite_band_and_never_natural():
    states = [("h_low", 1.0), ("h_low", 2.4), ("h_high", 4.0), ("h_high", 5.0),
              ("h_mid", 3.0), ("h_mid", 3.5)]
    flips = keys.plan_flips(states, seed=42, n_polar=3, n_mid=2)
    assert flips == keys.plan_flips(states, seed=42, n_polar=3, n_mid=2)
    by: dict[str, list] = {}
    for f in flips:
        by.setdefault(f.comment_sha256, []).append(f)
    assert len(by["h_low"]) == 3 and all(f.band == "low" and f.rating >= 4.0 for f in by["h_low"])
    assert len(by["h_high"]) == 3 and all(f.rating <= 2.0 for f in by["h_high"])
    mid = sorted(f.rating for f in by["h_mid"])
    assert len(mid) == 2 and mid[0] <= 2.0 and mid[1] >= 4.0
    assert not any((f.comment_sha256, f.rating) in set(states) for f in flips)
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_keys.py -q` → FAIL.

- [ ] **Step 3: Implement `src/jevdbx/keys.py`**

```python
"""Ground-truth construction for demo 06. Pure functions, stdlib only; seeds make every key
reproducible. Never edit a committed key to make a judge win."""

import hashlib
import random
import re
from collections.abc import Iterable
from dataclasses import dataclass


def intent_family(intent: str) -> str:
    parts = intent.split("_")
    return "_".join(parts[:2]) if parts[0] == "top" and len(parts) > 1 else parts[0]


def families(intents: Iterable[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for i in sorted(set(intents)):
        out.setdefault(intent_family(i), []).append(i)
    return out


@dataclass(frozen=True)
class Swap:
    query_id: str
    in_sample: bool
    original_intent: str
    labelled_intent: str
    swap_type: str  # random | near_miss


def choose_sample(test_ids: list[str], n: int, seed: int) -> list[str]:
    return sorted(random.Random(seed).sample(sorted(test_ids), n))


def _swap(rng, qid, intent, kind, fam, all_intents, in_sample) -> Swap | None:
    if kind == "near_miss":
        options = [i for i in fam[intent_family(intent)] if i != intent]
    else:
        options = [i for i in all_intents if intent_family(i) != intent_family(intent)]
    if not options:
        return None
    return Swap(qid, in_sample, intent, rng.choice(options), kind)


def plan_swaps(rows: list[tuple[str, str]], sample: set[str], seed: int, n_random: int,
               n_near: int, full_rate: float) -> list[Swap]:
    rng = random.Random(seed)
    all_intents = sorted({i for _, i in rows})
    fam = families(all_intents)
    has_sibling = {i for members in fam.values() if len(members) > 1 for i in members}
    rows = sorted(rows)
    swaps: list[Swap] = []
    in_s = [r for r in rows if r[0] in sample]
    rng.shuffle(in_s)
    near_pool = [r for r in in_s if r[1] in has_sibling]
    near = near_pool[:n_near]
    taken = {q for q, _ in near}
    rand = [r for r in in_s if r[0] not in taken][:n_random]
    for qid, intent in near:
        swaps.append(_swap(rng, qid, intent, "near_miss", fam, all_intents, True))
    for qid, intent in rand:
        swaps.append(_swap(rng, qid, intent, "random", fam, all_intents, True))
    for qid, intent in [r for r in rows if r[0] not in sample]:
        u = rng.random()
        if u < full_rate / 2 and intent in has_sibling:
            swaps.append(_swap(rng, qid, intent, "near_miss", fam, all_intents, False))
        elif full_rate / 2 <= u < full_rate:
            swaps.append(_swap(rng, qid, intent, "random", fam, all_intents, False))
    return sorted((s for s in swaps if s), key=lambda s: s.query_id)


_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower().replace("-", "")))


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def fit_jaccard_threshold(pairs: list[tuple[str, str, int]]) -> float:
    """The threshold in (0, 1] that maximises F1 of `jaccard >= t` on labelled pairs."""
    scored = [(jaccard(a, b), y) for a, b, y in pairs]
    best_t, best_f1 = 1.0, -1.0
    for t in sorted({s for s, _ in scored if s > 0}):
        tp = sum(1 for s, y in scored if s >= t and y)
        fp = sum(1 for s, y in scored if s >= t and not y)
        fn = sum(1 for s, y in scored if s < t and y)
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        if f1 > best_f1:
            best_t, best_f1 = t, f1
    return round(best_t, 4)


def comment_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def state_id(comment: str, rating: float) -> str:
    return hashlib.sha256(f"{comment}|{rating:.1f}".encode()).hexdigest()


def contradiction(polarity: str, rating: float) -> bool:
    r = round(rating, 1)
    return (polarity == "negative" and r >= 4.0) or (polarity == "positive" and r <= 2.0)


RATING_GRID = [round(1.0 + 0.1 * i, 1) for i in range(41)]  # 1.0 .. 5.0


def rating_band(ratings: Iterable[float]) -> str:
    """A comment's natural rating band: low (all <= 2.4), high (all >= 4.0), else mid."""
    rs = [round(r, 1) for r in ratings]
    if max(rs) <= 2.4:
        return "low"
    if min(rs) >= 4.0:
        return "high"
    return "mid"


@dataclass(frozen=True)
class Flip:
    comment_sha256: str
    rating: float
    band: str  # the comment's natural band


def plan_flips(states: list[tuple[str, float]], seed: int, n_polar: int,
               n_mid: int) -> list[Flip]:
    """Seeded planted ratings (states = natural (comment_sha256, rating) pairs). A low-band
    comment gets n_polar ratings from 4.0-5.0, a high-band one n_polar from 1.0-2.0; a mid-band
    comment gets n_mid alternating from 1.0-2.0 and 4.0-5.0. Never a natural state. Whether a
    planted state is a contradiction is decided later by the polarity labels and the rule."""
    rng = random.Random(seed)
    by_comment: dict[str, set[float]] = {}
    for h, r in states:
        by_comment.setdefault(h, set()).add(round(r, 1))
    low = [r for r in RATING_GRID if r <= 2.0]
    high = [r for r in RATING_GRID if r >= 4.0]
    out: list[Flip] = []
    for h in sorted(by_comment):
        natural = by_comment[h]
        band = rating_band(natural)
        if band == "mid":
            picks: list[float] = []
            for i in range(n_mid):
                pool = [r for r in (low if i % 2 == 0 else high)
                        if r not in natural and r not in picks]
                picks.append(rng.choice(pool))
        else:
            picks = rng.sample([r for r in (high if band == "low" else low) if r not in natural],
                               n_polar)
        out += [Flip(h, r, band) for r in sorted(picks)]
    return out
```

- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_keys.py -q` → PASS (8). If `test_plan_swaps_counts_types_and_targets`' out-of-sample bound fails by randomness, widen nothing: change the seed in the test only if the count is outside [6, 14] for a reason you can name; otherwise fix the code.

- [ ] **Step 5: Commit**

```bash
git add src/jevdbx/keys.py tests/test_keys.py
git commit -m "feat(keys): intent families, seeded swaps, Jaccard, wanderbricks rule and planted ratings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Data fetch and key files (download/upload confirm-first)

**Files:**
- Create: `scripts/fetch_data.py`, `scripts/make_keys.py`, `tests/test_fetch_data.py`, `tests/test_make_keys.py`, `tests/fixtures/banking_test.csv`, `tests/fixtures/abt_tableA.csv`, `tests/fixtures/abt_tableB.csv`, `tests/fixtures/abt_test.csv`

**Interfaces:**
- Consumes: `eval/sources.toml` (Task 2), `jevdbx.keys` (Task 7), `jevdbx.databricks.Sql`.
- Produces (local, gitignored `data/`): `data/banking77.parquet` (`query_id, split, query, intent`), `data/abt_buy_pairs.parquet` (`pair_id, split, left_record, right_record`); volume files `/Volumes/jev_demo/bench/raw/banking77.parquet`, `/Volumes/jev_demo/bench/raw/abt_buy_pairs.parquet`. Committed: `eval/banking77_swaps.csv`, `eval/banking77_sample.csv`, `eval/intent_families.csv`, `eval/abt_buy_pairs.csv` (`pair_id, split, label`), `eval/abt_buy_jaccard.txt` (threshold), `eval/wanderbricks_polarity.csv` (`comment_sha256, polarity`), `eval/wanderbricks_flips.csv` (`comment_sha256, rating, band`); dbt seeds `bench/seeds/banking77_relabel.csv` (`query_id, labelled_intent`), `bench/seeds/banking77_sample.csv` (`query_id`), `bench/seeds/baseline_params.csv` (`name, value`), `bench/seeds/wanderbricks_flips.csv` (`comment_sha256, rating`).
- Functions: `fetch_data.banking_rows(csv_text: str, split: str) -> list[dict]`, `fetch_data.record_text(row: dict) -> str`, `fetch_data.abt_pairs(table_a: str, table_b: str, pairs_csv: str, split: str) -> list[dict]`; `make_keys.write_wanderbricks_flips(states, out_eval, out_seeds, seed)` (states = natural (comment, rating) rows; writes hashes, never text); `make_keys.main(argv)`.

- [ ] **Step 1: Write fixtures**

`tests/fixtures/banking_test.csv`:

```csv
text,category
I am still waiting on my card?,card_arrival
How do I top up by card?,top_up_by_card
What's the exchange rate today?,exchange_rate
```

`tests/fixtures/abt_tableA.csv`:

```csv
id,name,description,price
1,"Sony Bravia 40in LCD TV","Sony Bravia KDL-40 40-inch LCD HDTV",899.99
2,"Canon PowerShot SD1100","Canon 8MP digital camera, pink",
```

`tests/fixtures/abt_tableB.csv`:

```csv
id,name,description,price
10,"Sony KDL-40 Bravia","40"" LCD television",870.00
11,"Nikon Coolpix S210","8MP camera",120.00
```

`tests/fixtures/abt_test.csv`:

```csv
ltable_id,rtable_id,label
1,10,1
2,11,0
```

- [ ] **Step 2: Write the failing tests**

`tests/test_fetch_data.py`:

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIX = ROOT / "tests" / "fixtures"
spec = importlib.util.spec_from_file_location("fetch_data", ROOT / "scripts" / "fetch_data.py")
fd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fd)


def test_banking_rows_get_stable_ids():
    rows = fd.banking_rows((FIX / "banking_test.csv").read_text(), "test")
    assert [r["query_id"] for r in rows] == ["test-00000", "test-00001", "test-00002"]
    assert rows[0] == {"query_id": "test-00000", "split": "test",
                       "query": "I am still waiting on my card?", "intent": "card_arrival"}


def test_abt_pairs_render_both_records_without_labels():
    pairs = fd.abt_pairs((FIX / "abt_tableA.csv").read_text(), (FIX / "abt_tableB.csv").read_text(),
                         (FIX / "abt_test.csv").read_text(), "test")
    assert pairs[0]["pair_id"] == "test-1-10"
    assert pairs[0]["left_record"] == "Sony Bravia 40in LCD TV | Sony Bravia KDL-40 40-inch LCD HDTV | 899.99"
    assert pairs[1]["left_record"].endswith("| Canon 8MP digital camera, pink")   # no empty price
    assert "label" not in pairs[0]


def test_download_and_upload_need_explicit_flags():
    assert fd.parse_args([]).download is False and fd.parse_args([]).upload is False
```

`tests/test_make_keys.py`:

```python
import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("make_keys", ROOT / "scripts" / "make_keys.py")
mk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mk)


def test_relabel_seed_contains_only_swapped_rows(tmp_path):
    rows = [{"query_id": f"test-{i:05d}", "split": "test", "query": "q",
             "intent": ["card_arrival", "card_linking", "exchange_rate"][i % 3]} for i in range(60)]
    mk.write_banking_keys(rows, out_eval=tmp_path / "eval", out_seeds=tmp_path / "seeds",
                          sample_n=30, n_random=3, n_near=3, full_rate=0.1, seed=42)
    relabel = list(csv.DictReader((tmp_path / "seeds" / "banking77_relabel.csv").open()))
    swaps = list(csv.DictReader((tmp_path / "eval" / "banking77_swaps.csv").open()))
    assert len(relabel) == len(swaps) > 0
    assert set(relabel[0]) == {"query_id", "labelled_intent"}   # no ground truth in the seed
    sample = list(csv.DictReader((tmp_path / "seeds" / "banking77_sample.csv").open()))
    assert len(sample) == 30


def test_flips_are_written_as_hashes_never_text(tmp_path):
    states = [("Awful stay", "1.0"), ("Awful stay", "2.0"), ("Perfect", "4.5"), ("Okay", "3.0")]
    mk.write_wanderbricks_flips(states, out_eval=tmp_path / "eval", out_seeds=tmp_path / "seeds")
    seed_file = tmp_path / "seeds" / "wanderbricks_flips.csv"
    rows = list(csv.DictReader(seed_file.open()))
    assert set(rows[0]) == {"comment_sha256", "rating"} and len(rows) == 3 + 3 + 2
    text = seed_file.read_text() + (tmp_path / "eval" / "wanderbricks_flips.csv").read_text()
    assert "Awful" not in text and "Perfect" not in text and "Okay" not in text
```

- [ ] **Step 3: Run to verify failure** — `uv run pytest tests/test_fetch_data.py tests/test_make_keys.py -q` → FAIL.

- [ ] **Step 4: Implement `scripts/fetch_data.py`**

```python
"""Download the two public datasets (confirm-first), write parquet to data/, upload to the
volume (confirm-first). Labels never go into the parquet files.

    uv run python scripts/fetch_data.py --download      # Banking77 + entity-matching files
    uv run python scripts/fetch_data.py --upload        # data/*.parquet -> /Volumes/.../raw/
"""

import argparse
import csv
import io
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VOLUME = "/Volumes/jev_demo/bench/raw"


def banking_rows(csv_text: str, split: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    return [{"query_id": f"{split}-{i:05d}", "split": split, "query": r["text"],
             "intent": r["category"]} for i, r in enumerate(reader)]


def record_text(row: dict) -> str:
    parts = [row.get("name", ""), row.get("description", ""), row.get("price", "")]
    return " | ".join(p.strip() for p in parts if p and p.strip())


def abt_pairs(table_a: str, table_b: str, pairs_csv: str, split: str) -> list[dict]:
    a = {r["id"]: r for r in csv.DictReader(io.StringIO(table_a))}
    b = {r["id"]: r for r in csv.DictReader(io.StringIO(table_b))}
    out = []
    for p in csv.DictReader(io.StringIO(pairs_csv)):
        out.append({"pair_id": f"{split}-{p['ltable_id']}-{p['rtable_id']}", "split": split,
                    "left_record": record_text(a[p["ltable_id"]]),
                    "right_record": record_text(b[p["rtable_id"]])})
    return out


def abt_labels(pairs_csv: str, split: str) -> list[dict]:
    return [{"pair_id": f"{split}-{p['ltable_id']}-{p['rtable_id']}", "split": split,
             "label": int(p["label"])} for p in csv.DictReader(io.StringIO(pairs_csv))]


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def download(sources: dict) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    DATA.mkdir(exist_ok=True)
    bk = sources["banking77"]
    rows = banking_rows(_get(bk["train_url"]), "train") + banking_rows(_get(bk["test_url"]), "test")
    pq.write_table(pa.Table.from_pylist(rows), DATA / "banking77.parquet")
    ab = sources["abt_buy"]
    ta, tb = _get(ab["table_a_url"]), _get(ab["table_b_url"])
    pairs, labels = [], []
    for split in ("train", "valid", "test"):
        text = _get(ab[f"{split}_url"])
        pairs += abt_pairs(ta, tb, text, split)
        labels += abt_labels(text, split)
    pq.write_table(pa.Table.from_pylist(pairs), DATA / "abt_buy_pairs.parquet")
    with (DATA / "abt_buy_labels.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pair_id", "split", "label"])
        w.writeheader()
        w.writerows(labels)
    print(f"banking77: {len(rows)} rows · abt_buy: {len(pairs)} pairs "
          f"({sum(r['label'] for r in labels)} matches)")


def upload() -> None:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    for name in ("banking77.parquet", "abt_buy_pairs.parquet"):
        with (DATA / name).open("rb") as f:
            w.files.upload(f"{VOLUME}/{name}", f, overwrite=True)
        print(f"uploaded {name} -> {VOLUME}/{name}")


def parse_args(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--upload", action="store_true")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    a = parse_args(argv)
    if a.download:
        download(tomllib.loads((ROOT / "eval" / "sources.toml").read_text()))
    if a.upload:
        upload()
    if not (a.download or a.upload):
        print("nothing to do: pass --download and/or --upload (each needs the user's OK)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Implement `scripts/make_keys.py`**

```python
"""Write the committed ground truth (eval/) and the dbt seeds (bench/seeds/) from data/.

    uv run python scripts/make_keys.py banking          # swaps, sample, families, seeds
    uv run python scripts/make_keys.py abt              # pair labels, Jaccard threshold
    uv run python scripts/make_keys.py wanderbricks-template   # data/wanderbricks_label_me.csv
    uv run python scripts/make_keys.py wanderbricks-commit     # eval/wanderbricks_polarity.csv
    uv run python scripts/make_keys.py wanderbricks-flips      # planted ratings (eval/ + seed)
"""

import csv
import sys
from pathlib import Path

from jevdbx import keys

ROOT = Path(__file__).resolve().parents[1]
DATA, EVAL, SEEDS = ROOT / "data", ROOT / "eval", ROOT / "bench" / "seeds"
SEED, SAMPLE_N, N_RANDOM, N_NEAR, FULL_RATE = 42, 2000, 75, 75, 0.075
N_FLIPS_POLAR, N_FLIPS_MID = 3, 2


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_banking_keys(rows, out_eval=EVAL, out_seeds=SEEDS, sample_n=SAMPLE_N,
                       n_random=N_RANDOM, n_near=N_NEAR, full_rate=FULL_RATE, seed=SEED) -> None:
    test_ids = [r["query_id"] for r in rows if r["split"] == "test"]
    sample = keys.choose_sample(test_ids, sample_n, seed)
    swaps = keys.plan_swaps([(r["query_id"], r["intent"]) for r in rows], set(sample), seed,
                            n_random, n_near, full_rate)
    _write(out_eval / "banking77_swaps.csv",
           ["query_id", "in_sample", "original_intent", "labelled_intent", "swap_type"],
           [s.__dict__ for s in swaps])
    _write(out_eval / "banking77_sample.csv", ["query_id"], [{"query_id": q} for q in sample])
    fam = keys.families(r["intent"] for r in rows)
    _write(out_eval / "intent_families.csv", ["intent", "family"],
           [{"intent": i, "family": f} for f, members in fam.items() for i in members])
    _write(out_seeds / "banking77_relabel.csv", ["query_id", "labelled_intent"],
           [{"query_id": s.query_id, "labelled_intent": s.labelled_intent} for s in swaps])
    _write(out_seeds / "banking77_sample.csv", ["query_id"], [{"query_id": q} for q in sample])


def _banking_rows() -> list[dict]:
    import pyarrow.parquet as pq
    return pq.read_table(DATA / "banking77.parquet").to_pylist()


def write_abt_keys() -> None:
    import pyarrow.parquet as pq
    labels = list(csv.DictReader((DATA / "abt_buy_labels.csv").open()))
    _write(EVAL / "abt_buy_pairs.csv", ["pair_id", "split", "label"], labels)
    pairs = {p["pair_id"]: p for p in pq.read_table(DATA / "abt_buy_pairs.parquet").to_pylist()}
    train = [(pairs[r["pair_id"]]["left_record"], pairs[r["pair_id"]]["right_record"],
              int(r["label"])) for r in labels if r["split"] == "train"]
    t = keys.fit_jaccard_threshold(train)
    (EVAL / "abt_buy_jaccard.txt").write_text(f"{t}\n")
    _write(SEEDS / "baseline_params.csv", ["name", "value"],
           [{"name": "abt_jaccard_threshold", "value": t}])
    print(f"abt: {len(labels)} labelled pairs · Jaccard threshold {t} (fit on train)")


def wanderbricks_template() -> None:
    from jevdbx.databricks import Sql
    r = Sql().run("select distinct comment from samples.wanderbricks.reviews "
                  "where comment is not null order by comment")
    _write(DATA / "wanderbricks_label_me.csv", ["comment", "polarity"],
           [{"comment": c, "polarity": ""} for (c,) in r.rows])
    print(f"wrote data/wanderbricks_label_me.csv ({len(r.rows)} comments): fill polarity with "
          "positive | negative | neutral, then run wanderbricks-commit")


def wanderbricks_commit() -> None:
    rows = list(csv.DictReader((DATA / "wanderbricks_label_me.csv").open()))
    bad = [r["comment"] for r in rows if r["polarity"] not in ("positive", "negative", "neutral")]
    if bad:
        sys.exit(f"unlabelled or invalid polarity for {len(bad)} comments")
    _write(EVAL / "wanderbricks_polarity.csv", ["comment_sha256", "polarity"],
           [{"comment_sha256": keys.comment_hash(r["comment"]), "polarity": r["polarity"]}
            for r in rows])


def write_wanderbricks_flips(states, out_eval=EVAL, out_seeds=SEEDS, seed=SEED) -> None:
    """states: natural (comment, rating) rows. Only comment hashes are written."""
    flips = keys.plan_flips([(keys.comment_hash(c), float(r)) for c, r in states], seed,
                            N_FLIPS_POLAR, N_FLIPS_MID)
    _write(out_eval / "wanderbricks_flips.csv", ["comment_sha256", "rating", "band"],
           [f.__dict__ for f in flips])
    _write(out_seeds / "wanderbricks_flips.csv", ["comment_sha256", "rating"],
           [{"comment_sha256": f.comment_sha256, "rating": f.rating} for f in flips])
    print(f"wanderbricks: {len(flips)} planted ratings over {len({c for c, _ in states})} comments")


def wanderbricks_flips() -> None:
    from jevdbx.databricks import Sql
    r = Sql().run("select distinct comment, round(rating, 1) from samples.wanderbricks.reviews "
                  "where comment is not null and rating is not null")
    write_wanderbricks_flips(r.rows)


def main(argv=None) -> None:
    cmd = (argv or sys.argv[1:] or [""])[0]
    {"banking": lambda: write_banking_keys(_banking_rows()), "abt": write_abt_keys,
     "wanderbricks-template": wanderbricks_template,
     "wanderbricks-commit": wanderbricks_commit,
     "wanderbricks-flips": wanderbricks_flips}.get(
        cmd, lambda: sys.exit(f"unknown command {cmd!r}"))()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the tests** — `uv run pytest tests/test_fetch_data.py tests/test_make_keys.py -q && uv run ruff check` → PASS (5).

- [ ] **Step 7: Commit**

```bash
git add scripts/fetch_data.py scripts/make_keys.py tests/test_fetch_data.py tests/test_make_keys.py tests/fixtures
git commit -m "feat(data): fetch and key writers; labels kept out of the model inputs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Models, the three semantic tests and the baselines

**Files:**
- Create: `bench/models/staging/stg_banking_queries.sql`, `stg_product_pairs.sql`, `stg_wanderbricks_reviews.sql`, `bench/tests/baseline/baseline_banking_keyword.sql`, `bench/tests/baseline/baseline_pairs_jaccard.sql`, `tests/test_models.py`
- Create (header-only until Task 15 writes the real keys, so the project parses offline): `bench/seeds/banking77_relabel.csv` (`query_id,labelled_intent`), `bench/seeds/banking77_sample.csv` (`query_id`), `bench/seeds/baseline_params.csv` (`name,value`), `bench/seeds/wanderbricks_flips.csv` (`comment_sha256,rating`)
- Modify: `bench/dbt_project.yml` (seed column types, below), `bench/models/staging/schema.yml` (replace the fixture), delete `bench/models/staging/stg_fixture.sql` and update `tests/test_jev_judge_sql.py` to render `stg_wanderbricks_reviews` instead of `stg_fixture` and to compile `wanderbricks_comment_contradicts_rating` instead of `fixture_body_is_odd` (threshold 0.8 unchanged)

**Interfaces:**
- Consumes: seeds from Task 8; volume files; var `bench_scope`.
- Produces: models `stg_banking_queries(query_id, split, query, intent)`, `stg_product_pairs(pair_id, split, left_record, right_record)`, `stg_wanderbricks_reviews(comment, rating, review_rows)` (natural states with `review_rows > 0`, planted states with `review_rows = 0`); tests `banking_query_not_about_intent` (column `query`, context `[intent]`), `pairs_describe_same_product` (column `left_record`, context `[right_record]`), `wanderbricks_comment_contradicts_rating` (column `comment`, context `[rating]`); baselines `baseline_banking_keyword`, `baseline_pairs_jaccard` (tag `baseline`, `store_failures: true`).

- [ ] **Step 1: Write the models**

`stg_banking_queries.sql`:

```sql
{#- Banking77 with planted intent swaps applied; scope: pilot (50 of the sample) | sample | full -#}
with raw as (
  select query_id, split, query, intent
  from read_files('/Volumes/jev_demo/bench/raw/banking77.parquet', format => 'parquet')
),
labelled as (
  select raw.query_id, raw.split, raw.query, coalesce(r.labelled_intent, raw.intent) as intent
  from raw left join {{ ref('banking77_relabel') }} r on r.query_id = raw.query_id
)
select * from labelled
{% if var('bench_scope') == 'sample' %}
where query_id in (select query_id from {{ ref('banking77_sample') }})
{% elif var('bench_scope') == 'pilot' %}
where query_id in (select query_id from {{ ref('banking77_sample') }} order by query_id limit 50)
{% endif %}
```

`stg_product_pairs.sql`:

```sql
{#- Candidate pairs, two product records per row; no labels. sample = the test split -#}
select pair_id, split, left_record, right_record
from read_files('/Volumes/jev_demo/bench/raw/abt_buy_pairs.parquet', format => 'parquet')
{% if var('bench_scope') == 'sample' %}
where split = 'test'
{% elif var('bench_scope') == 'pilot' %}
where pair_id in (select pair_id from read_files('/Volumes/jev_demo/bench/raw/abt_buy_pairs.parquet',
                  format => 'parquet') where split = 'test' order by pair_id limit 50)
{% endif %}
```

`stg_wanderbricks_reviews.sql`:

```sql
{#- Databricks' own sample data: one row per distinct (comment, rating) state, plus the seeded
    planted ratings (review_rows = 0) keyed by comment hash. The natural data holds no
    contradictions (query 2026-10-01): its states are the control. -#}
with natural as (
  select comment, cast(round(rating, 1) as double) as rating, count(*) as review_rows
  from samples.wanderbricks.reviews
  where comment is not null and rating is not null
  group by comment, round(rating, 1)
),
planted as (
  select c.comment, cast(f.rating as double) as rating, cast(0 as bigint) as review_rows
  from (select distinct comment from natural) c
  join {{ ref('wanderbricks_flips') }} f on f.comment_sha256 = sha2(c.comment, 256)
)
select * from (select * from natural union all select * from planted)
{% if var('bench_scope') == 'pilot' %}
order by comment, rating limit 50
{% endif %}
```

Append to `bench/dbt_project.yml` (fixed types, so the header-only seeds load and the keys never get inferred types):

```yaml
seeds:
  bench:
    banking77_relabel: {+column_types: {query_id: string, labelled_intent: string}}
    banking77_sample: {+column_types: {query_id: string}}
    baseline_params: {+column_types: {name: string, value: string}}
    wanderbricks_flips: {+column_types: {comment_sha256: string, rating: double}}
```

- [ ] **Step 2: Write `bench/models/staging/schema.yml`**

```yaml
version: 2
models:
  - name: stg_banking_queries
    columns:
      - name: query_id
        data_tests: [unique, not_null]
      - name: query
        data_tests:
          - jev_expect:
              name: banking_query_not_about_intent
              arguments:
                fails_if: "The customer's `query` is not about its labelled `intent` (a banking support category such as card_arrival or exchange_rate)."
                context: [intent]
                threshold: 0.8
                criteria:
                  "true": "The query plainly asks about a different topic than the intent names"
                  "false": "The query fits the intent, or is too vague to tell"
              config: {severity: warn, store_failures: true, tags: [semantic, banking]}
  - name: stg_product_pairs
    columns:
      - name: pair_id
        data_tests: [unique, not_null]
      - name: left_record
        data_tests:
          - jev_expect:
              name: pairs_describe_same_product
              arguments:
                fails_if: "`left_record` and `right_record` describe the same product (same brand and model; ignore price and wording)."
                context: [right_record]
                threshold: 0.8
                criteria:
                  "true": "Same brand and model number or the same specific item, written differently"
                  "false": "Different products, different models, or accessories for the product"
              config: {severity: warn, store_failures: true, tags: [semantic, pairs]}
  - name: stg_wanderbricks_reviews
    columns:
      - name: comment
        data_tests:
          - jev_expect:
              name: wanderbricks_comment_contradicts_rating
              arguments:
                fails_if: "The review `comment` clearly contradicts its `rating` (1.0 = very bad, 5.0 = excellent)."
                context: [rating]
                threshold: 0.8
                criteria:
                  "true": "A clearly negative comment with a rating of 4.0 or more, or a clearly positive comment with 2.0 or less"
                  "false": "The comment roughly matches the rating, or the comment is neutral or mixed"
              config: {severity: warn, store_failures: true, tags: [semantic, wanderbricks]}
```

- [ ] **Step 3: Write the baselines**

`bench/tests/baseline/baseline_banking_keyword.sql`:

```sql
{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
{#- flags a query that mentions none of its intent's words (longer than 2 letters) -#}
select query_id, query, intent
from {{ ref('stg_banking_queries') }}
where size(filter(split(intent, '_'), w -> length(w) > 2 and lower(query) like concat('%', w, '%'))) = 0
```

`bench/tests/baseline/baseline_pairs_jaccard.sql`:

```sql
{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
{#- flags a pair whose token-Jaccard similarity reaches the threshold fit on the train split -#}
with t as (
  select cast(value as double) as threshold from {{ ref('baseline_params') }}
  where name = 'abt_jaccard_threshold'
),
tok as (
  select pair_id,
         array_distinct(filter(split(regexp_replace(lower(replace(left_record, '-', '')), '[^a-z0-9]+', ' '), ' '), x -> x != '')) as a,
         array_distinct(filter(split(regexp_replace(lower(replace(right_record, '-', '')), '[^a-z0-9]+', ' '), ' '), x -> x != '')) as b
  from {{ ref('stg_product_pairs') }}
)
select pair_id, size(array_intersect(a, b)) / size(array_union(a, b)) as jaccard
from tok, t
where size(array_union(a, b)) > 0
  and size(array_intersect(a, b)) / size(array_union(a, b)) >= t.threshold
```

(The Python `keys.tokens` drops `-` then keeps `[a-z0-9]+` runs; this SQL does the same: a test in `tests/test_models.py` pins both on one example.)

- [ ] **Step 4: Write `tests/test_models.py`**

```python
import pytest

from jevdbx import keys
from tests.dbt_helpers import dbt


@pytest.mark.slow
def test_project_parses_with_three_semantic_tests_and_two_baselines():
    out = dbt("ls", "--resource-type", "test", "--select", "tag:semantic tag:baseline")
    names = {line.split(".")[-1] for line in out.stdout.split() if line.startswith("bench.")}
    assert {"banking_query_not_about_intent", "pairs_describe_same_product",
            "wanderbricks_comment_contradicts_rating", "baseline_banking_keyword",
            "baseline_pairs_jaccard"} <= names


def test_python_tokens_match_the_sql_baseline_rule():
    # SQL: lower, drop '-', split on non [a-z0-9] runs, distinct
    assert keys.tokens("Sony KDL-40 Bravia, 40in") == {"sony", "kdl40", "bravia", "40in"}
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -q`
Expected: PASS (all offline tests; `test_jev_judge_sql` now renders `stg_wanderbricks_reviews`).

- [ ] **Step 6: Commit**

```bash
git add bench tests
git commit -m "feat(dbt): banking, pairs and wanderbricks models with their semantic tests and baselines

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Metrics

**Files:**
- Create: `src/jevdbx/metrics.py`, `tests/test_metrics.py`

**Interfaces:**
- Produces: `@dataclass Scores(tp, fp, fn, tn, precision, recall, f1)`; `score(flagged: set, positives: set, universe: set) -> Scores`; `wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]`; `brier(probs: list[float], labels: list[bool]) -> float`; `reliability(probs, labels, bins=10) -> list[tuple[float, float, float, int]]` (bin low, bin high, observed rate, count); `agreement(flags: dict[str, set], positives: set) -> dict[str, int]` with keys `all`, `none`, `only_<judge>` for positives.

- [ ] **Step 1: Write the failing tests**

```python
import math

from jevdbx import metrics


def test_score_counts_and_rates():
    s = metrics.score({1, 2, 3}, {2, 3, 4}, set(range(10)))
    assert (s.tp, s.fp, s.fn, s.tn) == (2, 1, 1, 6)
    assert math.isclose(s.precision, 2 / 3) and math.isclose(s.recall, 2 / 3)
    assert math.isclose(s.f1, 2 / 3)


def test_score_empty_flags_is_zero_not_nan():
    s = metrics.score(set(), {1}, {1, 2})
    assert s.precision == 0.0 and s.recall == 0.0 and s.f1 == 0.0


def test_wilson_matches_known_value():
    lo, hi = metrics.wilson(94, 100)
    assert round(lo, 3) == 0.875 and round(hi, 3) == 0.972
    assert metrics.wilson(0, 0) == (0.0, 1.0)


def test_brier_and_reliability():
    assert metrics.brier([1.0, 0.0], [True, False]) == 0.0
    bins = metrics.reliability([0.05, 0.95, 0.9], [False, True, True], bins=2)
    assert bins[0] == (0.0, 0.5, 0.0, 1) and bins[1] == (0.5, 1.0, 1.0, 2)


def test_agreement_on_positives():
    a = metrics.agreement({"jev": {1, 2}, "llm": {2, 3}}, positives={1, 2, 3, 4})
    assert a == {"all": 1, "none": 1, "only_jev": 1, "only_llm": 1}
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_metrics.py -q` → FAIL.

- [ ] **Step 3: Implement `src/jevdbx/metrics.py`**

```python
"""Scoring math for demo 06. Stdlib only."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Scores:
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float


def score(flagged: set, positives: set, universe: set) -> Scores:
    flagged, positives = flagged & universe, positives & universe
    tp = len(flagged & positives)
    fp = len(flagged - positives)
    fn = len(positives - flagged)
    tn = len(universe) - tp - fp - fn
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return Scores(tp, fp, fn, tn, p, r, f1)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def brier(probs: list[float], labels: list[bool]) -> float:
    return sum((p - float(y)) ** 2 for p, y in zip(probs, labels, strict=True)) / len(probs)


def reliability(probs, labels, bins: int = 10):
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        rate = sum(labels[i] for i in idx) / len(idx) if idx else 0.0
        out.append((lo, hi, rate, len(idx)))
    return out


def agreement(flags: dict[str, set], positives: set) -> dict[str, int]:
    out = {"all": 0, "none": 0} | {f"only_{j}": 0 for j in flags}
    for x in positives:
        who = [j for j, f in flags.items() if x in f]
        if len(who) == len(flags):
            out["all"] += 1
        elif not who:
            out["none"] += 1
        elif len(who) == 1:
            out[f"only_{who[0]}"] += 1
    return out
```

- [ ] **Step 4: Run** — `uv run pytest tests/test_metrics.py -q` → PASS (5).

- [ ] **Step 5: Commit**

```bash
git add src/jevdbx/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): P/R/F1, Wilson, Brier, reliability, agreement

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Budget guard and eval-log helpers

**Files:**
- Create: `src/jevdbx/budget.py`, `src/jevdbx/evallog.py`, `tests/test_budget.py`, `tests/test_evallog.py`

**Interfaces:**
- Produces:
  - `budget.PRICES: dict[str, tuple[float, float]]` ($ per 1M input, output tokens), `budget.CAP_USD = 15.0`, `budget.SINCE = "2026-10-01"`, `budget.DEFAULT_TOKENS_PER_ROW: dict[str, tuple[int, int]]` (by test name, assumption until the pilot), `budget.cost_usd(endpoint, input_tokens, output_tokens) -> float`, `budget.usage_sql(since: str, until: str | None = None) -> str` (this user's `system.serving.endpoint_usage` per `served_entity_id` in a window; columns `served_entity_id, requests, input_tokens, output_tokens`; spec S2: `served_entities` has no rows for these endpoints, so usage is attributed by time window, one judge per window), `budget.window_cost(endpoint, rows) -> tuple[float, int, int, int] | None` (cost, requests, in, out when exactly one served entity used the window, else None), `budget.project(endpoint, rows: int, per_row: tuple[int, int]) -> float`, `class BudgetExceeded(Exception)`, `budget.check(spent: float, projected: float, cap: float = CAP_USD) -> None`.
  - `evallog.llm_spend(md: str) -> float` (sum of `- llm cost $X` lines; a later entry with the same `- invocation <id>` — a `measured cost` entry — replaces that invocation's earlier cost), `evallog.tokens_per_row(md: str, endpoint: str, test: str) -> tuple[int, int] | None` (from the latest pilot entry line `- tokens/row <test> in A out B (measured)`), `evallog.append(path: Path, entry: str) -> None`, `evallog.has_preregistration(md: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

`tests/test_budget.py`:

```python
import pytest

from jevdbx import budget


def test_prices_per_endpoint():
    assert budget.cost_usd("databricks-gpt-oss-20b", 1_000_000, 1_000_000) == pytest.approx(0.37)
    assert budget.cost_usd("databricks-claude-opus-5", 1_000_000, 0) == pytest.approx(5.0)


def test_projection_and_guard():
    p = budget.project("databricks-meta-llama-3-3-70b-instruct", 2000, (300, 25))
    assert p == pytest.approx(2000 * (300 * 0.50 + 25 * 1.50) / 1e6)
    budget.check(spent=10.0, projected=4.9)
    with pytest.raises(budget.BudgetExceeded):
        budget.check(spent=10.0, projected=5.1)


def test_usage_sql_reads_my_endpoint_usage_in_a_window():
    sql = budget.usage_sql("2026-10-01", "2026-10-02T10:00:00")
    assert "system.serving.endpoint_usage" in sql and "served_entities" not in sql
    assert "requester = current_user()" in sql and "group by served_entity_id" in sql
    assert ">= timestamp'2026-10-01'" in sql and "< timestamp'2026-10-02T10:00:00'" in sql


def test_window_cost_needs_exactly_one_served_entity():
    rows = [["e1", "3", "600", "90"]]
    assert budget.window_cost("databricks-gpt-oss-20b", rows) == (
        budget.cost_usd("databricks-gpt-oss-20b", 600, 90), 3, 600, 90)
    assert budget.window_cost("databricks-gpt-oss-20b", []) is None
    assert budget.window_cost("databricks-gpt-oss-20b", [*rows, ["e2", "1", "5", "5"]]) is None
```

`tests/test_evallog.py`:

```python
from jevdbx import evallog

MD = """# Eval results
## 2026-10-03T10:00:00Z · pilot · databricks-gpt-oss-20b
- tokens/row banking_query_not_about_intent in 310 out 140 (measured)
- llm cost $0.012 (measured)
## 2026-10-03T11:00:00Z · pass 1 · databricks-gpt-oss-20b
- llm cost $0.40 (estimated)
"""


def test_spend_and_tokens_per_row():
    assert evallog.llm_spend(MD) == 0.412
    assert evallog.tokens_per_row(MD, "databricks-gpt-oss-20b",
                                  "banking_query_not_about_intent") == (310, 140)
    assert evallog.tokens_per_row(MD, "databricks-gpt-oss-20b", "other") is None


def test_measured_entry_replaces_the_estimate_of_its_invocation():
    md = ("## a · pass 1 · x\n- invocation inv-1\n- llm cost $0.40 (estimated)\n"
          "## b · measured cost · pass 1 · x\n- invocation inv-1\n- llm cost $0.31 (measured)\n"
          "## c · pass 1 · y\n- invocation inv-2\n- llm cost $0.10 (estimated)\n")
    assert evallog.llm_spend(md) == 0.41


def test_append_and_preregistration(tmp_path):
    p = tmp_path / "e.md"
    p.write_text("# Eval results\n")
    evallog.append(p, "## x\n- y\n")
    assert p.read_text().endswith("\n## x\n- y\n")
    assert not evallog.has_preregistration(p.read_text())
    assert evallog.has_preregistration("## Pre-registration (frozen before pass 1)\n")
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_budget.py tests/test_evallog.py -q` → FAIL.

- [ ] **Step 3: Implement `src/jevdbx/budget.py`**

```python
"""The $15 LLM budget (Databricks pay-per-token, Azure Premium, $0.070/DBU; prices checked
2026-10-01, re-check before pass 1). Spend comes from system.serving.endpoint_usage when it is
readable, else from the eval log's cost lines; the guard uses the larger of the two."""

DBU_USD = 0.070
# $ per 1M tokens (input, output), Azure Premium at DBU_USD, from the Databricks pricing pages
# (DBU per 1M: gpt-oss-20b 1.000 / 4.286, llama-3.3-70b 7.143 / 21.429).
# opus-5 is an ESTIMATE (S2 replaced sonnet-5-5, which ai_query rejects): verify before the pilot.
PRICES: dict[str, tuple[float, float]] = {
    "databricks-gpt-oss-20b": (0.07, 0.30),
    "databricks-meta-llama-3-3-70b-instruct": (0.50, 1.50),
    # ESTIMATE until verified before the pilot gate (Task 15 Step 5); S2: no Sonnet works with ai_query
    "databricks-claude-opus-5": (5.00, 25.00),
}
CAP_USD = 15.0
SINCE = "2026-10-01"
# ESTIMATES (input, output tokens per row) until the pilot measures them
DEFAULT_TOKENS_PER_ROW: dict[str, tuple[int, int]] = {
    "banking_query_not_about_intent": (300, 250),
    "pairs_describe_same_product": (450, 250),
    "wanderbricks_comment_contradicts_rating": (270, 250),
}


class BudgetExceeded(Exception):
    pass


def cost_usd(endpoint: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES[endpoint]
    return round((input_tokens * pin + output_tokens * pout) / 1_000_000, 6)


def project(endpoint: str, rows: int, per_row: tuple[int, int]) -> float:
    return cost_usd(endpoint, rows * per_row[0], rows * per_row[1])


def check(spent: float, projected: float, cap: float = CAP_USD) -> None:
    if spent + projected > cap:
        raise BudgetExceeded(f"spent ${spent:.2f} + projected ${projected:.2f} > cap ${cap:.2f}")


def _lit(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def usage_sql(since: str, until: str | None = None) -> str:
    """This user's foundation-model usage per served entity in [since, until). S2 (spec §4):
    served_entities has no rows for the pay-per-token endpoints, so usage is attributed by time
    window (the scorer runs one judge at a time), not by endpoint name."""
    until_sql = f" and request_time < timestamp{_lit(until)}" if until else ""
    return ("select served_entity_id, count(*) as requests, "
            "coalesce(sum(input_token_count), 0) as input_tokens, "
            "coalesce(sum(output_token_count), 0) as output_tokens "
            "from system.serving.endpoint_usage "
            f"where requester = current_user() and request_time >= timestamp{_lit(since)}"
            f"{until_sql} group by served_entity_id")


def window_cost(endpoint: str, rows: list) -> tuple[float, int, int, int] | None:
    """Cost of one judge's window, or None unless exactly one served entity was used (usage not
    landed yet — it lags ~2 h — or another model ran in the same window)."""
    if len(rows) != 1:
        return None
    _, n, i, o = rows[0]
    return cost_usd(endpoint, int(i), int(o)), int(n), int(i), int(o)
```

(If Task 3 found different column names in `endpoint_usage`/`served_entities`, use those here and in the test.)

- [ ] **Step 4: Implement `src/jevdbx/evallog.py`**

```python
"""docs/eval-results.md helpers: spend and tokens-per-row from logged lines, appending entries."""

import re
from pathlib import Path

_COST = re.compile(r"^- llm cost \$([0-9.]+) \((?:measured|estimated)\)$", re.M)
PREREG = "## Pre-registration (frozen before pass 1)"


_INV = re.compile(r"^- invocation (\S+)$", re.M)


def llm_spend(md: str) -> float:
    """Logged LLM spend. A later entry for the same invocation (a `measured cost` entry written by
    `score.py --measure`) replaces that invocation's earlier (estimated) cost."""
    by_inv: dict[str, float] = {}
    loose = 0.0
    for block in re.split(r"\n(?=## )", md):
        costs = [float(x) for x in _COST.findall(block)]
        if not costs:
            continue
        inv = _INV.search(block)
        if inv:
            by_inv[inv[1]] = sum(costs)
        else:
            loose += sum(costs)
    return round(loose + sum(by_inv.values()), 6)


def tokens_per_row(md: str, endpoint: str, test: str) -> tuple[int, int] | None:
    found = None
    for block in re.split(r"\n(?=## )", md):
        head = block.splitlines()[0]
        if " · pilot · " in head and head.endswith(endpoint):
            m = re.search(rf"^- tokens/row {re.escape(test)} in (\d+) out (\d+) \(measured\)$",
                          block, re.M)
            if m:
                found = (int(m[1]), int(m[2]))
    return found


def append(path: Path, entry: str) -> None:
    text = path.read_text()
    path.write_text(text.rstrip("\n") + "\n\n" + entry.rstrip("\n") + "\n")


def has_preregistration(md: str) -> bool:
    return PREREG in md
```

- [ ] **Step 5: Run** — `uv run pytest tests/test_budget.py tests/test_evallog.py -q` → PASS (7).

- [ ] **Step 6: Commit**

```bash
git add src/jevdbx/budget.py src/jevdbx/evallog.py tests/test_budget.py tests/test_evallog.py
git commit -m "feat(budget): \$15 LLM guard from endpoint usage and the eval log

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Scorer — run, score, guard, log, pre-register

**Files:**
- Create: `scripts/score.py`, `tests/test_score.py`, `docs/eval-results.md`

**Interfaces:**
- Consumes: `jevdbx.metrics`, `jevdbx.budget`, `jevdbx.evallog`, `jevdbx.keys`, `jevdbx.databricks.Sql`, `scripts/dbtw.py` (subprocess), committed `eval/*.csv`.
- Produces: CLI `score.py [--run --judge J --scope S --pass N --mode live|demo] [--append] [--fresh] [--preregister] [--usage] [--measure [--append]]`; `unmeasured(md) -> list[tuple[str, str, str]]` (label, judge, invocation of logged LLM runs whose cost is still estimated and has no later measured-cost entry); functions `TESTS: dict[str, TestSpec]`, `@dataclass TestSpec(name, model, id_expr, state_cols, truth)`, `truth_ids(test: str, scope: str) -> tuple[set, set]` (universe, positives), `stored_flags(sql, spec, judge, is_llm) -> tuple[set, set, set]` (flagged ids, unjudged ids, invocation ids), `run_stats(sql, invocation, is_llm) -> dict` (requests, wall_s, jev_cost), `swap_recall(flagged, scope_ids) -> dict[str, tuple[int, int]]`, `natural_ids(sql, spec) -> set` (wanderbricks states with `review_rows > 0`), `false_alarms(flagged, natural, positives) -> tuple[int, int]` (the wanderbricks control: flags on natural states the key calls clean, out of those states), `entry_md(..., extra: list[str]) -> str`, `refuse_reasons(mode, judge, invocation_ids, errors) -> list[str]`.

- [ ] **Step 1: Write the failing tests** (pure parts only; the workspace parts are exercised in Task 14)

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("score", ROOT / "scripts" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def test_three_tests_with_id_and_state_columns():
    assert set(score.TESTS) == {"banking_query_not_about_intent", "pairs_describe_same_product",
                                "wanderbricks_comment_contradicts_rating"}
    assert score.TESTS["banking_query_not_about_intent"].state_cols == ["query", "intent"]
    assert score.TESTS["pairs_describe_same_product"].state_cols == ["left_record", "right_record"]


def test_state_expr_matches_the_macro():
    # the macro renders to_json(named_struct('query', `query`, 'intent', `intent`))
    assert score.state_expr(["query", "intent"]) == \
        "to_json(named_struct('query', `query`, 'intent', `intent`))"


def test_simulated_or_mixed_runs_are_refused_for_append():
    assert score.refuse_reasons("demo", "jev", {"a"}, 0) == ["SIMULATED runs are never logged"]
    assert "stored failures from more than one invocation" in score.refuse_reasons(
        "live", "jev", {"a", "b"}, 0)[0]
    assert score.refuse_reasons("live", "jev", {"a"}, 0) == []


def test_entry_names_pass_judge_and_cost_source():
    md = score.entry_md(stamp="2026-10-05T09:00:00Z", label="pass 1", judge="databricks-gpt-oss-20b",
                        invocation="inv-1", rows=[], cost=0.41, cost_source="estimated",
                        tokens_per_row={}, extra=["- requests 4,615 · wall time 812.4 s"])
    assert md.startswith("## 2026-10-05T09:00:00Z · pass 1 · databricks-gpt-oss-20b")
    assert "- invocation inv-1" in md and "- llm cost $0.410 (estimated)" in md
    assert "- requests 4,615 · wall time 812.4 s" in md


def test_unmeasured_lists_estimates_without_a_later_measurement():
    md = ("# Eval results\n"
          "## s1 · pilot · databricks-gpt-oss-20b\n\n- invocation inv-1\n"
          "- llm cost $0.010 (estimated)\n"
          "## s2 · pass 1 · jev\n\n- invocation inv-2\n"
          "## s3 · pass 1 · databricks-gpt-oss-20b\n\n- invocation inv-3\n"
          "- llm cost $0.400 (estimated)\n"
          "## s4 · measured cost · pass 1 · databricks-gpt-oss-20b\n\n- invocation inv-3\n"
          "- llm cost $0.350 (measured)\n")
    assert score.unmeasured(md) == [("pilot", "databricks-gpt-oss-20b", "inv-1")]


def test_swap_recall_splits_random_and_near_miss():
    swaps = [{"query_id": "a", "swap_type": "random"}, {"query_id": "b", "swap_type": "random"},
             {"query_id": "c", "swap_type": "near_miss"}]
    assert score.swap_recall({"a", "c", "z"}, {"a", "b", "c"}, swaps) == {
        "random": (1, 2), "near_miss": (1, 1)}


def test_false_alarms_count_flags_on_clean_natural_states_only():
    assert score.false_alarms({"a", "b", "x"}, natural={"a", "b", "c", "d"},
                              positives={"b"}) == (1, 3)
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_score.py -q` → FAIL.

- [ ] **Step 3: Implement `scripts/score.py`**

```python
"""Build, score, guard and log demo 06's benchmark.

    uv run python scripts/score.py --preregister                      # once, before pass 1
    uv run python scripts/score.py --run --judge databricks-gpt-oss-20b --scope pilot --pass 0 \
        --mode live --append                                          # confirm-first: billed
    uv run python scripts/score.py --usage                            # measured LLM spend so far

`--run` builds the models (no judging), counts the states, checks the $15 budget for an LLM
judge, then runs `dbt build --select +tag:semantic tag:baseline` with the judge (judging), and
scores what dbt stored. `--append` writes the entry to docs/eval-results.md (live only).
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jevdbx import budget, evallog, keys, metrics
from jevdbx.databricks import Sql

ROOT = Path(__file__).resolve().parents[1]
EVAL, LOG = ROOT / "eval", ROOT / "docs" / "eval-results.md"
AUDIT = "jev_demo.bench_dbt_test__audit"
JUDGMENTS = "jev_demo.bench.judgments"
JUDGES = ["jev", *budget.PRICES]


@dataclass(frozen=True)
class TestSpec:
    name: str
    model: str
    id_cols: list[str]
    state_cols: list[str]
    baseline: str | None


TESTS = {
    "banking_query_not_about_intent": TestSpec(
        "banking_query_not_about_intent", "stg_banking_queries", ["query_id"],
        ["query", "intent"], "baseline_banking_keyword"),
    "pairs_describe_same_product": TestSpec(
        "pairs_describe_same_product", "stg_product_pairs", ["pair_id"],
        ["left_record", "right_record"], "baseline_pairs_jaccard"),
    "wanderbricks_comment_contradicts_rating": TestSpec(
        "wanderbricks_comment_contradicts_rating", "stg_wanderbricks_reviews",
        ["comment", "rating"], ["comment", "rating"], None),
}


def state_expr(cols: list[str]) -> str:
    return "to_json(named_struct(" + ", ".join(f"'{c}', `{c}`" for c in cols) + "))"


def _csv(name: str) -> list[dict]:
    return list(csv.DictReader((EVAL / name).open()))


def row_id(test: str, row: list) -> str:
    if test == "wanderbricks_comment_contradicts_rating":
        return keys.state_id(row[0], float(row[1]))
    return str(row[0])


def universe(sql: Sql, spec: TestSpec) -> set[str]:
    r = sql.run(f"select {', '.join(spec.id_cols)} from jev_demo.bench.{spec.model}")
    return {row_id(spec.name, row) for row in r.rows}


def positives(sql: Sql, spec: TestSpec) -> set[str]:
    if spec.name == "banking_query_not_about_intent":
        return {s["query_id"] for s in _csv("banking77_swaps.csv")}
    if spec.name == "pairs_describe_same_product":
        return {p["pair_id"] for p in _csv("abt_buy_pairs.csv") if p["label"] == "1"}
    polarity = {p["comment_sha256"]: p["polarity"] for p in _csv("wanderbricks_polarity.csv")}
    r = sql.run(f"select comment, rating from jev_demo.bench.{spec.model}")
    return {keys.state_id(c, float(x)) for c, x in r.rows
            if keys.contradiction(polarity[keys.comment_hash(c)], float(x))}


def stored_flags(sql: Sql, spec: TestSpec, judge: str, is_llm: bool):
    r = sql.run(f"select {', '.join(spec.id_cols)}, jev_p, jev_decision, jev_judge, "
                f"jev_invocation_id from {AUDIT}.{spec.name}")
    flagged, unjudged, invs = set(), set(), set()
    for row in r.rows:
        rid = row_id(spec.name, row)
        p, decision, j, inv = row[-4], row[-3], row[-2], row[-1]
        invs.add(inv)
        if j != judge:
            continue
        if p is None and decision is None:
            unjudged.add(rid)
        elif (decision in ("true", True)) if is_llm else p is not None:
            flagged.add(rid)
    return flagged, unjudged, invs


def baseline_flags(sql: Sql, spec: TestSpec) -> set[str]:
    r = sql.run(f"select {', '.join(spec.id_cols)} from {AUDIT}.{spec.baseline}")
    return {row_id(spec.name, row) for row in r.rows}


def refuse_reasons(mode: str, judge: str, invocation_ids: set, errors: int) -> list[str]:
    if mode != "live":
        return ["SIMULATED runs are never logged"]
    if len(invocation_ids) != 1:
        return [f"stored failures from more than one invocation: {sorted(invocation_ids)}"]
    return []


def entry_md(stamp, label, judge, invocation, rows, cost, cost_source, tokens_per_row,
             extra: list[str]) -> str:
    lines = [f"## {stamp} · {label} · {judge}", "", f"- invocation {invocation}", *extra]
    if judge != "jev":
        lines.append(f"- llm cost ${cost:.3f} ({cost_source})")
        for test, (tin, tout) in tokens_per_row.items():
            lines.append(f"- tokens/row {test} in {tin} out {tout} (measured)")
    lines += ["", "| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |",
              "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(r)
    return "\n".join(lines) + "\n"


def _row(test, s: metrics.Scores, n, pos, unjudged) -> str:
    plo, phi = metrics.wilson(s.tp, s.tp + s.fp)
    rlo, rhi = metrics.wilson(s.tp, s.tp + s.fn)
    return (f"| {test} | {n:,} | {pos:,} | {s.tp + s.fp:,} | {s.precision:.2f} ({plo:.2f}–{phi:.2f}) "
            f"| {s.recall:.2f} ({rlo:.2f}–{rhi:.2f}) | {s.f1:.2f} | {unjudged:,} |")


def swap_recall(flagged: set, scope_ids: set, swaps: list[dict]) -> dict[str, tuple[int, int]]:
    """Banking77 recall per swap type (headline 3): (caught, planted) within the scope."""
    out: dict[str, tuple[int, int]] = {}
    for kind in ("random", "near_miss"):
        ids = {s["query_id"] for s in swaps if s["swap_type"] == kind} & scope_ids
        out[kind] = (len(ids & flagged), len(ids))
    return out


def natural_ids(sql: Sql, spec: TestSpec) -> set[str]:
    r = sql.run(f"select comment, rating from jev_demo.bench.{spec.model} where review_rows > 0")
    return {keys.state_id(c, float(x)) for c, x in r.rows}


def false_alarms(flagged: set, natural: set, positives: set) -> tuple[int, int]:
    """Wanderbricks control (spec §2 amendment): flags on natural states the key calls clean."""
    clean = natural - positives
    return (len(flagged & clean), len(clean))


def run_stats(sql: Sql, invocation: str, is_llm: bool) -> dict:
    """Requests, wall time (the hook windows) and, for Jev, the ledger cost of one invocation."""
    inv = invocation.replace("'", "")
    w = sql.run("select coalesce(sum(missing), 0), coalesce(sum(unix_micros(finished_at) - "
                f"unix_micros(started_at)) / 1e6, 0) from jev_demo.bench.hook_runs "
                f"where invocation_id = '{inv}'")
    calls, wall = int(w.rows[0][0]), float(w.rows[0][1])
    if is_llm:
        return {"requests": calls, "wall_s": wall, "jev_cost": None}
    r = sql.run("select count(*), coalesce(sum(pack_tokens), 0) from jev_demo.bench.requests "
                f"where invocation_id = '{inv}'")
    from jevdbx.pricing import cost_usd
    return {"requests": int(r.rows[0][0]), "wall_s": wall, "jev_cost": cost_usd(int(r.rows[0][1]))}


def dbt(*args: str) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "dbtw.py"), *args]).returncode


def unmeasured(md: str) -> list[tuple[str, str, str]]:
    """Logged LLM runs whose cost is still an estimate and has no later measured-cost entry."""
    blocks = re.split(r"\n(?=## )", md)
    measured = set()
    for block in blocks:
        inv = re.search(r"^- invocation (\S+)$", block, re.M)
        if inv and " · measured cost · " in block.splitlines()[0]:
            measured.add(inv[1])
    out = []
    for block in blocks:
        m = re.match(r"## \S+ · (pilot|pass \d+) · (\S+)$", block.splitlines()[0])
        inv = re.search(r"^- invocation (\S+)$", block, re.M)
        if m and inv and "(estimated)" in block and inv[1] not in measured:
            out.append((m[1], m[2], inv[1]))
    return out


def measure(append: bool) -> int:
    """Attribute endpoint usage to logged runs whose cost is still estimated (usage lags ~2 h):
    window = the run's hook_runs window ± 5 s; exactly one served entity must have been used."""
    sql = Sql()
    for label, judge, inv in unmeasured(LOG.read_text()):
        w = sql.run("select min(started_at) - interval 5 seconds, max(finished_at) + interval 5 "
                    "seconds from jev_demo.bench.hook_runs where invocation_id = "
                    f"'{inv.replace(chr(39), '')}'")
        start, end = w.rows[0]
        r = sql.run(budget.usage_sql(str(start), str(end)))
        m = budget.window_cost(judge, r.rows) if r.state == "SUCCEEDED" else None
        if m is None:
            print(f"{label} · {judge} · {inv}: usage not attributable yet; try again later")
            continue
        cost, n, i, o = m
        lines = [f"## {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} · measured cost · "
                 f"{label} · {judge}", "", f"- invocation {inv}",
                 f"- requests {n:,} · tokens in {i:,} out {o:,}", f"- llm cost ${cost:.3f} (measured)"]
        if label == "pilot":
            lines += [f"- tokens/row {t} in {i // n} out {o // n} (measured)" for t in TESTS]
        print("\n".join(lines))
        if append:
            evallog.append(LOG, "\n".join(lines) + "\n")
    return 0


def run(a) -> int:
    sql = Sql()
    is_llm = a.judge != "jev"
    vars_ = json.dumps({"judge": a.judge, "bench_scope": a.scope})
    if dbt("build", "--vars", vars_, "--exclude", "tag:semantic", "tag:baseline") != 0:
        return 1
    md = LOG.read_text()
    if is_llm:
        spent = evallog.llm_spend(md)  # logged runs; measured entries replace estimates
        projected = 0.0
        for test, spec in TESTS.items():
            n = len(universe(sql, spec))
            per_row = (evallog.tokens_per_row(md, a.judge, test)
                       or budget.DEFAULT_TOKENS_PER_ROW[test])
            projected += budget.project(a.judge, n, per_row)
        print(f"budget: spent ${spent:.2f} (logged) + projected ${projected:.2f}"
              f" of ${budget.CAP_USD:.2f}")
        budget.check(spent, projected)
    if a.fresh:
        sql.run(f"delete from {JUDGMENTS} where judge = '{a.judge}' and mode = '{a.mode}'")
    t0 = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    rc = dbt("build", "--vars", vars_, "--select", "+tag:semantic", "tag:baseline")
    t1 = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    rows, invs, errors, extra_lines = [], set(), 0, []
    for test, spec in TESTS.items():
        uni, pos = universe(sql, spec), positives(sql, spec) & universe(sql, spec)
        flagged, unjudged, inv = stored_flags(sql, spec, a.judge, is_llm)
        invs |= inv
        errors += len(unjudged)
        rows.append(_row(test, metrics.score(flagged, pos, uni), len(uni), len(pos), len(unjudged)))
        if test == "banking_query_not_about_intent":
            for kind, (k, n) in swap_recall(flagged, uni, _csv("banking77_swaps.csv")).items():
                lo, hi = metrics.wilson(k, n)
                extra_lines.append(f"- banking recall on {kind} swaps {k}/{n} "
                                   f"({k / n if n else 0:.2f}, 95% {lo:.2f}–{hi:.2f})")
        if test == "wanderbricks_comment_contradicts_rating":
            k, n = false_alarms(flagged, natural_ids(sql, spec), pos)
            lo, hi = metrics.wilson(k, n)
            extra_lines.append(f"- wanderbricks false alarms on natural states {k}/{n} "
                               f"({k / n if n else 0:.2f}, 95% {lo:.2f}–{hi:.2f})")
        if spec.baseline and a.judge == "jev":
            rows.append(_row(spec.baseline, metrics.score(baseline_flags(sql, spec), pos, uni),
                             len(uni), len(pos), 0))
    print("\n".join(rows))
    cost, source, tpr = 0.0, "estimated", {}
    if is_llm:
        r = sql.run(budget.usage_sql(t0, t1))
        m = budget.window_cost(a.judge, r.rows) if r.state == "SUCCEEDED" else None
        if m is not None:
            cost, n_req, i, o = m
            source = "measured"
            if a.scope == "pilot":
                tpr = {t: (i // n_req, o // n_req) for t in TESTS}
        else:
            cost = sum(budget.project(a.judge, len(universe(sql, s)),
                                      budget.DEFAULT_TOKENS_PER_ROW[t]) for t, s in TESTS.items())
    if a.append:
        reasons = refuse_reasons(a.mode, a.judge, invs, errors)
        if rc != 0:
            reasons.append(f"dbt exited {rc}")
        if reasons:
            print("not appended: " + "; ".join(reasons))
            return 1
        label = "pilot" if a.scope == "pilot" else f"pass {a.pass_}"
        inv = next(iter(invs))
        st = run_stats(sql, inv, is_llm)
        n_rows = sum(len(universe(sql, s)) for s in TESTS.values())
        run_cost = cost if is_llm else st["jev_cost"]
        extra = [f"- scope {a.scope} · {n_rows:,} rows · requests {st['requests']:,} · "
                 f"wall time {st['wall_s']:.1f} s",
                 f"- cost per 1,000 rows ${1000 * run_cost / n_rows:.4f}"
                 + ("" if is_llm else f" · jev cost ${run_cost:.4f} (ledger)"),
                 *extra_lines]
        evallog.append(LOG, entry_md(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), label,
                                     a.judge, inv, rows, cost, source, tpr, extra))
    return rc


def preregister() -> int:
    md = LOG.read_text()
    if evallog.has_preregistration(md):
        print("pre-registration already present; it is frozen")
        return 1
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dbtw.py"), "compile", "--select", "tag:semantic"],
        capture_output=True, text=True)
    swaps = _csv("banking77_swaps.csv")
    entry = "\n".join([
        evallog.PREREG, "",
        "- judges: " + ", ".join(JUDGES) + "; temperature 0; prompt version p1",
        "- prompts and test wording: bench/models/staging/schema.yml and "
        "bench/macros/jev_question.sql at commit " + subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
            cwd=ROOT).stdout.strip(),
        f"- Banking77: seed 42, sample 2,000 test queries, swaps in sample "
        f"{sum(s['in_sample'] == 'True' for s in swaps)} (75 random + 75 near-miss), "
        "families in eval/intent_families.csv",
        "- Abt-Buy: sample = test split; Jaccard threshold "
        + (EVAL / "abt_buy_jaccard.txt").read_text().strip() + " fit on train",
        "- wanderbricks: every natural (comment, rating) state (the control: false-alarm rate) "
        "+ planted ratings in eval/wanderbricks_flips.csv (seed 42); rule in "
        "jevdbx.keys.contradiction",
        "- headline 1: per dataset, F1 of Jev vs each LLM (decision level), Wilson 95% for P and R",
        "- headline 2: per dataset, cost per 1,000 rows and wall time per judge",
        "- headline 3: Banking77 recall on random vs near-miss swaps, per judge",
        f"- dbt compile exit {out.returncode}", ""])
    evallog.append(LOG, entry)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--judge", choices=JUDGES, default="jev")
    ap.add_argument("--scope", choices=["pilot", "sample", "full"], default="sample")
    ap.add_argument("--pass", dest="pass_", type=int, default=1)
    ap.add_argument("--mode", choices=["live", "demo"])
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--preregister", action="store_true")
    ap.add_argument("--usage", action="store_true")
    ap.add_argument("--measure", action="store_true")
    a = ap.parse_args(argv)
    if a.preregister:
        return preregister()
    if a.usage:
        r = Sql().run(budget.usage_sql(budget.SINCE))
        print(f"endpoint usage since {budget.SINCE} by served entity (no names: spec S2):")
        for row in r.rows:
            print("  ", row)
        return 0
    if a.measure:
        return measure(a.append)
    if a.run:
        if a.mode is None:
            ap.error("--run needs --mode live|demo")
        import os
        os.environ["JEV_MODE"] = a.mode
        return run(a)
    if a.append:
        ap.error("--append needs --run")
    ap.error("nothing to do")
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

`docs/eval-results.md`:

```markdown
# Eval results

Every scored live run of demo 06, newest last, written by `scripts/score.py --run --append`.
SIMULATED runs are never written here. LLM cost lines say `measured` (from
`system.serving.endpoint_usage`) or `estimated` (token assumptions); Jev cost comes from the ledger.
```

- [ ] **Step 4: Run** — `uv run pytest tests/test_score.py -q && uv run ruff check` → PASS (7).

- [ ] **Step 5: Commit**

```bash
git add scripts/score.py tests/test_score.py docs/eval-results.md
git commit -m "feat(score): build, budget guard, score against ground truth, pre-register, log

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12b: Side analyses (`score.py --compare`)

**Files:**
- Modify: `scripts/score.py` (add `THRESHOLD`, `judged_rows`, `side_md`, `--compare`)
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: Task 12's `TESTS`, `state_expr`, `positives`, `universe`, `row_id`; `jevdbx.metrics`.
- Produces: `THRESHOLD = 0.8`; `judged_rows(sql, spec) -> dict[str, dict[str, tuple[float | None, bool | None]]]` (judge → id → (p, decision)) from live judgments in the current scope; `side_md(test, per_judge, positives, universe) -> str`; CLI `score.py --compare --append` writes one `## <stamp> · side analyses · <scope>` entry (live judgments only, all four judges required).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_score.py`)

```python
def test_thresholds_in_schema_match_the_scorer():
    import yaml
    doc = yaml.safe_load((ROOT / "bench" / "models" / "staging" / "schema.yml").read_text())
    found = [t["jev_expect"]["arguments"]["threshold"] for m in doc["models"]
             for c in m.get("columns", []) for t in c.get("data_tests", [])
             if isinstance(t, dict) and "jev_expect" in t]
    assert found == [score.THRESHOLD] * 3


def test_side_md_reports_calibration_thresholded_f1_agreement_and_key_errors():
    uni = {"a", "b", "c", "d"}
    pos = {"a", "b"}
    per_judge = {
        "jev": {"a": (0.95, None), "b": (0.4, None), "c": (0.9, None), "d": (0.1, None)},
        "databricks-gpt-oss-20b": {"a": (0.9, True), "b": (0.9, True), "c": (0.6, True),
                                   "d": (0.2, False)},
    }
    md = score.side_md("t", per_judge, pos, uni)
    assert "| jev | 0.30 |" in md                   # Brier = (0.0025+0.36+0.81+0.01)/4
    llm_line = next(x for x in md.splitlines() if x.startswith("| databricks-gpt-oss-20b |"))
    assert llm_line.endswith("| 1.00 |")             # p >= 0.8 flags exactly a, b
    assert "possible key errors (flagged by every judge, not in the key): c" in md
    assert "agreement on positives: all 1 · none 0 · only jev 0 · only databricks-gpt-oss-20b 1" in md
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_score.py -q` → FAIL.

- [ ] **Step 3: Implement** (add to `scripts/score.py`)

```python
THRESHOLD = 0.8  # every jev_expect in schema.yml (a test keeps them equal)


def judged_rows(sql: Sql, spec: TestSpec) -> dict[str, dict[str, tuple]]:
    ids = ", ".join(f"m.`{c}`" for c in spec.id_cols)
    r = sql.run(
        f"select {ids}, j.judge, j.p, j.decision from jev_demo.bench.{spec.model} m "
        # unqualified state columns resolve to m: judgments has no column with those names
        f"join {JUDGMENTS} j on j.state = {state_expr(spec.state_cols)} "
        f"and j.test_name = '{spec.name}' and j.mode = 'live' "
        f"and (j.p is not null or j.decision is not null)")
    out: dict[str, dict[str, tuple]] = {}
    for row in r.rows:
        rid = row_id(spec.name, row[: len(spec.id_cols)])
        judge, p, d = row[len(spec.id_cols):]
        out.setdefault(judge, {})[rid] = (None if p is None else float(p),
                                          None if d is None else d in ("true", True))
    return out


def _flags(judge: str, rows: dict[str, tuple]) -> set[str]:
    if judge == "jev":
        return {i for i, (p, _) in rows.items() if p is not None and p >= THRESHOLD}
    return {i for i, (_, d) in rows.items() if d}


def side_md(test: str, per_judge: dict, pos: set, uni: set) -> str:
    lines = [f"### {test}", "", "| judge | Brier | reliability (bin: observed, n) | thresholded F1 |",
             "|---|---|---|---|"]
    for judge, rows in per_judge.items():
        ids = sorted(i for i in rows if i in uni and rows[i][0] is not None)
        probs = [rows[i][0] for i in ids]
        labels = [i in pos for i in ids]
        b = metrics.brier(probs, labels) if ids else float("nan")
        rel = " ".join(f"{lo:.1f}-{hi:.1f}: {rate:.2f}, {n}"
                       for lo, hi, rate, n in metrics.reliability(probs, labels, bins=5) if n)
        thr = {i for i in ids if rows[i][0] >= THRESHOLD}
        f1 = metrics.score(thr, pos, uni).f1
        lines.append(f"| {judge} | {b:.2f} | {rel} | "
                     + ("(the decision rule)" if judge == "jev" else f"{f1:.2f}") + " |")
    flags = {j: _flags(j, rows) for j, rows in per_judge.items()}
    a = metrics.agreement(flags, pos)
    lines += ["", "agreement on positives: " + " · ".join(
        f"{k.replace('only_', 'only ')} {v}" for k, v in a.items())]
    every = set.intersection(*flags.values()) - pos if flags else set()
    lines.append("possible key errors (flagged by every judge, not in the key): "
                 + (", ".join(sorted(every)[:50]) or "none"))
    return "\n".join(lines) + "\n"
```

Add to `main()` before `if a.run:`:

```python
    if a.compare:
        sql = Sql()
        parts = []
        for test, spec in TESTS.items():
            per = judged_rows(sql, spec)
            missing = [j for j in JUDGES if j not in per]
            if missing:
                print(f"{test}: no live judgments yet for {missing}; nothing compared")
                return 1
            uni = universe(sql, spec)
            parts.append(side_md(test, per, positives(sql, spec) & uni, uni))
        text = "\n".join(parts)
        print(text)
        if a.append:
            evallog.append(LOG, f"## {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} · side "
                                f"analyses · {a.scope}\n\n{text}")
        return 0
```

and the flag `ap.add_argument("--compare", action="store_true")`.

- [ ] **Step 4: Run** — `uv run pytest tests/test_score.py -q && uv run ruff check` → PASS (9).

- [ ] **Step 5: Commit**

```bash
git add scripts/score.py tests/test_score.py
git commit -m "feat(score): side analyses: calibration, thresholded F1, agreement, possible key errors

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Terminal views for the video

**Files:**
- Create: `scripts/show.py`, `tests/test_show.py`

**Interfaces:**
- Consumes: `docs/eval-results.md`, `score.TESTS`.
- Produces: `show.py tests` (the three sentences from `schema.yml`), `show.py board` (latest logged entry per judge: F1 per dataset and cost, from the eval log only), `board_rows(md: str) -> list[tuple[str, str, str, str]]` (judge, test, F1, cost).

- [ ] **Step 1: Write the failing test**

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("show", ROOT / "scripts" / "show.py")
show = importlib.util.module_from_spec(spec)
spec.loader.exec_module(show)

MD = """## 2026-10-05T09:00:00Z · pass 1 · jev

- invocation a

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 2,000 | 150 | 140 | 0.90 (0.84–0.94) | 0.84 (0.77–0.89) | 0.87 | 0 |

## 2026-10-05T10:00:00Z · pass 1 · databricks-gpt-oss-20b

- invocation b
- llm cost $0.410 (measured)

| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |
|---|---|---|---|---|---|---|---|
| banking_query_not_about_intent | 2,000 | 150 | 150 | 0.80 (0.73–0.86) | 0.80 (0.73–0.86) | 0.80 | 2 |
"""


def test_board_reads_the_latest_entry_per_judge_from_the_log_only():
    assert show.board_rows(MD) == [
        ("jev", "banking_query_not_about_intent", "0.87", "-"),
        ("databricks-gpt-oss-20b", "banking_query_not_about_intent", "0.80", "$0.410 (measured)"),
    ]
```

- [ ] **Step 2: Run to verify failure** — FAIL.

- [ ] **Step 3: Implement `scripts/show.py`**

```python
"""Terminal views for the recording. Numbers come only from docs/eval-results.md.

    uv run python scripts/show.py tests     # the three sentences
    uv run python scripts/show.py board     # latest logged pass per judge
"""

import re
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[1]


def board_rows(md: str) -> list[tuple[str, str, str, str]]:
    latest: dict[str, str] = {}
    for block in re.split(r"\n(?=## \d{4}-)", md):
        m = re.match(r"## \S+ · pass \d+ · (\S+)", block.strip())
        if m:
            latest[m[1]] = block
    out = []
    for judge, block in latest.items():
        cost = re.search(r"^- llm cost (\$[0-9.]+ \(\w+\))$", block, re.M)
        for line in block.splitlines():
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 8 and not cells[0].startswith(("test", "---", "baseline")):
                out.append((judge, cells[0], cells[6], cost[1] if cost else "-"))
    return out


def tests() -> None:
    doc = yaml.safe_load((ROOT / "bench" / "models" / "staging" / "schema.yml").read_text())
    for model in doc["models"]:
        for col in model.get("columns", []):
            for t in col.get("data_tests", []):
                if isinstance(t, dict) and "jev_expect" in t:
                    e = t["jev_expect"]
                    print(f"{e['name']}\n  {e['arguments']['fails_if']}\n")


def board() -> None:
    table = Table(title="latest logged pass per judge")
    for c in ("judge", "test", "F1", "LLM cost"):
        table.add_column(c)
    for row in board_rows((ROOT / "docs" / "eval-results.md").read_text()):
        table.add_row(*row)
    Console().print(table)


if __name__ == "__main__":
    {"tests": tests, "board": board}[sys.argv[1]]()
```

- [ ] **Step 4: Run** — `uv run pytest tests/test_show.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/show.py tests/test_show.py
git commit -m "feat(show): sentences and a board read from the eval log only

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Platform deploy and SIMULATED integration tests (confirm-first: schema creation)

**Files:**
- Create: `tests/integration/test_bench_demo.py`

**Interfaces:**
- Consumes: everything above. Needs schema `jev_demo.bench` (user OK) and only `samples.wanderbricks` (no upload).

- [ ] **Step 1: Ask the user, then deploy the platform objects**

Ask: "Task 14 creates schema `jev_demo.bench`, volume `jev_demo.bench.raw`, the judgments/hook_runs tables, the requests view and the SIMULATED `llm_demo` function on the dev warehouse (DDL only, no Jev or LLM call). OK?" On yes:

Run: `DATABRICKS_CONFIG_PROFILE=jev-demo-5 uv run python scripts/deploy.py --apply`
Expected: six lines `… SUCCEEDED`.

- [ ] **Step 2: Write the integration tests**

```python
"""SIMULATED end-to-end on the dev warehouse (wanderbricks only: no upload needed)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jevdbx.databricks import Sql

ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.databricks
LLM = "databricks-gpt-oss-20b"


def dbt(*args):
    env = {**os.environ, "JEV_MODE": "demo", "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "dbtw.py"), *args],
                          env=env, capture_output=True, text=True, timeout=1800)


@pytest.mark.parametrize("judge", ["jev", LLM])
def test_simulated_build_judges_every_state_once(judge):
    sql = Sql()
    sql.run(f"delete from jev_demo.bench.judgments where judge = '{judge}' and mode = 'demo'")
    vars_ = json.dumps({"judge": judge, "bench_scope": "pilot"})
    out = dbt("build", "--vars", vars_, "--select", "+stg_wanderbricks_reviews",
              "wanderbricks_comment_contradicts_rating")
    assert out.returncode == 0, out.stdout[-3000:]
    assert "once-per-row OK · SIMULATED" in out.stdout
    n = sql.run("select count(*) from jev_demo.bench.stg_wanderbricks_reviews").scalar()
    j = sql.run(f"select count(*) from jev_demo.bench.judgments where judge = '{judge}' "
                "and mode = 'demo'").scalar()
    assert int(j) == int(n)
    rerun = dbt("build", "--vars", vars_, "--select", "+stg_wanderbricks_reviews",
                "wanderbricks_comment_contradicts_rating")
    assert " 0 judged now" in rerun.stdout


def test_simulated_llm_errors_are_stored_not_flagged():
    sql = Sql()
    r = sql.run(f"select count_if(error is not null), count_if(error is not null and "
                f"(p is not null or decision is not null)) from jev_demo.bench.judgments "
                f"where judge = '{LLM}' and mode = 'demo'")
    errors, leaked = (int(x) for x in r.rows[0])
    assert leaked == 0
    assert errors >= 0   # ~1 in 97 prompts errors in llm_demo; 50 rows may hold none
```

- [ ] **Step 3: Run** — `DATABRICKS_CONFIG_PROFILE=jev-demo-5 uv run pytest -m databricks -q`
Expected: PASS (3). If `samples.wanderbricks` is missing in the workspace, stop and report.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_bench_demo.py
git commit -m "test(integration): SIMULATED judge paths end to end on the dev warehouse

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Live runbook — data, labels, pre-registration, pilot, passes, scale

Every step here is confirm-first with the estimate shown; record each OK in the session. No code changes unless a step fails (then: systematic-debugging, fix with a test, commit).

**Files:**
- Create (by scripts): `eval/banking77_swaps.csv`, `eval/banking77_sample.csv`, `eval/intent_families.csv`, `eval/abt_buy_pairs.csv`, `eval/abt_buy_jaccard.txt`, `eval/wanderbricks_polarity.csv`, `bench/seeds/*.csv`, entries in `docs/eval-results.md`

- [ ] **Step 1: Download (ask: names, sources, sizes from `eval/sources.toml`)** — `uv run python scripts/fetch_data.py --download`. Expected: `banking77: 13083 rows · abt_buy: N pairs (M matches)`; N and M equal S1's numbers.
- [ ] **Step 2: Keys** — `uv run python scripts/make_keys.py banking && uv run python scripts/make_keys.py abt`. Expected: 150 in-sample swaps (75/75). Commit `eval/` and `bench/seeds/` (`git add eval bench/seeds`; message `data: Banking77 swaps and sample, Abt-Buy labels and Jaccard threshold`).
- [ ] **Step 3: Upload (ask: two parquet files to `/Volumes/jev_demo/bench/raw/`)** — `uv run python scripts/fetch_data.py --upload`; then `uv run python scripts/dbtw.py seed && uv run python scripts/dbtw.py build --exclude tag:semantic tag:baseline` (no judging).
- [ ] **Step 4: wanderbricks labels by the user and planted ratings** — `uv run python scripts/make_keys.py wanderbricks-flips` (standing-OK query; expected ≈ 40 planted ratings over 15 comments); `uv run python scripts/make_keys.py wanderbricks-template`; the user fills `data/wanderbricks_label_me.csv`; then `wanderbricks-commit`; `uv run python scripts/dbtw.py seed`; commit `eval/wanderbricks_polarity.csv`, `eval/wanderbricks_flips.csv`, `bench/seeds/wanderbricks_flips.csv`.
- [ ] **Step 5: Re-check prices** on the Databricks pricing pages, and verify `databricks-claude-opus-5` (an estimate until now); if any changed, update `budget.PRICES` with a test and commit.
- [ ] **Step 6: Pre-register** — `uv run python scripts/score.py --preregister`; commit `docs/eval-results.md` (`docs: pre-registration, frozen before pass 1`). From here on, prompts and sentences are frozen.
- [ ] **Step 7: Pilot (ask: 50 rows per dataset per judge; est. ≈ $0.10 LLM, under $0.01 Jev)** — for each judge: `uv run python scripts/score.py --run --judge <judge> --scope pilot --pass 0 --mode live --append`. Expected: entries with `tokens/row … (measured)` lines for each LLM, or `estimated` cost when usage has not landed (it lags ~2 h): then later `uv run python scripts/score.py --measure --append` writes `measured cost` entries that replace the estimates (and carry the pilot's tokens/row).
- [ ] **Step 8: Re-estimate pass 1** from the measured tokens/row; show the user the per-judge estimate and the running total against $15.
- [ ] **Step 9: Pass 1 (ask with the step-8 estimate)** — `--scope sample --pass 1` for `jev`, then each LLM.
- [ ] **Step 10: Pass 2 (ask)** — the same with `--fresh --pass 2` for `jev`, `databricks-gpt-oss-20b` and `databricks-meta-llama-3-3-70b-instruct` only (spec S2 amendment: Opus 5 gets one pass).
- [ ] **Step 11: Jev at scale (ask: est. ≈ $0.25)** — `--judge jev --scope full --pass 3`.
- [ ] **Step 12: Commit the log** after each logged step: `git add docs/eval-results.md && git commit -m "eval: <step> (<judge>)"` with the Co-Authored-By trailer.

---

### Task 16: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`** with these sections, numbers only from `docs/eval-results.md` once logged (until then the Results section says "No numbers yet: the live runs have not been made."): what it shows (one test, four judges, `--vars`), the three datasets with sources and licences (Banking77 CC BY 4.0 with citation; the entity-matching dataset as recorded in `eval/sources.toml`; wanderbricks from the Databricks samples catalog), how it works (the judging hook's two paths, single-source prompt, per-judge cache), prerequisites (demo 05's function and secret, the bench schema), run commands (from CLAUDE.md), budgets and how cost is measured, fairness rules (frozen prompts, temperature 0, pre-registration), results, pins.
- [ ] **Step 2: Verify** — `uv run pytest -q && uv run ruff check && git ls-files | xargs grep -l "TODO\|TBD" || true` → tests pass, no TODO/TBD in tracked files.
- [ ] **Step 3: Commit** — `git add README.md && git commit -m "docs: README"` with the trailer.

---

## Self-review notes (resolved)

- Spec §2 datasets, sample sizes, swap mix, families, wanderbricks rule → Tasks 7, 8, 9, 15.
  Possible key errors → Task 12b.
- Spec §4 switch, single prompt source, decisions, per-judge cache, loud errors, SIMULATED →
  Tasks 4, 5, 6, 14. Jev flags `p >= threshold` (demo 05's rule); Task 6 Step 7 amends the spec.
- Spec §5 platform and data handling → Tasks 4, 8, 14, 15 (schema creation, downloads, uploads all
  confirm-first).
- Spec §6 spikes, pilot, passes, scale, $15 guard → Tasks 2, 3, 11, 12, 15.
- Spec §7 pre-registration (Task 12), headline 1 (P/R/F1 + Wilson per entry, Task 12), headline 2
  (cost per 1,000 rows, requests, wall time per entry, Task 12), headline 3 (Banking77 recall per
  swap type, Task 12), side analyses (Task 12b).
- Spec §8 layout and tests → file map, Tasks 1–14; §9 publishing → after this plan (same flow as
  demo 05); README → Task 16.
- Names checked across tasks: `jev_judge_name`, `jev_is_llm`, `jev_judge_model`, `jev_layout`,
  `jev_prompt_expr`, `jev_llm_call`; `Target.fq/fn`; `budget.PRICES/CAP_USD/SINCE/
  DEFAULT_TOKENS_PER_ROW/usage_sql/project/check/cost_usd`; `evallog.llm_spend/tokens_per_row/
  append/has_preregistration/PREREG`; `score.TESTS/THRESHOLD/state_expr/stored_flags/run_stats/
  swap_recall/entry_md/side_md/judged_rows`; tests `banking_query_not_about_intent`,
  `pairs_describe_same_product`, `wanderbricks_comment_contradicts_rating`.
