import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from jevdbx import databricks


class FakeStatements:
    def __init__(self, states, rows=None):
        self.states = list(states)
        self.rows = rows or [["1"]]
        self.executed = []

    def _resp(self, state):
        return NS(statement_id="s1", status=NS(state=NS(value=state), error=None),
                  manifest=NS(schema=NS(columns=[NS(name="n")]), total_chunk_count=1),
                  result=NS(data_array=self.rows, next_chunk_index=None))

    def execute_statement(self, **kw):
        self.executed.append(kw)
        return self._resp(self.states.pop(0))

    def get_statement(self, statement_id):
        return self._resp(self.states.pop(0))


def test_run_polls_until_done(monkeypatch):
    fake = FakeStatements(["RUNNING", "RUNNING", "SUCCEEDED"])
    client = NS(statement_execution=fake)
    monkeypatch.setattr(databricks.time, "sleep", lambda s: None)
    sql = databricks.Sql(client=client, warehouse_id="w1")
    res = sql.run("select 1")
    assert res.state == "SUCCEEDED" and res.columns == ["n"] and res.rows == [["1"]]
    assert fake.executed[0]["warehouse_id"] == "w1" and fake.executed[0]["statement"] == "select 1"


def test_resolve_warehouse_by_name():
    client = NS(warehouses=NS(list=lambda: [NS(id="abc", name="jev-demo-5"), NS(id="x", name="o")]))
    assert databricks.resolve_warehouse_id(client, "jev-demo-5") == "abc"
    assert databricks.resolve_warehouse_id(client, "abc") == "abc"


def _client(headers, host="https://adb-1.azuredatabricks.net/"):
    return NS(
        config=NS(host=host, authenticate=lambda: headers),
        warehouses=NS(list=lambda: [NS(id="wid9", name="jev-demo-5")]),
    )


def test_dbt_env_returns_host_path_and_token(monkeypatch):
    monkeypatch.delenv("JEV_WAREHOUSE", raising=False)
    env = databricks.dbt_env(client=_client({"Authorization": "Bearer tok-123"}))
    assert env == {
        "DATABRICKS_HOST": "adb-1.azuredatabricks.net",
        "JEV_HTTP_PATH": "/sql/1.0/warehouses/wid9",
        "DBT_ENV_SECRET_DATABRICKS_TOKEN": "tok-123",
    }


def test_dbt_env_uses_warehouse_argument(monkeypatch):
    monkeypatch.setenv("JEV_WAREHOUSE", "nonexistent")
    client = _client({"Authorization": "Bearer t"})
    client.warehouses = NS(list=lambda: [NS(id="p1", name="jev-demo-5-prod")])
    env = databricks.dbt_env(warehouse="jev-demo-5-prod", client=client)
    assert env["JEV_HTTP_PATH"] == "/sql/1.0/warehouses/p1"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic SECRETVALUE"}])
def test_dbt_env_without_bearer_raises_without_leaking(headers):
    with pytest.raises(RuntimeError) as exc:
        databricks.dbt_env(client=_client(headers))
    assert "SECRETVALUE" not in str(exc.value) and "Basic" not in str(exc.value)


_spec = importlib.util.spec_from_file_location(
    "dbtw", Path(__file__).parents[1] / "scripts" / "dbtw.py")
dbtw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbtw)


def test_build_command_adds_defaults():
    assert dbtw.build_command(["build", "--select", "+tag:semantic"]) == [
        "build", "--select", "+tag:semantic", "--profiles-dir", ".", "--target", "dev"]


def test_build_command_respects_given_flags():
    assert dbtw.build_command(["test", "--profiles-dir", "p", "--target=prod"]) == [
        "test", "--profiles-dir", "p", "--target=prod"]
    assert dbtw.build_command(["run", "--profiles-dir=p", "--target", "prod"]) == [
        "run", "--profiles-dir=p", "--target", "prod"]
