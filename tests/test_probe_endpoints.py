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
