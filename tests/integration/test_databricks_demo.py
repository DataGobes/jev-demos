"""Demo-mode end-to-end on the dev warehouse. Run: uv run pytest -m databricks -q

dbt runs through scripts/dbtw.py (host, warehouse and a short-lived token from the Databricks
CLI profile; nothing is printed). JEV_MODE=demo everywhere: never a live Jev call."""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from jevdbx.databricks import Sql

pytestmark = pytest.mark.databricks
ROOT = Path(__file__).parents[2]
DEMO4_DB = Path.home() / "Projects/jev-demo-4/jaffle_shop/jaffle_shop.duckdb"
BASELINES = ["customers_full_name_is_a_person", "returns_comment_matches_reason_code",
             "reviews_body_matches_stars", "tickets_body_has_no_pii"]
ID_COL = {"customers_full_name_is_a_person": "customer_id",
          "returns_comment_matches_reason_code": "return_id",
          "reviews_body_matches_stars": "review_id", "tickets_body_has_no_pii": "ticket_id"}


def dbt(*args):
    """dbt on the dev target via scripts/dbtw.py, demo mode only."""
    env = {**os.environ, "JEV_MODE": "demo", "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    return subprocess.run(["uv", "run", "python", "scripts/dbtw.py", *args],
                          cwd=ROOT, capture_output=True, text=True, env=env, timeout=1800)


def clear_demo_rows(sql):
    assert sql.run("delete from jev_demo.jev.judgments where mode = 'demo'").state == "SUCCEEDED"


@pytest.fixture(scope="module")
def sql():
    return Sql()


@pytest.fixture(scope="module")
def cold_build(sql):
    clear_demo_rows(sql)
    seed = dbt("seed")
    assert seed.returncode == 0, seed.stdout[-3000:]
    # relationships tests on stg_returns/stg_reviews read stg_orders, which +tag:semantic does not
    # select; on a fresh schema it must exist first (no jev_expect tests: its hook is a no-op).
    orders = dbt("run", "--select", "stg_orders")
    assert orders.returncode == 0, orders.stdout[-3000:]
    return dbt("build", "--select", "+tag:semantic", "tag:baseline")


def test_cold_build_judges_every_state_once(cold_build):
    out = cold_build.stdout
    assert cold_build.returncode == 0, out[-4000:]
    assert "SIMULATED" in out and "once-per-row OK" in out and "0% cached" in out
    # 1,057 = demo 04's distinct (test, state) count at pack=1. If this differs, find out why
    # (e.g. a to_json difference) before touching the number.
    assert "1,057 judgments" in out


def test_rerun_is_fully_cached(cold_build):
    res = dbt("build", "--select", "+tag:semantic")
    assert res.returncode == 0, res.stdout[-3000:]
    assert "100% cached" in res.stdout and " 0 requests" in res.stdout


def test_single_python_eval_in_insert_plan(sql, cold_build):
    res = dbt("run-operation", "jev_render_judge",
              "--args", json.dumps({"model_name": "stg_reviews"}))
    assert res.returncode == 0, res.stdout[-3000:]
    insert = res.stdout.split("-- insert\n", 1)[1].split("\n-- inserted\n", 1)[0]
    # EXPLAIN of the INSERT itself shows only the write node (AppendDataExecV1), so explain the
    # query it writes: everything from the CTEs on.
    query = insert[insert.index("with tested as"):]
    plan = "\n".join(str(r[0]) for r in sql.run("explain formatted " + query).rows)
    # Photon runs a UC Python function as PhotonScalarUDF; classic Spark as *EvalPython*.
    nodes = re.findall(r"^\((\d+)\) (\w*(?:EvalPython|ScalarUDF)\w*)", plan, re.M)
    assert len(nodes) == 1, plan[:3000]
    assert plan.count("jev_demo.jev.noul_pack_demo(") == 1, plan[:3000]


def test_one_uuid_per_pack_and_every_row_written_once(sql, cold_build):
    packs, mismatched, rows = sql.run(
        "select count(*), count_if(rows_written <> pack_rows), sum(pack_rows) "
        "from jev_demo.jev.requests where mode = 'demo'").rows[0]
    assert int(packs) > 0 and int(mismatched) == 0 and int(rows) == 1057
    shared = sql.run(
        "select count(*) from (select pack_uuid from jev_demo.jev.judgments where mode = 'demo' "
        "and pack_uuid is not null group by pack_uuid having count(distinct test_name) > 1 "
        "or count(distinct pack_rows) > 1 or count(distinct pack_tokens) > 1)").scalar()
    assert int(shared) == 0


