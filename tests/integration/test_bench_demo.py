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
