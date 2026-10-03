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
    assert ("judge STRING" in sql and "started_at TIMESTAMP" in sql
            and "finished_at TIMESTAMP" in sql)


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