def test_stored_failures_have_jev_p(sql, cold_build):
    total, with_p = sql.run(
        "select count(*), count(jev_p) from "
        "jev_demo.jaffle_shop_dbt_test__audit.reviews_body_matches_stars").rows[0]
    assert int(total) == int(with_p) > 0


def test_staging_matches_demo04_and_has_no_nulls(sql, cold_build):
    counts = {m: int(sql.run(f"select count(*) from jev_demo.jaffle_shop.{m}").scalar())
              for m in ["stg_customers", "stg_orders", "stg_returns", "stg_reviews", "stg_tickets"]}
    assert counts == {"stg_customers": 500, "stg_orders": 1500, "stg_returns": 200,
                      "stg_reviews": 400, "stg_tickets": 200}
    nulls = sql.run(
        "select (select count(*) from jev_demo.jaffle_shop.stg_customers"
        " where full_name is null or email is null)"
        " + (select count(*) from jev_demo.jaffle_shop.stg_returns"
        " where comment is null or reason_code is null)"
        " + (select count(*) from jev_demo.jaffle_shop.stg_reviews"
        " where body is null or stars is null)"
        " + (select count(*) from jev_demo.jaffle_shop.stg_tickets where body is null)").scalar()
    assert int(nulls) == 0  # so Spark's to_json NULL-field omission cannot change any state
    # dbt-core's seed reader turns the text "Null" into NULL; jevdbx.dbt_cli keeps it (demo 04 does)
    assert sql.run("select full_name from jev_demo.jaffle_shop.stg_customers"
                   " where customer_id = 477").scalar() == "Sofie Null"


@pytest.mark.skipif(not DEMO4_DB.exists(), reason="demo 04 DuckDB file not present")
@pytest.mark.parametrize("name", BASELINES)
def test_baselines_flag_same_rows_as_demo04(sql, cold_build, name):
    ref = subprocess.run(["uv", "run", "python", "scripts/demo04_reference.py", name],
                         cwd=ROOT, capture_output=True, text=True)
    if ref.returncode == 2:
        pytest.skip(ref.stdout.strip())
    assert ref.returncode == 0, ref.stderr[-2000:]
    theirs = set(json.loads(ref.stdout))
    ours = {int(r[0]) for r in sql.run(
        f"select {ID_COL[name]} from jev_demo.jaffle_shop_dbt_test__audit.baseline_{name}").rows}
    assert ours == theirs


def test_oversized_rows_are_reported_not_sent(sql, cold_build):
    clear_demo_rows(sql)
    res = dbt("build", "--select", "+stg_reviews", "--vars", "{jev_row_token_limit: 40}")
    assert res.returncode == 0, res.stdout[-3000:]
    # The hook judges distinct states: 400 reviews have 241 distinct (body, stars) states.
    states = sql.run("select count(distinct body, stars) from jev_demo.jaffle_shop.stg_reviews")
    assert int(states.scalar()) == 241
    assert " 0 requests" in res.stdout and "+241 too long" in res.stdout
    errs = sql.run("select count(*) from jev_demo.jev.judgments where mode = 'demo' "
                   "and test_name = 'reviews_body_matches_stars' "
                   "and error like 'row exceeds token limit%'").scalar()
    assert int(errs) == 241
    # Mixed: a limit at the median estimate sends some rows in packs and reports the rest, so
    # both branches of the INSERT's UNION ALL write in one statement. Oversized rows store their
    # estimate in pack_est_tokens.
    limit = int(sql.run("select cast(percentile_disc(0.5) within group (order by pack_est_tokens)"
                        " as bigint) "
                        "from jev_demo.jev.judgments where mode = 'demo' "
                        "and test_name = 'reviews_body_matches_stars'").scalar())
    over = int(sql.run("select count_if(pack_est_tokens > " + str(limit) + ") from "
                       "jev_demo.jev.judgments where mode = 'demo' "
                       "and test_name = 'reviews_body_matches_stars'").scalar())
    assert 0 < over < 241
    clear_demo_rows(sql)
    res = dbt("build", "--select", "stg_reviews", "--vars", f"{{jev_row_token_limit: {limit}}}")
    assert res.returncode == 0, res.stdout[-3000:]
    assert f"packs sum {241 - over:,} (+{over:,} too long)" in res.stdout, res.stdout[-3000:]
    judged, unjudged = sql.run(
        "select count(p), count_if(p is null and error like 'row exceeds token limit%') "
        "from jev_demo.jev.judgments where mode = 'demo'").rows[0]
    assert (int(judged), int(unjudged)) == (241 - over, over)
    clear_demo_rows(sql)
