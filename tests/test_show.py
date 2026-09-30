import importlib.util
from pathlib import Path

import pytest

from jevdbx.databricks import Result

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
# select_example_row (reads stored failures through Sql.run; here a fake)
# ---------------------------------------------------------------------------


class FakeSql:
    """Answers Sql.run by the first key that appears in the statement."""

    def __init__(self, answers):
        self.answers, self.seen = answers, []

    def run(self, sql, timeout_s=900):
        self.seen.append(sql)
        for key, res in self.answers.items():
            if key in sql:
                return res
        raise AssertionError(f"unexpected statement: {sql[:120]}")


AUDIT = "jev_demo.jaffle_shop_dbt_test__audit"
MISSING = Result("FAILED", error="[TABLE_OR_VIEW_NOT_FOUND] The table or view cannot be found")


def audit_sql(baseline_ids=(2,), jev=None):
    # Databricks' Statement API returns every value as a string
    jev = jev if jev is not None else [(1, 0.95), (2, 0.80), (3, 0.99), (4, 0.99)]
    return FakeSql({
        f"{AUDIT}.baseline_t": Result("SUCCEEDED", rows=[[str(i)] for i in baseline_ids]),
        f"{AUDIT}.t ": Result("SUCCEEDED", rows=[[str(i), str(p)] for i, p in jev]),
    })


def test_select_example_row_prefers_defect_baseline_missed():
    # id=1 (p=0.95) and id=2 (p=0.80) are golden defects; baseline caught id=2 but missed
    # id=1, so id=1 should win even though id=3/4 have higher jev_p (they're not defects).
    assert show.select_example_row(audit_sql(), "t", "id", {1, 2}) == (1, 0.95, False)


def test_select_example_row_tie_breaks_on_lowest_id():
    # id=3 and id=4 tie at p=0.99 and neither is caught by baseline; lowest id wins.
    assert show.select_example_row(audit_sql(), "t", "id", {3, 4}) == (3, 0.99, False)


def test_select_example_row_falls_back_when_baseline_catches_everything():
    # Only id=2 is a golden defect, and the baseline caught it -- no "baseline missed" row
    # exists, so the fallback (highest-jev_p golden defect regardless of baseline) applies.
    assert show.select_example_row(audit_sql(), "t", "id", {2}) == (2, 0.80, True)


def test_select_example_row_none_when_no_flagged_row_is_a_golden_defect():
    assert show.select_example_row(audit_sql(), "t", "id", {999}) is None


def test_select_example_row_missing_baseline_table_treated_as_empty():
    sql = FakeSql({
        f"{AUDIT}.baseline_t": MISSING,
        f"{AUDIT}.t ": Result("SUCCEEDED", rows=[["1", "0.9"]]),
    })
    assert show.select_example_row(sql, "t", "id", {1}) == (1, 0.9, False)


def test_select_example_row_reads_judged_rows_only():
    sql = audit_sql()
    show.select_example_row(sql, "t", "id", {1})
    jev_query = next(q for q in sql.seen if ".baseline_" not in q)
    assert "jev_p is not null" in jev_query


def test_select_example_row_missing_jev_table_says_no_stored_failures():
    sql = FakeSql({f"{AUDIT}.t ": MISSING})
    with pytest.raises(show.NoStoredFailures):
        show.select_example_row(sql, "t", "id", {1})


def test_select_example_row_other_errors_are_not_swallowed():
    sql = FakeSql({f"{AUDIT}.t ": Result("FAILED", error="PERMISSION_DENIED")})
    with pytest.raises(RuntimeError, match="PERMISSION_DENIED"):
        show.select_example_row(sql, "t", "id", {1})


def test_fetch_row_returns_a_dict_by_column():
    sql = FakeSql({f"{AUDIT}.t where": Result(
        "SUCCEEDED", columns=["id", "comment", "jev_p"], rows=[["7", "it broke", "0.91"]])})
    row = show.fetch_row(sql, "t", "id", 7)
    assert row == {"id": "7", "comment": "it broke", "jev_p": "0.91"}
    assert "where id = 7" in sql.seen[0]


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


def test_shipped_schema_has_the_four_yardstick_tests_and_score_knows_their_ids():
    tests = show.load_jev_tests(show.SCHEMA_PATH.read_text())
    assert {t["name"] for t in tests} == set(show.score.TESTS)
    assert show.FEATURED_TEST in show.score.TESTS
    assert set(show.SHORT_NAMES) == set(show.score.TESTS)


