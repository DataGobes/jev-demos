import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jevviz.api import create_app
from jevviz.backend import DemoBackend
from jevviz.data import generate
from jevviz.types import JudgeResult

TREND = "SELECT date_trunc('month', order_date) AS m, region, sum(revenue) AS revenue FROM orders GROUP BY ALL"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("d") / "api.duckdb"
    generate(path, n_orders=6_000)
    return path


def run(client, sql):
    resp = client.post("/run", json={"sql": sql})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in resp.text.splitlines() if line]


def test_full_stream_order_and_payload(db):
    events = run(TestClient(create_app(db, DemoBackend())), TREND + " VISUALIZE 'how are regions trending'")
    assert [e["type"] for e in events] == ["parsed", "result", "spec"]
    parsed, result, spec = events
    assert parsed["intents"] == ["how are regions trending"] and "VISUALIZE" not in parsed["sql"]
    assert result["columns"] == ["m", "region", "revenue"] and isinstance(result["rows"][0], dict)
    assert "query" in result["ms"] and result["truncated"] is False
    assert spec["simulated"] is True and spec["spec"]["root"] == "grid"
    assert {"profile", "enumerate", "jev"} <= set(spec["ms"]) and "usd" in spec["usage"]


def test_no_clause_ends_after_result(db):
    events = run(TestClient(create_app(db, DemoBackend())), "SELECT 1 AS x")
    assert [e["type"] for e in events] == ["parsed", "result"] and events[0]["intents"] is None


def test_sql_error_is_a_query_stage_error(db):
    events = run(TestClient(create_app(db, DemoBackend())), "SELEKT 1 VISUALIZE 'x'")
    assert [e["type"] for e in events] == ["parsed", "error"] and events[1]["stage"] == "query"


def test_parse_error_is_a_parse_stage_error(db):
    events = run(TestClient(create_app(db, DemoBackend())), "SELECT 1 VISUALIZE 'a' LIMIT 1")
    assert events == [{"type": "error", "stage": "parse", "message": events[0]["message"]}]


def test_viz_failure_keeps_the_data(db):
    class Broken(DemoBackend):
        async def judge(self, state, questions):
            return JudgeResult({}, 0, "OverloadedError: 529")

    events = run(TestClient(create_app(db, Broken())), TREND + " VISUALIZE 'x'")
    assert [e["type"] for e in events] == ["parsed", "result", "spec", "error"]
    assert events[2]["panels"][0]["chosen"]["kind"] == "table" and events[3]["stage"] == "jev"


def test_dates_are_json_serialised(db):
    events = run(TestClient(create_app(db, DemoBackend())), "SELECT order_date FROM orders LIMIT 1")
    assert isinstance(events[1]["rows"][0]["order_date"], str)


def test_duplicate_result_columns_are_unique_and_keep_all_values(db):
    events = run(TestClient(create_app(db, DemoBackend())), "SELECT 1 AS id, 2 AS id")
    result = events[1]
    assert len(result["columns"]) == len(set(result["columns"])) == 2
    assert sorted(result["rows"][0].values()) == [1, 2]


def test_connection_is_shared_across_path_spellings(db):
    abs_path = str(db.resolve())
    alt_path = str(db.parent) + "/./" + db.name

    run(TestClient(create_app(abs_path, DemoBackend())), "SELECT 1 AS x")
    events = run(TestClient(create_app(alt_path, DemoBackend())), "SELECT 1 AS x")

    assert [e["type"] for e in events] == ["parsed", "result"]
    assert Path(alt_path).resolve() == Path(abs_path).resolve()
