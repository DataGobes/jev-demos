"""scripts/deploy.py: --only validation and the --smoke call (offline: a fake Sql)."""

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

from jevdbx import deploy
from jevdbx.databricks import Result

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("deploy_cli", ROOT / "scripts" / "deploy.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class FakeSql:
    def __init__(self, result):
        self.result, self.seen = result, []

    def run(self, sql, timeout_s=900):
        self.seen.append(sql)
        return self.result


@pytest.fixture
def fake_sql(monkeypatch):
    holder = {}

    def make(result=None):
        sql = FakeSql(result or Result("SUCCEEDED", wall_s=0.1))
        holder["sql"] = sql
        monkeypatch.setattr(cli, "Sql", lambda: sql)
        return sql

    return make


# -- --only ------------------------------------------------------------------------------------


def test_only_with_an_unknown_label_lists_the_valid_labels_and_fails(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--apply", "--only", "noul_pak"])
    assert e.value.code != 0
    err = capsys.readouterr().err
    assert "noul_pak" in err
    for label in ("schema", "judgments", "hook_runs", "requests", "noul_pack_demo", "noul_pack"):
        assert label in err


def test_only_unknown_label_is_rejected_before_connecting(monkeypatch):
    monkeypatch.setattr(cli, "Sql", lambda: pytest.fail("connected"))
    with pytest.raises(SystemExit):
        cli.main(["--only", "schema", "nope"])


def test_only_production_labels_are_checked_against_the_production_statements(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--production", "--only", "schema"])
    assert "production schema" in capsys.readouterr().err


def test_only_with_known_labels_prints_just_those(capsys):
    assert cli.main(["--only", "hook_runs"]) == 0
    out = capsys.readouterr().out
    assert "-- hook_runs" in out and "-- judgments" not in out


# -- --smoke -----------------------------------------------------------------------------------


def _unquote(literal: str) -> str:
    """A Databricks SQL string literal ('...' with \\' and \\\\ escapes) back to its value."""
    assert literal[0] == literal[-1] == "'"
    return re.sub(r"\\(.)", r"\1", literal[1:-1])


LITERAL = r"'(?:[^'\\]|\\.)*'"


def test_smoke_sql_is_one_two_row_call_of_the_live_function():
    sql = deploy.smoke_sql(deploy.Target())
    assert sql.startswith("SELECT jev_demo.jev.noul_pack(array(")
    assert sql.count("noul_pack(") == 1 and "noul_pack_demo" not in sql
    literals = [_unquote(m) for m in re.findall(LITERAL, sql)]
    records, question, model = literals[:2], literals[2], literals[3]
    assert len(literals) == 4
    assert [json.loads(r) for r in records] == [json.loads(r) for r in deploy.SMOKE_RECORDS]
    assert set(json.loads(question)) == {"instructions", "criteria"}
    assert model == deploy.SMOKE_MODEL
    for leak in ("secret", "typesafe_api_key", "Bearer", "SECRETS"):
        assert leak not in sql


def test_smoke_model_is_the_pinned_dbt_model():
    vars_ = yaml.safe_load((ROOT / "jaffle_shop/dbt_project.yml").read_text())["vars"]
    assert deploy.SMOKE_MODEL == vars_["jev_model"]


def test_smoke_sql_escapes_quotes_and_backslashes():
    lit = deploy.sql_string("it's a \\ test")
    assert lit == "'it\\'s a \\\\ test'" and _unquote(lit) == "it's a \\ test"


def test_smoke_runs_the_statement_and_prints_values_tokens_model_error(fake_sql, capsys):
    payload = {"values": [0.93, 0.04], "input_tokens": 480, "model": "jev-1.13.0",
               "error": None, "attempts": 1, "retries": []}
    sql = fake_sql(Result("SUCCEEDED", rows=[[json.dumps(payload)]], wall_s=21.0))
    assert cli.main(["--smoke"]) == 0
    assert sql.seen == [deploy.smoke_sql(deploy.Target())]
    out = capsys.readouterr().out
    assert "LIVE" in out and "[0.93, 0.04]" in out and "480" in out and "jev-1.13.0" in out
    assert "error: None" in out


def test_smoke_reports_a_failed_call(fake_sql, capsys):
    payload = {"values": None, "input_tokens": 0, "model": None,
               "error": "HTTP 401: [redacted]", "attempts": 1, "retries": []}
    fake_sql(Result("SUCCEEDED", rows=[[json.dumps(payload)]]))
    assert cli.main(["--smoke"]) == 1
    assert "HTTP 401" in capsys.readouterr().out


def test_smoke_reports_a_failed_statement(fake_sql, capsys):
    fake_sql(Result("FAILED", error="UNRESOLVED_ROUTINE"))
    assert cli.main(["--smoke"]) == 1
    assert "UNRESOLVED_ROUTINE" in capsys.readouterr().out


def test_smoke_demo_calls_the_simulated_twin(fake_sql, capsys):
    payload = {"values": [0.1, 0.2], "input_tokens": 60, "model": "demo:jev-1.13.0",
               "error": None, "attempts": 1, "retries": []}
    sql = fake_sql(Result("SUCCEEDED", rows=[[json.dumps(payload)]]))
    assert cli.main(["--smoke", "--demo"]) == 0
    assert "jev_demo.jev.noul_pack_demo(" in sql.seen[0]
    assert "SIMULATED" in capsys.readouterr().out


@pytest.mark.parametrize("extra", [["--apply"], ["--only", "schema"], ["--production"]])
def test_smoke_is_not_combined_with_ddl_flags(extra):
    with pytest.raises(SystemExit) as e:
        cli.main(["--smoke", *extra])
    assert e.value.code == 2


def test_demo_needs_smoke():
    with pytest.raises(SystemExit) as e:
        cli.main(["--demo"])
    assert e.value.code == 2
