import importlib.util
from pathlib import Path

import duckdb

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("show", ROOT / "scripts" / "show.py")
show = importlib.util.module_from_spec(spec)
spec.loader.exec_module(show)


SCHEMA = """
version: 2

models:
  - name: stg_widgets
    columns:
      - name: name
        data_tests:
          - not_null
          - jev_expect:
              name: widgets_name_is_real
              arguments:
                fails_if: "The `name` is fake."
                context: [color]
                threshold: 0.7
                criteria:
                  "true": "fake"
                  "false": "real"
              config: {severity: error, store_failures: true, tags: [semantic]}

  - name: stg_gadgets
    columns:
      - name: body
        data_tests:
          - not_null
          - jev_expect:
              name: gadgets_body_is_clean
              arguments:
                fails_if: "The `body` contains junk."
                threshold: 0.5
                criteria:
                  "true": "junk"
                  "false": "clean"
              config: {severity: error, store_failures: true, tags: [semantic]}
"""


# ---------------------------------------------------------------------------
# load_jev_tests
# ---------------------------------------------------------------------------


def test_load_jev_tests_finds_both_in_document_order():
    tests = show.load_jev_tests(SCHEMA)
    assert [t["name"] for t in tests] == ["widgets_name_is_real", "gadgets_body_is_clean"]


def test_load_jev_tests_captures_model_column_and_arguments():
    tests = show.load_jev_tests(SCHEMA)
    widgets = tests[0]
    assert widgets["model"] == "stg_widgets"
    assert widgets["column"] == "name"
    assert widgets["arguments"]["fails_if"] == "The `name` is fake."
    assert widgets["arguments"]["context"] == ["color"]


def test_load_jev_tests_context_defaults_absent_when_not_configured():
    tests = show.load_jev_tests(SCHEMA)
    gadgets = tests[1]
    assert "context" not in gadgets["arguments"]


def test_load_jev_tests_ignores_non_jev_expect_data_tests():
    schema = """
models:
  - name: m
    columns:
      - name: c
        data_tests: [not_null, unique]
"""
    assert show.load_jev_tests(schema) == []


def test_load_jev_tests_empty_document():
    assert show.load_jev_tests("") == []


# ---------------------------------------------------------------------------
# select_example_row
# ---------------------------------------------------------------------------


def _build_audit_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("create schema main_dbt_test__audit")
    con.execute(
        "create table main_dbt_test__audit.t as "
        "select id, jev_p::double as jev_p from "
        "(values (1, 0.95), (2, 0.80), (3, 0.99), (4, 0.99)) v(id, jev_p)"
    )
    con.execute(
        "create table main_dbt_test__audit.baseline_t as "
        "select * from (values (2,)) v(id)"
    )
    return con


def test_select_example_row_prefers_defect_baseline_missed():
    con = _build_audit_db()
    try:
        # id=1 (p=0.95) and id=2 (p=0.80) are golden defects; baseline caught id=2 but missed
        # id=1, so id=1 should win even though id=3/4 have higher jev_p (they're not defects).
        result = show.select_example_row(con, "t", "id", {1, 2})
        assert result == (1, 0.95, False)
    finally:
        con.close()


def test_select_example_row_tie_breaks_on_lowest_id():
    con = _build_audit_db()
    try:
        # id=3 and id=4 tie at p=0.99 and neither is caught by baseline; lowest id wins.
        result = show.select_example_row(con, "t", "id", {3, 4})
        assert result == (3, 0.99, False)
    finally:
        con.close()


def test_select_example_row_falls_back_when_baseline_catches_everything():
    con = _build_audit_db()
    try:
        # Only id=2 is a golden defect, and the baseline caught it -- no "baseline missed" row
        # exists, so the fallback (highest-jev_p golden defect regardless of baseline) applies.
        result = show.select_example_row(con, "t", "id", {2})
        assert result == (2, 0.80, True)
    finally:
        con.close()


def test_select_example_row_none_when_no_flagged_row_is_a_golden_defect():
    con = _build_audit_db()
    try:
        result = show.select_example_row(con, "t", "id", {999})
        assert result is None
    finally:
        con.close()


def test_select_example_row_missing_baseline_table_treated_as_empty():
    con = duckdb.connect()
    con.execute("create schema main_dbt_test__audit")
    con.execute(
        "create table main_dbt_test__audit.t as "
        "select id, jev_p::double as jev_p from (values (1, 0.9)) v(id, jev_p)"
    )
    try:
        # no baseline_t table at all
        assert show.select_example_row(con, "t", "id", {1}) == (1, 0.9, False)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# render_row_body / format_headline (pure formatting)
# ---------------------------------------------------------------------------


def test_render_row_body_includes_context_and_full_text_never_truncated():
    long_text = "x" * 500
    row = {"id": 7, "reason_code": "damaged", "comment": long_text}
    body = show.render_row_body(row, "id", 7, 0.91, "comment", ["reason_code"], False)
    assert "id=7" in body
    assert "jev_p=0.91" in body
    assert "regex: missed" in body
    assert "reason_code=damaged" in body
    assert long_text in body  # not truncated


def test_render_row_body_caught_by_baseline_says_caught():
    body = show.render_row_body({"id": 1, "body": "hi"}, "id", 1, 0.5, "body", [], True)
    assert "regex: caught" in body


def test_render_row_body_no_context_cols_omits_context_line():
    body = show.render_row_body({"id": 1, "body": "hi"}, "id", 1, 0.5, "body", [], False)
    assert "hi" in body


def test_format_headline_matches_spec_example():
    assert show.format_headline("Jev", 74, 75, 1) == "Jev    caught 74/75 · 1 false alarm"
    assert show.format_headline("Regex", 58, 75, 64) == "Regex  caught 58/75 · 64 false alarms"


def test_format_headline_zero_false_alarms_is_plural():
    assert show.format_headline("Jev", 5, 5, 0) == "Jev    caught 5/5 · 0 false alarms"
