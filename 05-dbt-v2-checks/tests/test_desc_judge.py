from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

import duckdb
from conftest import PROJECT, write_info_schema

from desc_judge.cache import VerdictCache
from desc_judge.cli import main
from desc_judge.facts import load_column_facts
from desc_judge.judges import ColumnFacts, MockJudge, Verdict
from desc_judge.runner import evaluate

WRONG = {
    ("model.desc_checks.stg_customers", "last_name"),
    ("model.desc_checks.stg_orders", "order_total"),
    ("model.desc_checks.customer_orders", "order_count"),
    ("model.desc_checks.fct_revenue", "revenue_date"),
}
SUBTLE = ("model.desc_checks.customer_orders", "first_order_date")


class CountingJudge:
    """MockJudge's verdicts, counting what is actually sent to it."""

    def __init__(self, id: str = "counting-v1"):
        self.id = id
        self.sent: list[ColumnFacts] = []

    def judge(self, items: Sequence[ColumnFacts]) -> list[Verdict]:
        self.sent.extend(items)
        return MockJudge().judge(items)


def failures(report) -> set[tuple[str, str]]:
    return {(f.unique_id, f.column_name) for f in report.failures}


def test_mock_judge_flags_the_wrong_descriptions_and_misses_the_subtle_one(info_schema):
    report = evaluate(load_column_facts(info_schema), MockJudge(), VerdictCache(None))
    assert failures(report) == WRONG
    assert SUBTLE not in failures(report)  # a keyword rule cannot see it; the reason Jev exists
    assert report.undocumented == 1  # fct_revenue.order_count


def test_unchanged_columns_are_never_judged_twice(info_schema, tmp_path):
    cache_path = tmp_path / "cache.json"
    facts = load_column_facts(info_schema)

    first = CountingJudge()
    evaluate(facts, first, cache := VerdictCache(cache_path))
    cache.save()
    assert len(first.sent) == 16  # 17 columns, one undocumented

    second = CountingJudge()
    report = evaluate(facts, second, VerdictCache(cache_path))
    assert second.sent == [] and report.cached == 16 and failures(report) == WRONG


def test_a_description_edit_re_judges_only_that_column(tmp_path, rows):
    cache_path = tmp_path / "cache.json"
    before = load_column_facts(write_info_schema(tmp_path / "a", rows))
    evaluate(before, CountingJudge(), cache := VerdictCache(cache_path))
    cache.save()

    edited = [dict(r) for r in rows]
    for r in edited:
        if r["column_name"] == "order_total":
            r["description"] = "Total amount of the order"
    after = load_column_facts(write_info_schema(tmp_path / "b", edited))

    judge = CountingJudge()
    report = evaluate(after, judge, VerdictCache(cache_path))
    assert [f.column_name for f in judge.sent] == ["order_total"]
    assert ("model.desc_checks.stg_orders", "order_total") not in failures(report)


def test_state_limits_the_run_to_changed_columns(tmp_path, rows):
    baseline = load_column_facts(write_info_schema(tmp_path / "prod", rows))
    edited = [dict(r) for r in rows]
    edited[0]["description"] = "Customer shoe size"  # stg_customers.customer_id, now wrong
    current = load_column_facts(write_info_schema(tmp_path / "dev", edited))

    report = evaluate(current, MockJudge(), VerdictCache(None), baseline=baseline)
    assert report.in_scope == 1 and report.unchanged == 16
    # Pre-existing failures are out of scope: this run answers for what changed.
    assert failures(report) == {("model.desc_checks.stg_customers", "customer_id")}


def test_a_new_judge_never_reuses_another_judges_verdicts(info_schema, tmp_path):
    cache_path = tmp_path / "cache.json"
    facts = load_column_facts(info_schema)
    evaluate(facts, CountingJudge("mock-a"), cache := VerdictCache(cache_path))
    cache.save()
    swapped = CountingJudge("jev-b")
    evaluate(facts, swapped, VerdictCache(cache_path))
    assert len(swapped.sent) == 16


def test_identical_columns_are_sent_once_per_run(tmp_path, rows):
    twin = [dict(r, unique_id="model.desc_checks.copy", model="copy") for r in rows if r["model"] == "stg_orders"]
    facts = load_column_facts(write_info_schema(tmp_path / "t", rows + twin))
    judge = CountingJudge()
    report = evaluate(facts, judge, VerdictCache(None))
    assert len(judge.sent) == 16 and report.in_scope == 21
    assert ("model.desc_checks.copy", "order_total") in failures(report)


def test_a_parse_only_schema_falls_back_to_raw_sql_and_declared_types(tmp_path, rows):
    facts = load_column_facts(write_info_schema(tmp_path / "p", rows, compiled=False))
    by_col = {(f.unique_id, f.column_name): f for f in facts}
    f = by_col[("model.desc_checks.stg_orders", "order_total")]
    assert f.data_type == "decimal(10,2)" and "order_total" in f.sql


def test_cli_is_check_shaped(info_schema, tmp_path, capsys):
    cache = str(tmp_path / "c.json")
    assert main(["--info-schema", str(info_schema), "--cache", cache]) == 1
    out = capsys.readouterr().out
    assert out.startswith("FAIL description_matches_column (4 violations)")

    assert main(["--info-schema", str(info_schema), "--cache", cache, "--warn", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["violations"] == 4 and payload["stats"]["judged"] == 0 and payload["stats"]["cached"] == 16

    clean = ["--select", "model.desc_checks.stg_orders", "--info-schema", str(info_schema), "--no-cache"]
    assert main(clean) == 1  # order_total
    assert main(["--select", "model.desc_checks.fct_revenue_nope", "--info-schema", str(info_schema)]) == 0


def test_the_sql_macro_in_the_native_check_agrees_with_the_python_mock(rows):
    """checks/description_matches_column_macro.sql must judge exactly like MockJudge (name only)."""
    check = (PROJECT / "checks/description_matches_column_macro.sql").read_text()
    create_macro = re.search(r"create or replace temp macro.*?\);\n", check, re.DOTALL).group(0)
    con = duckdb.connect()
    con.execute(create_macro)
    for r in rows:
        if not r["description"]:
            continue
        sql_says = con.execute("select mock_judge(?, ?)", [r["column_name"], r["description"]]).fetchone()[0]
        py_says = MockJudge().judge([ColumnFacts("", r["column_name"], None, r["description"], None)])[0].ok
        assert sql_says == py_says, r


def test_the_jinja_macro_judges_like_the_python_mock(rows):
    """macros/mock_judge.sql, rendered, must judge exactly like MockJudge (name only)."""
    import jinja2

    env = jinja2.Environment()
    macros = env.from_string((PROJECT / "macros/mock_judge.sql").read_text()).module
    expr = str(macros.mock_judge_matches("column_name", "description"))
    con = duckdb.connect()
    for r in rows:
        if not r["description"]:
            continue
        sql_says = con.execute(
            f"select {expr} from (select ? as column_name, ? as description)", [r["column_name"], r["description"]]
        ).fetchone()[0]
        py_says = MockJudge().judge([ColumnFacts("", r["column_name"], None, r["description"], None)])[0].ok
        assert sql_says == py_says, r


def test_the_probes_still_exist():
    probes = Path(__file__).parent.parent / "probes"
    assert {p.name for p in probes.glob("probe_*.py")} >= {"probe_adbc.py", "probe_ext.py"}
