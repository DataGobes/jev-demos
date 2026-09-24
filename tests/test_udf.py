import json

import duckdb

from jevdbt.runtime import Settings, build_runtime
from jevdbt.udf import register


def make_con(tmp_path):
    rt = build_runtime(Settings("demo", "jev-latest", 1, 4, 0, None))
    con = duckdb.connect()
    register(con, rt)
    return con, rt


def test_jev_noul_over_json_struct_groups_questions(tmp_path):
    con, rt = make_con(tmp_path)
    con.execute(
        "create table t as select * from "
        "(values (1,'a','x'),(2,'b','y'),(3,null,'z')) v(id,c,d)"
    )
    q1 = json.dumps({"instructions": "Q1 about `d`"})
    q2 = json.dumps({"instructions": "Q2", "criteria": {"true": "it's yes", "false": "no"}})
    q2_sql = q2.replace("'", "''")
    rows = con.execute(
        f"""select id,
                   jev_noul(
                       case when c is null then null
                       else to_json(struct_pack(c := c, d := d)) end,
                       '{q1}'),
                   jev_noul(to_json(struct_pack(c := c, d := d)), '{q2_sql}')
            from t order by id"""
    ).fetchall()
    assert rows[2][1] is None
    assert all(0.0 <= r[1] <= 1.0 for r in rows[:2])
    assert all(0.0 <= r[2] <= 1.0 for r in rows)
    assert rt.stats.snapshot().judgments == 5
    rt.scorer.close()


def test_materialized_cte_evaluates_once(tmp_path):
    con, rt = make_con(tmp_path)
    con.execute("create table t as select range as id, 'txt' || range as c from range(300)")
    q = json.dumps({"instructions": "Q"})
    con.execute(
        f"""with judged as materialized (
              select *, jev_noul(to_json(struct_pack(c := c)), '{q}') as jev_p from t)
            select * from judged where jev_p >= 0.5"""
    ).fetchall()
    assert rt.stats.snapshot().judgments == 300
    rt.scorer.close()


def test_jev_stats_returns_json(tmp_path):
    con, rt = make_con(tmp_path)
    data = json.loads(con.execute("select jev_stats()").fetchone()[0])
    assert data["simulated"] is True and "summary" in data
    rt.scorer.close()


def test_bad_question_raises_clear_error(tmp_path):
    con, rt = make_con(tmp_path)
    try:
        con.execute("select jev_noul('{}', 'not json')").fetchall()
        raise AssertionError("expected an error")
    except duckdb.Error as exc:
        assert "jev_noul" in str(exc)
    rt.scorer.close()