def test_current_run_does_not_show_a_partial_invocation_as_the_scored_run(monkeypatch):
    monkeypatch.setattr(show.score, "load_budget", lambda: 48_000)
    sql = FakeSql({
        "order by recorded_at desc limit 1": Result("SUCCEEDED", rows=[["inv"]]),
        "from jev_demo.jev.hook_runs": Result("SUCCEEDED", rows=[
            ["3", "10", "10", "10", "0", "live", "jev-1.13.0"]]),
    })
    assert show.current_run(sql) is None
    assert "SIMULATED" in show.score.simulated_banner(show.current_run(sql))


DESCRIBE_ROWS = [
    "Function:        jev_demo.jev.noul_pack_demo",
    "Input:           records  ARRAY<STRING>\n                 question STRING       ",
    "                 question STRING       ",
    "                 model    STRING       ",
    "Returns:         STRING",
    "Comment:         SIMULATED stand-in for noul_pack.",
    "Deterministic:   false",
    "Configs:         spark.sql.ansi.enabled=false",
    "                 spark.sql.session.timeZone=Etc/UTC",
    "Owner:           someone@example.com",
    "Create Time:     Wed Sep 30 20:19:27 UTC 2026",
    'Body:            \n"""Body of the function: def handler(x): return x"""',
    "Language:        Python",
    "Parameter Style: Scalar",
]


def test_describe_lines_keep_the_contract_and_drop_owner_configs_and_body():
    text = "\n".join(show.describe_lines(DESCRIBE_ROWS))
    assert "Function:" in text and "model    STRING" in text and "Language:        Python" in text
    for dropped in ("someone@example.com", "spark.sql", "Create Time", "Body", "handler"):
        assert dropped not in text


def test_function_name_follows_the_mode(monkeypatch):
    monkeypatch.delenv("JEV_MODE", raising=False)
    assert show.function_name() == "jev_demo.jev.noul_pack"
    assert show.function_name("demo") == "jev_demo.jev.noul_pack_demo"
    monkeypatch.setenv("JEV_MODE", "demo")
    assert show.function_name() == "jev_demo.jev.noul_pack_demo"


def test_render_function_prints_the_statement_and_the_kept_lines():
    from io import StringIO

    from rich.console import Console

    sql = FakeSql({"DESCRIBE FUNCTION EXTENDED": Result(
        "SUCCEEDED", rows=[[r] for r in DESCRIBE_ROWS])})
    out = StringIO()
    assert show.render_function(Console(file=out, width=90), sql, "jev_demo.jev.x") == 0
    text = out.getvalue()
    assert "> DESCRIBE FUNCTION EXTENDED jev_demo.jev.x" in text
    assert "someone@example.com" not in text


def test_render_function_reports_a_missing_function():
    from io import StringIO

    from rich.console import Console

    sql = FakeSql({"DESCRIBE FUNCTION": Result("FAILED", error="UNRESOLVED_ROUTINE")})
    out = StringIO()
    assert show.render_function(Console(file=out, width=90), sql, "jev_demo.jev.x") == 1
    assert "UNRESOLVED_ROUTINE" in out.getvalue()


def test_show_never_puts_a_live_banner_over_stale_stored_failures(monkeypatch):
    # F5: the latest invocation is a complete LIVE run, but the stored failures were written by
    # another invocation (e.g. an older build, or a SIMULATED one): no LIVE provenance is shown.
    monkeypatch.setattr(show.score, "load_budget", lambda: 48_000)
    sql = FakeSql({
        "order by recorded_at desc limit 1": Result("SUCCEEDED", rows=[["inv"]]),
        "from jev_demo.jev.hook_runs": Result("SUCCEEDED", rows=[
            ["4", "10", "10", "10", "0", "live", "jev-1.13.0"]]),
        "from jev_demo.jev.requests": Result("SUCCEEDED", rows=[
            ["1", "100", "90", "10", "0", "0", "0", "1.0", "jev-1.13.0"]]),
        "from jev_demo.jev.judgments where invocation_id": Result("SUCCEEDED", rows=[["0", "0"]]),
        "is distinct from": Result("SUCCEEDED", rows=[["5", "5"]]),
    })
    run = show.current_run(sql)
    assert run is None
    banner = show.score.simulated_banner(run)
    assert banner is not None and "LIVE" not in banner
