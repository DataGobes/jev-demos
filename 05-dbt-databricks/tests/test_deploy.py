import json
import sys
import textwrap
import types

import pytest

from jevdbx import deploy

T = deploy.Target()


def _exec_body(sql: str, fake_modules: dict):
    """Run a rendered function body the way UC does: as the body of a Python function.

    The fake modules are installed only while the function runs (its imports execute at call time).
    """
    body = sql.split("AS $$", 1)[1].rsplit("$$", 1)[0]
    src = "def __udf(records, question, model):\n" + textwrap.indent(body, "    ")
    ns: dict = {}
    exec(compile(src, "<udf>", "exec"), ns)

    def call(*args):
        saved = {k: sys.modules.get(k) for k in fake_modules}
        sys.modules.update(fake_modules)
        try:
            return ns["__udf"](*args)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    return call


def test_live_function_clauses():
    sql = deploy.live_function_sql(T)
    assert sql.startswith("CREATE OR REPLACE FUNCTION jev_demo.jev.noul_pack(")
    assert "records ARRAY<STRING>, question STRING, model STRING" in sql
    assert "RETURNS STRING" in sql and "LANGUAGE PYTHON" in sql and "NOT DETERMINISTIC" in sql
    assert "SECRETS (jev_demo.jev.typesafe_api_key)" in sql
    assert "ENVIRONMENT (environment_version = '6')" in sql
    assert sql.count("$$") == 2


def test_demo_function_has_no_secret_and_no_network():
    sql = deploy.demo_function_sql(T)
    assert "jev_demo.jev.noul_pack_demo(" in sql and "SECRETS" not in sql
    assert "urllib" not in sql and "typesafe.ai" not in sql


def test_live_body_runs_inside_a_function(monkeypatch):
    secrets = types.ModuleType("databricks.secrets")
    got = {}

    def fake_get(catalog, schema, key):
        got.update(catalog=catalog, schema=schema, key=key)
        return "K"

    secrets.get = fake_get
    pkg = types.ModuleType("databricks")
    pkg.secrets = secrets
    fakes = {"databricks": pkg, "databricks.secrets": secrets}
    udf = _exec_body(deploy.live_function_sql(T), fakes)

    import urllib.request

    class Resp:
        status = 200
        headers = {}

        def read(self):
            return json.dumps({"model": "jev-1.13.0", "answers": {"r000": {"noul": 0.8}},
                               "usage": {"input_tokens": 9}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: Resp())
    res = json.loads(udf(['{"a": 1}'], json.dumps({"instructions": "q"}), "jev-1.13.0"))
    assert res["values"] == [0.8] and res["input_tokens"] == 9
    assert got == {"catalog": "jev_demo", "schema": "jev", "key": "typesafe_api_key"}


def test_demo_body_runs_inside_a_function():
    udf = _exec_body(deploy.demo_function_sql(T), {})
    res = json.loads(udf(['{"a": 1}', '{"a": 2}'], json.dumps({"instructions": "q"}), "m"))
    assert len(res["values"]) == 2 and res["model"] == "demo:m"


def test_tables_and_view():
    j = deploy.judgments_table_sql(T)
    for col in ["key STRING", "test_name STRING", "p DOUBLE", "pack_uuid STRING",
                "pack_tokens BIGINT", "pack_est_tokens BIGINT", "retry_statuses ARRAY<INT>",
                "invocation_id STRING", "judged_at TIMESTAMP"]:
        assert col in j
    assert j.startswith("CREATE TABLE IF NOT EXISTS jev_demo.jev.judgments")
    assert "CLUSTER BY (key)" in j
    h = deploy.hook_runs_table_sql(T)
    for col in ["invocation_id STRING", "tested BIGINT", "missing BIGINT", "oversized BIGINT",
                "inserted BIGINT"]:
        assert col in h
    v = deploy.requests_view_sql(T)
    assert v.startswith("CREATE OR REPLACE VIEW jev_demo.jev.requests")
    assert "GROUP BY pack_uuid" in v


def test_platform_order():
    labels = [label for label, _ in deploy.platform_statements(T)]
    assert labels == ["schema", "judgments", "hook_runs", "requests", "noul_pack_demo", "noul_pack"]


def test_production_statements():
    labels = [label for label, _ in deploy.production_statements()]
    assert labels == ["production schema", "raw volume"]


def test_rejects_unsafe_identifiers():
    with pytest.raises(ValueError):
        deploy.Target(catalog="jev_demo; drop")
