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
    assert rerun.returncode == 0, rerun.stdout[-3000:]
    assert " 0 judged now" in rerun.stdout


def test_simulated_llm_error_rows_are_stored_and_unjudged():
    """llm_demo errors on ~1 in 97 prompts: those rows are stored with an error and no verdict,
    and come back from the test as unjudged (jev_p and jev_decision null), never flagged."""
    sql = Sql()
    where = f"judge = '{LLM}' and mode = 'demo'"
    sql.run(f"delete from jev_demo.bench.judgments where {where}")
    vars_ = json.dumps({"judge": LLM, "bench_scope": "sample"})
    out = dbt("build", "--vars", vars_, "--select", "+stg_wanderbricks_reviews",
              "wanderbricks_comment_contradicts_rating")
    assert out.returncode == 0, out.stdout[-3000:]
    r = sql.run("select count(*), count_if(error is not null), "
                "count_if(error is not null and (p is not null or decision is not null)), "
                f"count_if(error is null and decision is null) "
                f"from jev_demo.bench.judgments where {where}")
    total, errors, leaked, verdictless = (int(x) for x in r.rows[0])
    assert total >= 205, total
    assert errors > 0, f"no error rows stored among {total} judgments"
    assert leaked == 0
    assert verdictless == 0
    unjudged = sql.run(
        "select count(*) from jev_demo.bench_dbt_test__audit."
        "wanderbricks_comment_contradicts_rating "
        f"where jev_judge = '{LLM}' and jev_p is null and jev_decision is null").scalar()
    assert int(unjudged) == errors, (unjudged, errors)
