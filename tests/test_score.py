import importlib.util
import json
from pathlib import Path

import pytest

from jevdbx.databricks import Result

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("score", ROOT / "scripts" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

GOLD = {1: "defect", 2: "defect", 3: "hard_negative", 4: "defect"}


def live_run(**kw):
    return score.Run(mode="live", answered_model="jev-1.13.0", requested_model="jev-1.13.0", **kw)


# -- metrics / golden --------------------------------------------------------------------------


def test_metrics():
    m = score.metrics({1, 2, 3, 9}, GOLD)
    assert (m.flagged, m.tp, m.fp, m.fn, m.hard_neg_flagged) == (4, 2, 2, 1, 1)
    assert m.precision == 0.5 and round(m.recall, 3) == 0.667


def test_metrics_nothing_flagged():
    m = score.metrics(set(), GOLD)
    assert (m.precision, m.recall, m.f1) == (0.0, 0.0, 0.0)


def test_load_golden_groups_by_test(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("test_name,id,label,note\nt1,1,defect,x\nt1,2,hard_negative,y\nt2,7,defect,z\n")
    assert score.load_golden(p) == {"t1": {1: "defect", 2: "hard_negative"}, "t2": {7: "defect"}}


def test_shipped_golden_key_covers_the_four_yardstick_tests():
    golden = score.load_golden(ROOT / "eval" / "golden_defects.csv")
    assert set(golden) == set(score.TESTS)


# -- wilson / audited precision ----------------------------------------------------------------


def test_wilson_8_of_10():
    lo, hi = score.wilson(8, 10)
    assert round(lo, 2) == 0.49 and round(hi, 2) == 0.94


def test_wilson_edges():
    assert score.wilson(0, 0) == (0.0, 1.0)
    lo, hi = score.wilson(10, 10)
    assert hi == pytest.approx(1.0) and 0.6 < lo < 0.75
    lo, hi = score.wilson(0, 10)
    assert lo == pytest.approx(0.0) and 0.25 < hi < 0.4


AUDIT = {i: "real" for i in range(40)} | {i: "ok" for i in range(100, 110)}


def test_audited_precision_extrapolates_the_sample_share():
    point, lo, hi = score.audited_precision(90, 50, AUDIT)
    assert point == pytest.approx((90 + 40) / (90 + 50))  # 0.929
    assert lo < point < hi <= 1.0
    # the interval is Wilson(40, 50) on the unplanted flags, scaled to all flags
    wlo, whi = score.wilson(40, 50)
    assert lo == pytest.approx((90 + wlo * 50) / 140) and hi == pytest.approx((90 + whi * 50) / 140)


def test_audited_precision_no_unplanted_flags_is_raw_precision():
    assert score.audited_precision(90, 0, AUDIT) == (1.0, 1.0, 1.0)


def test_audited_precision_nothing_flagged():
    assert score.audited_precision(0, 0, {}) == (0.0, 0.0, 0.0)


def test_audited_precision_needs_labels_when_unplanted_flags_exist():
    with pytest.raises(ValueError, match="audit"):
        score.audited_precision(90, 50, {})


def test_audited_precision_rejects_unknown_labels():
    with pytest.raises(ValueError, match="label"):
        score.audited_precision(1, 1, {5: "maybe"})


# -- gate --------------------------------------------------------------------------------------


def test_gate():
    good = score.metrics({1, 2, 4}, GOLD)
    weak = score.metrics({1}, GOLD)
    ok, reasons = score.gate({"t": (good, weak)}, live_run())
    assert ok and reasons == []
    ok, reasons = score.gate({"t": (good, weak)}, score.Run(mode="demo"))
    assert not ok and "run was not LIVE" in reasons
    ok, reasons = score.gate({"t": (weak, good)}, live_run())
    assert not ok and any("recall" in r for r in reasons)
    assert any("f1" in r and "does not beat baseline" in r for r in reasons)
    ok, reasons = score.gate({"t": (good, weak)}, live_run(error_packs=2))
    assert not ok and "run reported errors" in reasons


def test_gate_messages_match_demo04_wording():
    weak = score.metrics({1, 9}, GOLD)  # p=0.5 r=0.333
    ok, reasons = score.gate({"t": (weak, weak)}, live_run())
    assert "t: Jev precision 0.50 < 0.85" in reasons
    assert "t: Jev recall 0.33 < 0.85" in reasons
    assert "t: Jev f1 0.40 does not beat baseline f1 0.40" in reasons
    ok, reasons = score.gate({}, None)
    assert not ok and reasons == ["summary not captured (run with --run)"]


def test_gate_unjudged_rows_count_as_errors():
    good = score.metrics({1, 2, 4}, GOLD)
    ok, reasons = score.gate({"t": (good, good)}, live_run(unjudged=3))
    assert "run reported errors" in reasons


def test_gate_fails_when_once_per_row_is_violated():
    good = score.metrics({1, 2, 4}, GOLD)
    weak = score.metrics({1}, GOLD)
    # inserted != missing
    ok, reasons = score.gate({"t": (good, weak)}, live_run(missing=5, inserted=4, pack_rows=4))
    assert not ok and any("once-per-row" in r for r in reasons)
    # dbt itself printed VIOLATED
    ok, reasons = score.gate({"t": (good, weak)}, live_run(dbt_reported_violation=True))
    assert not ok and any("once-per-row" in r for r in reasons)


# -- SIMULATED ---------------------------------------------------------------------------------


def test_refuse_append_if_simulated():
    with pytest.raises(SystemExit) as e:
        score.refuse_append_if_simulated(score.Run(mode="demo"))
    assert e.value.code not in (0, None) and "SIMULATED" in str(e.value.code)
    score.refuse_append_if_simulated(live_run())  # live: no exception


def test_refuse_append_without_provenance():
    with pytest.raises(SystemExit):
        score.refuse_append_if_simulated(None)


def test_simulated_banner_and_title():
    demo = score.Run(mode="demo")
    assert "SIMULATED" in score.simulated_banner(demo)
    assert "SIMULATED" in score.simulated_banner(None)
    assert score.simulated_banner(live_run()) is None
    assert score.scorecard_title(demo) == "SIMULATED backend vs regex baseline"
    assert score.scorecard_title(None) == "SIMULATED backend vs regex baseline"
    assert score.scorecard_title(live_run()) == "Jev vs regex baseline"


# -- run provenance ----------------------------------------------------------------------------


def run_line_example(**kw):
    base = dict(
        mode="live", answered_model="jev-1.13.0", requested_model="jev-1.13.0", tested=1057,
        missing=1057, inserted=1057, packs=5, pack_rows=1057, tokens=31_000, est_tokens=30_000,
        retries=1, throttled=1, span_s=1.3, budget=48_000, invocation_id="abc")
    return score.Run(**(base | kw))


def test_run_derived_numbers():
    r = run_line_example()
    assert r.judgments == 1057 and r.cached_pct == 0.0 and r.errors == 0
    assert r.cost_usd == pytest.approx(31_000 * 0.042 / 1e6)
    assert r.est_ratio == pytest.approx(30_000 / 31_000)
    assert r.once_per_row_ok
    cached = run_line_example(missing=0, inserted=0, packs=0, pack_rows=0, tokens=0, est_tokens=0)
    assert cached.cached_pct == 100.0 and cached.est_ratio is None and cached.once_per_row_ok


def test_run_line_matches_the_dbt_summary_layout():
    line = score.run_line(run_line_example())
    assert line == (
        "Jev · 1,057 judgments · 0% cached · 5 requests · 1 retries (1× 429) · 1.3 s Jev · "
        "$0.001 · LIVE jev-1.13.0 budget=48k")
    demo = score.run_line(run_line_example(mode="demo", unjudged=2, error_packs=1))
    assert "SIMULATED jev-1.13.0 budget=48k" in demo
    assert demo.endswith(" · 2 unjudged (1 failed requests)")


def test_once_per_row_ok_counts_oversized_rows_out_of_the_packs():
    ok = run_line_example(inserted=1057, missing=1057, oversized=7, pack_rows=1050)
    assert ok.once_per_row_ok
    assert not run_line_example(pack_rows=1056).once_per_row_ok
    assert not run_line_example(dups=1).once_per_row_ok


def test_parse_once_per_row_violation():
    ok = "\x1b[0m12:00  Jev · once-per-row OK · LIVE: 5 inserted = 5 missing\n"
    bad = "Jev · once-per-row VIOLATED · LIVE: 5 inserted = 6 missing\n"
    assert score.dbt_reported_violation(ok) is False
    assert score.dbt_reported_violation(bad) is True
    assert score.dbt_reported_violation("nothing") is False


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


def test_load_run_reads_the_latest_invocation_of_the_selected_tests():
    sql = FakeSql({
        "from jev_demo.jev.hook_runs": Result("SUCCEEDED", rows=[["inv-1"]]),
    })
    assert score.latest_invocation(sql, ["a", "b"]) == "inv-1"
    q = sql.seen[0]
    assert "order by recorded_at desc limit 1" in q and "test_name in ('a', 'b')" in q


def test_latest_invocation_none_when_no_hook_runs():
    sql = FakeSql({"hook_runs": Result("SUCCEEDED", rows=[])})
    assert score.latest_invocation(sql, ["a"]) is None


TESTS4 = list(score.TESTS)


def ledger_sql(distinct_tests="4", mode="demo", dups="0", unjudged="0"):
    return FakeSql({
        "from jev_demo.jev.hook_runs": Result("SUCCEEDED", rows=[
            [distinct_tests, "1057", "1057", "1057", "0", mode, "jev-1.13.0"]]),
        "from jev_demo.jev.requests": Result("SUCCEEDED", rows=[
            ["5", "31000", "30000", "1057", "2", "1", "0", "1.3", "jev-1.13.0"]]),
        "from jev_demo.jev.judgments where invocation_id": Result(
            "SUCCEEDED", rows=[[unjudged, dups]]),
        "jev_invocation_id is distinct from": Result("SUCCEEDED", rows=[["10", "0"]]),
    })


def test_load_run_assembles_provenance_from_ledger_tables():
    r = score.load_run(ledger_sql(), "inv-1", 48_000, TESTS4)
    assert r.mode == "demo" and r.simulated and r.judgments == 1057
    assert (r.packs, r.tokens, r.est_tokens, r.retries, r.throttled) == (5, 31000, 30000, 2, 1)
    assert r.answered_model == "jev-1.13.0" and r.span_s == 1.3 and r.budget == 48_000


def test_load_run_queries_are_scoped_to_the_scored_tests_and_mode():
    sql = ledger_sql()
    score.load_run(sql, "inv-1", 48_000, TESTS4)
    for q in sql.seen:
        assert "test_name in ('customers_full_name_is_a_person'" in q, q
    dups_q = next(q for q in sql.seen if "having count(*) > 1" in q)
    assert "mode = 'demo'" in dups_q


def test_load_run_partial_coverage_is_not_captured():
    with pytest.raises(score.NotCaptured, match="3 of 4"):
        score.load_run(ledger_sql(distinct_tests="3"), "inv-1", 48_000, TESTS4)


@pytest.mark.parametrize("mode", [None, "", "simulated"])
def test_load_run_without_a_valid_mode_raises_instead_of_defaulting_to_live(mode):
    sql = ledger_sql()
    sql.answers["from jev_demo.jev.hook_runs"] = Result("SUCCEEDED", rows=[
        ["4", "1057", "1057", "1057", "0", mode, "jev-1.13.0"]])
    with pytest.raises(score.NotCaptured, match="mode"):
        score.load_run(sql, "inv-1", 48_000, TESTS4)


def test_not_captured_is_a_value_error():
    assert issubclass(score.NotCaptured, ValueError)


def test_require_new_invocation():
    assert score.require_new_invocation("old", "new") == "new"
    assert score.require_new_invocation(None, "new") == "new"
    with pytest.raises(score.NotCaptured, match="no new invocation"):
        score.require_new_invocation("old", "old")
    with pytest.raises(score.NotCaptured, match="no new invocation"):
        score.require_new_invocation(None, None)


def test_check_dbt_result():
    done = "12:00:00  Done. PASS=30 WARN=3 ERROR=0 SKIP=0 NO-OP=0 TOTAL=33\n"
    assert score.check_dbt_result(0, done, "") == done
    with pytest.raises(score.NotCaptured, match="exit status 1") as e:
        score.check_dbt_result(1, done, "boom on stderr")
    assert "boom on stderr" in str(e.value) and "PASS=30" in str(e.value)
    with pytest.raises(score.NotCaptured, match="ERROR=2"):
        score.check_dbt_result(0, "\x1b[0mDone. PASS=3 WARN=0 ERROR=2 SKIP=0 TOTAL=5\n", "")
    with pytest.raises(score.NotCaptured, match="Done"):
        score.check_dbt_result(0, "no final line", "")


def test_unjudged_consistency_between_ledger_states_and_table_rows():
    assert score.unjudged_consistent(0, 0)
    assert score.unjudged_consistent(3, 5)  # rows repeat states
    assert not score.unjudged_consistent(0, 2)  # table shows unjudged rows the ledger never saw
    assert not score.unjudged_consistent(2, 0)
    assert not score.unjudged_consistent(5, 3)  # more failed states than rows is impossible


def test_table_unjudged_counts_null_scores_in_each_stored_failure_table():
    sql = FakeSql({"count_if(jev_p is null)": Result("SUCCEEDED", rows=[["2"]])})
    assert score.table_unjudged(sql, ["a", "b"]) == 4
    assert all("jaffle_shop_dbt_test__audit." in q for q in sql.seen)


# -- dbt command / fresh / queries -------------------------------------------------------------


def test_dbt_args_yardstick_builds_the_whole_project_minus_production():
    assert score.dbt_args(production=False) == [
        "build", "--exclude", "tag:production", "tag:production_baseline"]


def test_dbt_args_production_selects_the_production_models_and_tests():
    assert score.dbt_args(production=True) == [
        "build", "--vars", "{production: true, jev_max_concurrency: 2}",
        "--select", "+tag:production", "tag:production_baseline"]


def test_fresh_sql_deletes_only_this_modes_judgments_for_the_selected_tests():
    sql = score.fresh_sql("demo", ["a", "b"])
    assert sql == ("delete from jev_demo.jev.judgments where mode = 'demo' "
                   "and test_name in ('a', 'b')")
    with pytest.raises(ValueError):
        score.fresh_sql("demo; drop", ["a"])
    with pytest.raises(ValueError):
        score.fresh_sql("live", ["a'b"])


def test_flagged_query_excludes_unjudged_rows_for_jev_tests_only():
    jev = score.flagged_query("reviews_body_matches_stars", "review_id", judged_only=True)
    assert jev == ("select review_id from jev_demo.jaffle_shop_dbt_test__audit."
                   "reviews_body_matches_stars where jev_p is not null")
    base = score.flagged_query("baseline_reviews_body_matches_stars", "review_id")
    assert "jev_p" not in base


def test_tests_are_the_four_yardstick_tests():
    assert set(score.TESTS) == {
        "customers_full_name_is_a_person", "returns_comment_matches_reason_code",
        "reviews_body_matches_stars", "tickets_body_has_no_pii"}


# -- demo 04 reference -------------------------------------------------------------------------


def test_demo04_reference_is_the_hand_copied_log():
    ref = score.load_demo04_reference()
    assert ref["compare_to"] == "live/pack=64/nested"
    assert set(ref["runs"]) == {"live/pack=1", "live/pack=32/nested", "live/pack=64/nested"}
    p64 = ref["runs"]["live/pack=64/nested"]
    assert (p64["requests"], p64["unique_states"], p64["wall_s"], p64["cost_usd"]) == (
        18, 1057, 1.2, 0.006)
    assert p64["source_heading"].endswith("live/pack=64/nested")
    assert set(p64["tests"]) == set(score.TESTS)
    t = p64["tests"]["tickets_body_has_no_pii"]
    assert (t["jev"]["precision"], t["jev"]["recall"]) == (0.93, 1.0)
    assert (t["baseline"]["precision"], t["baseline"]["recall"]) == (0.48, 0.86)
    assert ref["runs"]["live/pack=1"]["requests"] == 1057


# -- production --------------------------------------------------------------------------------


def prod_inputs(**kw):
    planted = set(range(1, 101))
    flagged = set(range(1, 91)) | set(range(1000, 1050))  # 90 planted TPs + 50 unplanted
    base = dict(flagged=flagged, planted=planted, baseline_flagged={1, 2, 3, 2000, 2001},
                audit=AUDIT)
    return base | kw


def test_production_metrics():
    m = score.production_metrics(**prod_inputs())
    assert (m.flagged, m.planted, m.planted_tp, m.unplanted_flagged) == (140, 100, 90, 50)
    assert m.recall == pytest.approx(0.9)
    assert m.raw_precision == pytest.approx(90 / 140)
    assert m.audited_precision == pytest.approx(130 / 140)
    assert m.audit_lo < m.audited_precision < m.audit_hi
    assert m.baseline.tp == 3 and m.baseline.fp == 2
    assert m.jev_raw.f1 > m.baseline.f1
    assert m.audited_f1 == pytest.approx(
        2 * m.audited_precision * m.recall / (m.audited_precision + m.recall))


def test_production_metrics_audit_pending_without_labels():
    m = score.production_metrics(**prod_inputs(audit=None))
    assert m.audited_precision is None and m.audit_lo is None and m.audited_f1 is None
    assert m.raw_precision == pytest.approx(90 / 140)
    assert score.production_metrics(**prod_inputs(audit={})).audited_precision is None


def test_production_gate_passes():
    m = score.production_metrics(**prod_inputs())
    ok, reasons = score.production_gate(m, live_run(), rerun_requests=0)
    assert ok and reasons == []


def test_production_gate_reasons():
    flagged = set(range(1, 51)) | set(range(1000, 1200))
    weak = score.production_metrics(**prod_inputs(flagged=flagged))
    bad_run = live_run(error_packs=1, dbt_reported_violation=True)
    ok, reasons = score.production_gate(weak, bad_run, rerun_requests=3)
    assert not ok
    assert any("recall" in r and "< 0.85" in r for r in reasons)
    assert any("audited precision" in r for r in reasons)
    assert "run reported errors" in reasons
    assert any("once-per-row" in r for r in reasons)
    assert any("rerun made 3 requests" in r for r in reasons)


def test_production_gate_pending_audit_is_not_a_pass():
    m = score.production_metrics(**prod_inputs(audit=None))
    ok, reasons = score.production_gate(m, live_run(), rerun_requests=0)
    assert not ok and reasons == ["audited precision: audit pending"]


def test_production_gate_is_pending_without_the_rerun_check():
    m = score.production_metrics(**prod_inputs())
    ok, reasons = score.production_gate(m, live_run(), rerun_requests=None)
    assert not ok and reasons == ["rerun not checked (use --rerun)"]
    assert score.gate_word(ok, reasons) == "PENDING"
    assert score.gate_word(True, []) == "PASS"
    assert score.gate_word(False, ["run was not LIVE"]) == "FAIL"
    assert score.gate_word(False, ["rerun not checked (use --rerun)", "run was not LIVE"]) == "FAIL"


def test_production_gate_f1_must_beat_baseline():
    m = score.production_metrics(**prod_inputs(baseline_flagged=set(range(1, 100))))
    ok, reasons = score.production_gate(m, live_run(), rerun_requests=0)
    assert not ok and any("does not beat baseline" in r for r in reasons)


def test_production_gate_not_live():
    m = score.production_metrics(**prod_inputs())
    ok, reasons = score.production_gate(m, score.Run(mode="demo"), rerun_requests=None)
    assert "run was not LIVE" in reasons


# -- audit labels ------------------------------------------------------------------------------


def test_read_labels_file(tmp_path):
    assert score.read_audit_labels(tmp_path / "missing.csv") is None
    p = tmp_path / "labels.csv"
    p.write_text("id,label\n5,real\n6,ok\n")
    assert score.read_audit_labels(p) == {5: "real", 6: "ok"}
    p.write_text("id,label\n5,real\n6,maybe\n")
    with pytest.raises(ValueError, match="label"):
        score.read_audit_labels(p)


def test_labels_from_blind_audit(tmp_path):
    p = tmp_path / "production_audit.csv"
    p.write_text("id,stars,body,label\n1,5,great,ok\n2,1,\"love, it\",real\n3,1,x,\n")
    labelled, total, labels = score.labels_from_audit_sample(p)
    assert (labelled, total) == (2, 3) and labels == {1: "ok", 2: "real"}
    assert score.labels_from_audit_sample(tmp_path / "none.csv") is None


# -- append ------------------------------------------------------------------------------------


def yard_results():
    good = score.metrics({1, 2, 4}, GOLD)
    weak = score.metrics({1, 3}, GOLD)
    return {"t": (good, weak)}


def test_append_report_shape(tmp_path):
    path = tmp_path / "eval-results.md"
    detail = {"t": ([3], [])}
    run = live_run(tested=10, missing=10, inserted=10, packs=2, pack_rows=10, tokens=1000,
                   est_tokens=900, retries=1, throttled=1, span_s=0.5, budget=48_000,
                   invocation_id="abc")
    score.append_report(path, yard_results(), detail, run, warehouse="jev-demo-5")
    text = path.read_text()
    assert "· live/budget=48k" in text.splitlines()[1]
    assert "Jev · 10 judgments" in text and "LIVE jev-1.13.0 budget=48k" in text
    assert "warehouse jev-demo-5" in text and "2 requests" in text
    assert "1 retries (1× 429)" in text and "1,000 tokens" in text and "$0.000042" in text
    assert "est/actual tokens 0.90" in text
    assert "| t | 3 | 1.00 | 1.00 | 0 | 0.50 | 0.33 | 1 |" in text
    assert "**Gate: PASS**" in text
    assert "- `t`: hard negatives flagged = [3], defects missed = []" in text


def test_append_report_refuses_simulated_and_writes_nothing(tmp_path):
    path = tmp_path / "eval-results.md"
    with pytest.raises(SystemExit):
        score.append_report(path, yard_results(), {"t": ([], [])}, score.Run(mode="demo"),
                            warehouse="w")
    assert not path.exists()


def test_append_production_report(tmp_path):
    path = tmp_path / "eval-results.md"
    m = score.production_metrics(**prod_inputs())
    run = live_run(tested=140, missing=140, inserted=140, packs=3, pack_rows=140, tokens=5000,
                   est_tokens=4500, span_s=2.0, budget=48_000)
    score.append_production_report(path, m, run, warehouse="w", rerun_requests=0)
    text = path.read_text()
    assert "production" in text.splitlines()[1] and "audited precision 0.93" in text
    assert "rerun requests 0" in text and "**Gate: PASS**" in text
    with pytest.raises(SystemExit):
        score.append_production_report(path, m, score.Run(mode="demo"), warehouse="w",
                                       rerun_requests=None)


def test_json_roundtrip_of_reference_is_valid():
    json.loads((ROOT / "eval" / "demo04_reference.json").read_text())


def test_audit_for_keeps_only_labels_of_still_flagged_unplanted_rows():
    labels = {1: "real", 5: "ok", 6: "real", 99: "ok"}
    assert score.audit_for({1, 5, 6}, {1}, labels) == {5: "ok", 6: "real"}
    assert score.audit_for(set(), set(), labels) == {}


# -- rendering (smoke: no crash, honest labels) ------------------------------------------------


def _render(fn, *args):
    from rich.console import Console

    console = Console(record=True, width=120)
    fn(console, *args)
    return console.export_text()


def test_print_production_report_pending_and_audited():
    pending = score.production_metrics(**prod_inputs(audit=None))
    text = _render(score.print_production_report, pending, live_run(), 0)
    assert "audit pending" in text and "GATE PENDING" in text and "SIMULATED" not in text
    audited = score.production_metrics(**prod_inputs())
    text = _render(score.print_production_report, audited, live_run(), 0)
    assert "audited precision" in text and "GATE PASS" in text and "rerun: 0 requests" in text


def test_print_production_report_labels_a_demo_run_simulated():
    m = score.production_metrics(**prod_inputs())
    text = _render(score.print_production_report, m, score.Run(mode="demo"), None)
    assert "SIMULATED" in text and "GATE FAIL" in text and "run was not LIVE" in text


def test_print_report_compares_with_demo04_and_labels_unique_states():
    ref = score.load_demo04_reference()
    results = {n: (score.metrics(set(), {}), score.metrics(set(), {})) for n in score.TESTS}
    text = _render(score.print_report, results, live_run(tested=5, missing=5, inserted=5,
                                                          pack_rows=5, packs=1), ref)
    assert "vs demo 04 (live/pack=64/nested)" in text
    assert "unique states" in text and "18 requests" in text
    assert "04 F1 (from P/R)" in text
    sim = _render(score.print_report, results, score.Run(mode="demo"), ref)
    assert "SIMULATED" in sim


def test_print_production_report_without_rerun_is_pending():
    m = score.production_metrics(**prod_inputs())
    text = _render(score.print_production_report, m, live_run(), None)
    assert "GATE PENDING" in text and "rerun not checked (use --rerun)" in text
    assert "GATE PASS" not in text


def test_append_production_report_records_pending_when_rerun_not_checked(tmp_path):
    path = tmp_path / "eval-results.md"
    m = score.production_metrics(**prod_inputs())
    score.append_production_report(path, m, live_run(tested=1, missing=1, inserted=1,
                                                     pack_rows=1), warehouse="w",
                                   rerun_requests=None)
    text = path.read_text()
    assert "**Gate: PENDING**" in text and "PASS" not in text.split("**Gate")[1]


def test_demo04_reference_marks_f1_as_derived():
    ref = score.load_demo04_reference()
    for run in ref["runs"].values():
        for t in run["tests"].values():
            for side in ("jev", "baseline"):
                assert "f1" not in t[side] and "f1_derived" in t[side]


# -- R15: provenance belongs to the scored run -------------------------------------------------


class Args:
    def __init__(self, **kw):
        self.run, self.fresh, self.rerun, self.mode = True, False, False, None
        self.__dict__.update(kw)


class SeqSql:
    """A warehouse whose hook_runs latest-invocation answers follow a script."""

    def __init__(self, latest, *, distinct="4", mode="demo", table_unjudged="0", unjudged="0"):
        self.latest = list(latest)
        self.fixed = ledger_sql(distinct_tests=distinct, mode=mode, unjudged=unjudged)
        self.fixed.answers["count_if(jev_p is null)"] = Result(
            "SUCCEEDED", rows=[[table_unjudged]])
        self.seen = self.fixed.seen

    def run(self, sql, timeout_s=900):
        if "order by recorded_at desc limit 1" in sql:
            self.seen.append(sql)
            inv = self.latest.pop(0)
            return Result("SUCCEEDED", rows=[[inv]] if inv else [])
        return self.fixed.run(sql, timeout_s)


@pytest.fixture
def dbt_calls(monkeypatch):
    calls = []

    def fake(*, production, mode):
        calls.append((production, mode))
        return "Done. PASS=1 WARN=0 ERROR=0 SKIP=0 TOTAL=1\n"

    monkeypatch.setattr(score, "run_dbt", fake)
    monkeypatch.setattr(score, "load_budget", lambda: 48_000)
    monkeypatch.setenv("JEV_MODE", "demo")
    return calls


def obtain(sql, args, **kw):
    return score._obtain_run(sql, args, TESTS4, production=False, **kw)


def test_obtain_run_takes_the_new_invocation_of_this_run(dbt_calls):
    sql = SeqSql(["old", "new"])
    run, increment = obtain(sql, Args())
    assert run.invocation_id == "new" and increment is None and dbt_calls == [(False, None)]


def test_obtain_run_rejects_a_stale_invocation(dbt_calls, capsys):
    sql = SeqSql(["same", "same"])
    run, _ = obtain(sql, Args())
    assert run is None
    assert "no new invocation" in capsys.readouterr().err


def test_obtain_run_rejects_partial_test_coverage(dbt_calls, capsys):
    run, _ = obtain(SeqSql(["old", "new"], distinct="3"), Args())
    assert run is None and "3 of 4" in capsys.readouterr().err


def test_obtain_run_rejects_a_mode_other_than_the_one_requested(dbt_calls, capsys):
    run, _ = obtain(SeqSql(["old", "new"], mode="demo"), Args(mode="live"))
    assert run is None and "mode" in capsys.readouterr().err


def test_obtain_run_reports_dbt_failure_as_not_captured(monkeypatch, capsys):
    def boom(*, production, mode):
        raise score.NotCaptured("dbt build ended with ERROR=1\n--- stdout (tail) ---\nxyz")

    monkeypatch.setattr(score, "run_dbt", boom)
    monkeypatch.setattr(score, "load_budget", lambda: 48_000)
    run, _ = obtain(SeqSql(["old", "new"]), Args())
    err = capsys.readouterr().err
    assert run is None and "ERROR=1" in err and "xyz" in err


def test_obtain_run_unjudged_mismatch_with_the_stored_tables_is_not_captured(dbt_calls, capsys):
    run, _ = obtain(SeqSql(["old", "new"], table_unjudged="3", unjudged="0"), Args())
    assert run is None and "unjudged" in capsys.readouterr().err
    ok, _ = obtain(SeqSql(["old", "new"], table_unjudged="3", unjudged="2"), Args())
    assert ok is not None and ok.unjudged == 2


def test_obtain_run_without_run_flag_uses_latest_and_does_not_run_dbt(dbt_calls):
    run, _ = obtain(SeqSql(["latest"]), Args(run=False))
    assert run.invocation_id == "latest" and dbt_calls == []


def test_rerun_needs_its_own_new_invocation(dbt_calls, capsys):
    # second build leaves no new invocation -> the rerun check cannot pass
    sql = SeqSql(["old", "new", "new"])
    run, _ = obtain(sql, Args(rerun=True))
    with pytest.raises(score.NotCaptured, match="no new invocation"):
        score._rerun(sql, Args(rerun=True), TESTS4, run, production=False)


def test_rerun_counts_the_second_builds_requests(dbt_calls):
    sql = SeqSql(["old", "new", "newer"])
    run, _ = obtain(sql, Args(rerun=True))
    assert run.invocation_id == "new" and len(dbt_calls) == 1  # _obtain_run builds once
    assert score._rerun(sql, Args(rerun=True), TESTS4, run, production=False) == 5
    assert len(dbt_calls) == 2


def test_append_requires_run():
    with pytest.raises(SystemExit) as e:
        score.main(["--append"])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        score.main(["--production", "--append"])
    assert e.value.code == 2


def test_current_run_is_none_for_a_partial_invocation():
    assert score.current_run(SeqSql(["inv"], distinct="3"), TESTS4, 48_000) is None
    assert score.current_run(SeqSql([None]), TESTS4, 48_000) is None
    assert score.current_run(SeqSql(["inv"]), TESTS4, 48_000).invocation_id == "inv"


# -- warehouse name ----------------------------------------------------------------------------


class FakeWarehouses:
    def __init__(self, items):
        self.items = items

    def list(self):
        from types import SimpleNamespace

        return [SimpleNamespace(id=i, name=n) for i, n in self.items]


class FakeClientSql:
    def __init__(self, items):
        from types import SimpleNamespace

        self.client = SimpleNamespace(warehouses=FakeWarehouses(items))


def test_warehouse_name_passes_names_through_and_resolves_ids():
    sql = FakeClientSql([("0123456789abcdef", "jev-demo-5")])
    assert score.warehouse_name(sql, "jev-demo-5") == "jev-demo-5"
    assert score.warehouse_name(sql, "0123456789abcdef") == "jev-demo-5"
    with pytest.raises(SystemExit, match="warehouse"):
        score.warehouse_name(sql, "ffffffffffffffff")


# -- audit labels: newest wins, written only on append -----------------------------------------


def _sample(path, rows):
    path.write_text("id,stars,body,label\n" + "".join(f"{i},1,x,{label}\n" for i, label in rows))


def test_resolve_audit_labels_prefers_a_newer_sample(tmp_path):
    import os

    labels, sample = tmp_path / "labels.csv", tmp_path / "sample.csv"
    labels.write_text("id,label\n1,ok\n")
    _sample(sample, [(1, "real"), (2, "ok")])
    os.utime(labels, (1_000, 1_000))
    os.utime(sample, (2_000, 2_000))
    got = score.resolve_audit_labels(labels, sample)
    assert got.labels == {1: "real", 2: "ok"} and got.source == "sample" and got.pending is None
    os.utime(sample, (500, 500))  # older sample: the committed labels win
    got = score.resolve_audit_labels(labels, sample)
    assert got.labels == {1: "ok"} and got.source == "labels"


def test_resolve_audit_labels_pending_cases(tmp_path):
    labels, sample = tmp_path / "labels.csv", tmp_path / "sample.csv"
    got = score.resolve_audit_labels(labels, sample)
    assert got.labels is None and "not found" in got.pending
    _sample(sample, [(1, "real"), (2, "")])
    got = score.resolve_audit_labels(labels, sample)
    assert got.labels is None and "1 of 2" in got.pending


def test_resolve_audit_labels_rejects_bad_labels_in_a_newer_sample(tmp_path):
    labels, sample = tmp_path / "labels.csv", tmp_path / "sample.csv"
    _sample(sample, [(1, "maybe")])
    with pytest.raises(ValueError, match="label"):
        score.resolve_audit_labels(labels, sample)


def test_write_audit_labels_writes_id_and_label_only(tmp_path):
    out = tmp_path / "labels.csv"
    score.write_audit_labels({2: "ok", 1: "real"}, out)
    assert out.read_text() == "id,label\n1,real\n2,ok\n"


# -- --run needs an explicit --mode ------------------------------------------------------------


def test_run_requires_an_explicit_mode(capsys):
    with pytest.raises(SystemExit) as e:
        score.main(["--run"])
    assert e.value.code == 2 and "--mode" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        score.main(["--production", "--run", "--fresh"])
    assert e.value.code == 2


# -- F5: stored failures must belong to the scored run -----------------------------------------


def test_stored_provenance_sql_checks_mode_and_invocation():
    q = score.stored_provenance_sql("t1", live_run(invocation_id="inv-9"))
    assert "from jev_demo.jaffle_shop_dbt_test__audit.t1" in q
    assert "jev_mode is distinct from 'live'" in q
    assert "jev_invocation_id is distinct from 'inv-9'" in q


def test_check_stored_provenance_accepts_rows_of_this_run():
    sql = FakeSql({"is distinct from": Result("SUCCEEDED", rows=[["7", "0"]])})
    score.check_stored_provenance(sql, ["a", "b"], live_run(invocation_id="inv"))
    assert len(sql.seen) == 2


def test_check_stored_provenance_rejects_stale_or_other_mode_rows():
    sql = FakeSql({"is distinct from": Result("SUCCEEDED", rows=[["7", "3"]])})
    with pytest.raises(score.NotCaptured, match="3 of 7 stored rows"):
        score.check_stored_provenance(sql, ["a"], live_run(invocation_id="inv"))


def test_check_stored_provenance_rejects_tables_without_the_columns():
    sql = FakeSql({"is distinct from": Result(
        "FAILED",
        error="[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column `jev_mode` cannot be resolved")})
    with pytest.raises(score.NotCaptured, match="no jev_mode"):
        score.check_stored_provenance(sql, ["a"], live_run(invocation_id="inv"))


def test_obtain_run_is_not_captured_when_stored_failures_are_stale(dbt_calls, capsys):
    sql = SeqSql(["old", "new"])
    sql.fixed.answers["jev_invocation_id is distinct from"] = Result(
        "SUCCEEDED", rows=[["10", "10"]])
    run, _ = obtain(sql, Args())
    assert run is None and "stored failures do not belong" in capsys.readouterr().err
    q = next(q for q in sql.seen if "is distinct from" in q)
    assert "'new'" in q and "'demo'" in q


def test_current_run_is_none_when_stored_failures_are_from_another_invocation():
    sql = SeqSql(["inv"])
    sql.fixed.answers["jev_invocation_id is distinct from"] = Result(
        "SUCCEEDED", rows=[["10", "2"]])
    assert score.current_run(sql, TESTS4, 48_000) is None


def test_rerun_happens_after_the_stored_failures_are_checked(dbt_calls):
    # the scored stored failures are the first build's; the rerun's own tables are not scored
    sql = SeqSql(["old", "new", "newer"])
    run, _ = obtain(sql, Args(rerun=True))
    checked = [q for q in sql.seen if "is distinct from" in q]
    assert checked and all("'new'" in q for q in checked)


# -- F2: recall counts only the planted flips that are loaded ----------------------------------


def test_loaded_ids_query_reads_the_production_model():
    q = score.loaded_ids_sql({3, 1, 2})
    assert q == ("select review_id from jev_demo.jaffle_shop.stg_product_reviews "
                 "where review_id in (1, 2, 3)")


def test_load_loaded_intersects_with_what_the_model_holds():
    sql = FakeSql({"stg_product_reviews": Result("SUCCEEDED", rows=[["1"], ["3"]])})
    assert score.load_loaded(sql, {1, 2, 3}) == {1, 3}
    assert score.load_loaded(FakeSql({}), set()) == set()  # no query for no ids


def test_production_metrics_scores_recall_on_the_loaded_flips_only():
    planted = set(range(1, 101))
    loaded = set(range(1, 81))  # part 1 holds 80 of the 100 planted flips
    m = score.production_metrics(set(range(1, 73)), planted, set(), None, loaded=loaded)
    assert (m.planted, m.planted_total) == (80, 100)
    assert m.recall == pytest.approx(72 / 80)
    text = _render(score.print_production_report, m, live_run(), None)
    assert "planted flips loaded: 80 of 100" in text


def test_append_production_report_records_loaded_flips(tmp_path):
    path = tmp_path / "e.md"
    m = score.production_metrics(set(range(1, 73)), set(range(1, 101)), set(), None,
                                 loaded=set(range(1, 81)))
    score.append_production_report(path, m, live_run(tested=5, missing=5, inserted=5,
                                                     pack_rows=5), "w", None)
    assert "planted flips loaded: 80 of 100" in path.read_text()


# -- F3: the increment, cached share and the invocations cached judgments came from -------------


def test_increment_line_and_checks():
    run = live_run(tested=50_000, missing=2_487, inserted=2_487, pack_rows=2_487)
    inc = score.check_increment(47_500, 50_000, run)
    assert inc.line == "increment: 2,487 new distinct states judged (2,500 rows loaded)"
    with pytest.raises(score.NotCaptured, match="no new rows"):
        score.check_increment(47_500, 47_500, run)
    with pytest.raises(score.NotCaptured, match="only 10 rows"):
        score.check_increment(47_500, 47_510, run)
    bad = live_run(tested=50_000, missing=2_487, inserted=2_400, pack_rows=2_400)
    with pytest.raises(score.NotCaptured, match="inserted"):
        score.check_increment(47_500, 50_000, bad)


def test_obtain_run_with_increment_counts_rows_before_and_after(dbt_calls):
    sql = SeqSql(["old", "new"])
    counts, builds_seen = iter([["47500"], ["50000"]]), []
    orig = sql.fixed.run

    def run(q, timeout_s=900):
        if q.startswith("select count(*) from jev_demo.jaffle_shop.stg_product_reviews"):
            builds_seen.append(len(dbt_calls))
            return Result("SUCCEEDED", rows=[next(counts)])
        return orig(q, timeout_s)

    sql.fixed.run = run
    got, inc = obtain(sql, Args(increment=True))
    assert got is not None and inc.rows_loaded == 2_500 and inc.new_states == 1057
    assert builds_seen == [0, 1]  # counted once before the build and once after it


def test_increment_needs_production_and_run_and_no_fresh():
    for argv in (["--increment"], ["--run", "--mode", "live", "--increment"],
                 ["--production", "--run", "--mode", "live", "--fresh", "--increment"]):
        with pytest.raises(SystemExit) as e:
            score.main(argv)
        assert e.value.code == 2, argv


def test_sources_sql_is_scoped_to_tests_mode_and_latest_question():
    q = score.sources_sql(["t1"], "live")
    assert "max_by(question, judged_at)" in q and "test_name in ('t1')" in q
    assert "j.p is not null" in q and "mode = 'live'" in q and "group by j.invocation_id" in q
    assert "jev_demo.jev.requests" in q


def test_load_sources():
    sql = FakeSql({"max_by(question": Result("SUCCEEDED", rows=[
        ["inv-a", "94000", "400", "12000000", "310.5"], ["inv-b", "4987", "22", "600000", "20"]])})
    src = score.load_sources(sql, ["t1"], "live")
    assert [s.invocation_id for s in src] == ["inv-a", "inv-b"]
    assert src[0].states == 94_000 and src[0].requests == 400 and src[0].tokens == 12_000_000
    assert src[0].cost_usd == pytest.approx(12_000_000 * 0.042 / 1e6)


def test_every_append_records_invocation_and_cached_share(tmp_path):
    path = tmp_path / "e.md"
    run = live_run(tested=10, missing=10, inserted=10, packs=2, pack_rows=10,
                   invocation_id="inv-a1")
    score.append_report(path, yard_results(), {"t": ([], [])}, run, warehouse="w")
    text = path.read_text()
    assert "- invocation inv-a1" in text
    assert "cached 0% (0 of 10 states from earlier invocations; 10 judged in this run)" in text


def test_production_append_records_where_cached_judgments_came_from(tmp_path):
    path = tmp_path / "e.md"
    m = score.production_metrics(**prod_inputs())
    run = live_run(tested=100, missing=0, inserted=0, packs=0, pack_rows=0, invocation_id="i3")
    sources = [score.Source("i1", 95, 3, 30_000, 12.5), score.Source("i2", 5, 1, 1_000, 1.0)]
    inc = score.Increment(47_500, 50_000, 5)
    score.append_production_report(path, m, run, "w", 0, increment=inc, sources=sources)
    text = path.read_text()
    assert "cached 100% (100 of 100 states from earlier invocations; 0 judged in this run)" in text
    assert "- judged in invocation i1: 95 states · 3 requests · 30,000 tokens · $0.001260" in text
    assert "12.5 s Jev" in text and "- judged in invocation i2: 5 states" in text
    assert "increment: 5 new distinct states judged (2,500 rows loaded)" in text


# -- F4: a yardstick entry never comes from cached judgments -----------------------------------


def test_yardstick_append_refuses_a_cached_run(tmp_path):
    path = tmp_path / "e.md"
    cached = live_run(tested=10, missing=4, inserted=4, pack_rows=4)
    with pytest.raises(SystemExit) as e:
        score.append_report(path, yard_results(), {"t": ([], [])}, cached, warehouse="w")
    assert "60% of the scored states were cached" in str(e.value.code)
    assert "--fresh" in str(e.value.code) and not path.exists()


# -- comparison note ---------------------------------------------------------------------------


def test_print_report_notes_how_packs_differ_from_demo04():
    ref = score.load_demo04_reference()
    results = {n: (score.metrics(set(), {}), score.metrics(set(), {})) for n in score.TESTS}
    text = _render(score.print_report, results, live_run(budget=48_000), ref)
    assert "pack=64/nested" in text and "estimated tokens" in text and "256" in text


# -- R26: key audit (is the planted key right?) and the LLM-labelled audit protocol ---------------

LOADED = set(range(1, 101))
KEY_FLAGGED = set(range(1, 81)) | {500, 501}  # 80 of the 100 loaded flips, plus 2 unplanted
# audited: 10 flagged flips (8 real) and 5 unflagged flips (2 real)
KEY_LABELS = ({i: "real" for i in range(1, 9)} | {9: "ok", 10: "ok"}
              | {81: "real", 82: "real", 83: "ok", 84: "ok", 85: "ok"})
PROTOCOL = ("Audit labels by two independent LLM labellers (Claude Opus, Claude Sonnet), blind to "
            "Jev's output; disagreements resolved against Jev.")
AGREEMENT = {
    "precision_audit": {"n": 100, "agreement": 0.94, "kappa": 0.81, "tie": "ok",
                        "disagreements": [3, 9, 12, 40, 41, 77]},
    "key_audit": {"n": 100, "agreement": 0.9, "kappa": 0.7, "tie": "real",
                  "disagreements": list(range(10))},
}


def test_key_audit_numbers():
    ka = score.key_audit(KEY_FLAGGED, LOADED, KEY_LABELS)
    assert (ka.n, ka.real, ka.loaded_flips, ka.flagged_flips) == (15, 10, 100, 80)
    assert ka.key_precision == pytest.approx(10 / 15)
    assert ka.key_lo < ka.key_precision < ka.key_hi
    assert (ka.flagged_real, ka.recall_vs_real) == (8, pytest.approx(0.8))
    assert ka.recall_lo < 0.8 < ka.recall_hi
    # flagged flips scaled from their audited real share (8/10), unflagged from theirs (2/5)
    assert ka.corrected_recall == pytest.approx(64 / 72)


def test_key_audit_ignores_labels_of_flips_that_are_not_loaded():
    ka = score.key_audit(KEY_FLAGGED, LOADED, KEY_LABELS | {999: "real"})
    assert ka.n == 15


def test_key_audit_corrected_recall_needs_both_strata_when_both_exist():
    only_flagged = {i: v for i, v in KEY_LABELS.items() if i <= 10}
    assert score.key_audit(KEY_FLAGGED, LOADED, only_flagged).corrected_recall is None
    # nothing unflagged exists: the unflagged stratum contributes nothing, so recall is 1.0
    ka = score.key_audit(LOADED, LOADED, only_flagged)
    assert ka.corrected_recall == pytest.approx(1.0)


def test_key_audit_with_no_real_flips_has_no_recall():
    ka = score.key_audit(KEY_FLAGGED, LOADED, {1: "ok", 81: "ok"})
    assert ka.real == 0 and ka.recall_vs_real is None and ka.corrected_recall is None
    assert ka.key_precision == 0.0


def test_key_audit_needs_labels_and_valid_ones():
    assert score.key_audit(KEY_FLAGGED, LOADED, {}) is None
    assert score.key_audit(KEY_FLAGGED, LOADED, {999: "real"}) is None
    with pytest.raises(ValueError, match="label"):
        score.key_audit(KEY_FLAGGED, LOADED, {1: "maybe"})


def test_corrected_recall_gate_is_a_separate_line():
    ka = score.key_audit(KEY_FLAGGED, LOADED, KEY_LABELS)
    assert score.corrected_recall_line(ka) == "recall (key-noise corrected) ≥ 0.85: PASS (0.89)"
    low = score.key_audit(set(range(1, 51)), LOADED,
                          {1: "real", 2: "real", 51: "real", 52: "real"})
    assert score.corrected_recall_line(low) == "recall (key-noise corrected) ≥ 0.85: FAIL (0.50)"
    assert score.corrected_recall_line(None) == (
        "recall (key-noise corrected) ≥ 0.85: PENDING (key audit not labelled)")
    unestimable = score.key_audit(KEY_FLAGGED, LOADED, {1: "real", 2: "ok"})
    assert score.corrected_recall_line(unestimable) == (
        "recall (key-noise corrected) ≥ 0.85: PENDING (not estimable from the audit)")


def test_the_raw_gate_does_not_change_when_a_key_audit_exists():
    base = score.production_metrics(**prod_inputs(flagged=set(range(1, 50))))
    keyed = score.production_metrics(**prod_inputs(flagged=set(range(1, 50))),
                                     flip_audit={1: "ok", 60: "ok"})
    assert keyed.key_audit is not None and base.key_audit is None
    assert score.production_gate(base, live_run(), 0) == score.production_gate(
        keyed, live_run(), 0)


def test_production_metrics_builds_the_key_audit_from_the_loaded_flips():
    m = score.production_metrics(KEY_FLAGGED, LOADED | {7000}, set(), None, loaded=LOADED,
                                 flip_audit=KEY_LABELS)
    assert m.key_audit.loaded_flips == 100 and m.key_audit.flagged_flips == 80


def test_read_agreement(tmp_path):
    p = tmp_path / "a.json"
    assert score.read_agreement(p) is None
    p.write_text(json.dumps(AGREEMENT))
    assert score.read_agreement(p) == AGREEMENT


def test_agreement_lines_report_both_audits_and_the_tie():
    lines = score.agreement_lines(AGREEMENT)
    text = "\n".join(lines)
    assert "precision audit" in text and "94%" in text and "kappa 0.81" in text
    assert "6 disagreements resolved to ok" in text
    assert "key audit" in text and "90%" in text and "kappa 0.70" in text
    assert "10 disagreements resolved to real" in text
    assert score.agreement_lines(None) == []
    assert score.agreement_lines({"key_audit": AGREEMENT["key_audit"]})[0].startswith(
        "- labeller agreement, key audit")


def test_report_prints_key_noise_corrected_numbers_next_to_the_raw_gate():
    m = score.production_metrics(KEY_FLAGGED, LOADED, set(), KEY_LABELS | {500: "ok"},
                                 loaded=LOADED, flip_audit=KEY_LABELS)
    text = _render(lambda c, *a: score.print_production_report(c, *a, agreement=AGREEMENT),
                   m, live_run(), 0)
    assert "key-noise corrected (LLM-labelled audit)" in text
    assert "key precision 0.67" in text
    assert "recall vs audited-real flips 0.80" in text
    assert "corrected recall over all 100 loaded flips 0.89" in text
    assert "recall (key-noise corrected) ≥ 0.85: PASS" in text
    assert "kappa 0.81" in text and "recall on planted flips" in text  # raw row kept
    assert "GATE" in text


def test_report_without_a_key_audit_says_it_is_pending():
    m = score.production_metrics(**prod_inputs())
    text = _render(score.print_production_report, m, live_run(), 0)
    assert "recall (key-noise corrected) ≥ 0.85: PENDING (key audit not labelled)" in text
    assert "key-noise corrected (LLM-labelled audit)" not in text


def test_append_records_corrected_numbers_the_gate_line_and_the_protocol(tmp_path):
    path = tmp_path / "e.md"
    m = score.production_metrics(KEY_FLAGGED, LOADED, set(), KEY_LABELS | {500: "ok"},
                                 loaded=LOADED, flip_audit=KEY_LABELS)
    run = live_run(tested=5, missing=5, inserted=5, pack_rows=5)
    score.append_production_report(path, m, run, "w", 0, agreement=AGREEMENT)
    text = path.read_text()
    assert PROTOCOL in text
    assert "key-noise corrected (LLM-labelled audit)" in text
    assert "key precision 0.67 (95% Wilson" in text and "n=15" in text
    assert "recall vs audited-real flips 0.80" in text
    assert "recall (key-noise corrected) ≥ 0.85: PASS" in text
    assert "kappa 0.81" in text and "kappa 0.70" in text
    # the raw recall and the raw gate line are still there, unchanged in form
    assert "- Jev: recall 0.80 on 100 planted flips" in text
    assert text.count("**Gate:") == 1
    assert text.index("**Gate:") < text.index("recall (key-noise corrected) ≥ 0.85")


def test_append_without_any_llm_audit_has_no_protocol_sentence(tmp_path):
    path = tmp_path / "e.md"
    m = score.production_metrics(**prod_inputs())
    score.append_production_report(path, m, live_run(tested=1, missing=1, inserted=1,
                                                     pack_rows=1), "w", 0)
    text = path.read_text()
    assert PROTOCOL not in text and "key-noise corrected (LLM-labelled audit)" not in text
    assert "recall (key-noise corrected) ≥ 0.85: PENDING" in text


def test_production_committed_paths():
    assert score.FLIP_LABELS_PATH == ROOT / "eval" / "production_flip_audit_labels.csv"
    assert score.AGREEMENT_PATH == ROOT / "eval" / "production_audit_agreement.json"


def test_main_production_reads_the_key_audit_and_agreement_files(tmp_path, monkeypatch):
    from argparse import Namespace

    from rich.console import Console

    flips = tmp_path / "flips.csv"
    flips.write_text("id,original_stars,planted_stars\n" + "".join(
        f"{i},5,1\n" for i in sorted(LOADED)))
    labels = tmp_path / "labels.csv"
    labels.write_text("id,label\n500,real\n501,ok\n")
    flip_labels = tmp_path / "flip_labels.csv"
    flip_labels.write_text("id,label\n" + "".join(f"{i},{v}\n" for i, v in KEY_LABELS.items()))
    agreement = tmp_path / "agreement.json"
    agreement.write_text(json.dumps(AGREEMENT))
    docs = tmp_path / "eval-results.md"
    monkeypatch.setattr(score, "ROOT", tmp_path)
    for name, value in dict(FLIPS_PATH=flips, LABELS_PATH=labels, FLIP_LABELS_PATH=flip_labels,
                            AGREEMENT_PATH=agreement, DOCS_PATH=docs,
                            AUDIT_SAMPLE_PATH=tmp_path / "none.csv").items():
        monkeypatch.setattr(score, name, value)
    run = live_run(tested=5, missing=5, inserted=5, pack_rows=5)
    monkeypatch.setattr(score, "_obtain_run", lambda *a, **k: (run, None))
    monkeypatch.setattr(score, "load_flagged", lambda sql, table, id_col, judged_only=False: (
        KEY_FLAGGED if "baseline" not in table else set()))
    monkeypatch.setattr(score, "load_loaded", lambda sql, ids: set(LOADED))
    monkeypatch.setattr(score, "load_sources", lambda *a, **k: [])
    console = Console(record=True, width=140)
    args = Namespace(append=True, rerun=False, run=True, mode="live")
    assert score._main_production(console, None, args, "w") == 0
    out = console.export_text()
    assert "key precision 0.67" in out and "kappa 0.81" in out
    text = docs.read_text()
    assert PROTOCOL in text and "recall (key-noise corrected) ≥ 0.85: PASS" in text
    assert "- Jev: recall 0.80 on 100 planted flips" in text


def test_main_production_without_key_audit_files_is_pending(tmp_path, monkeypatch):
    from argparse import Namespace

    from rich.console import Console

    flips = tmp_path / "flips.csv"
    flips.write_text("id,original_stars,planted_stars\n" + "".join(
        f"{i},5,1\n" for i in sorted(LOADED)))
    for name, value in dict(FLIPS_PATH=flips, LABELS_PATH=tmp_path / "l.csv",
                            FLIP_LABELS_PATH=tmp_path / "fl.csv",
                            AGREEMENT_PATH=tmp_path / "a.json",
                            AUDIT_SAMPLE_PATH=tmp_path / "none.csv").items():
        monkeypatch.setattr(score, name, value)
    monkeypatch.setattr(score, "_obtain_run", lambda *a, **k: (live_run(), None))
    monkeypatch.setattr(score, "load_flagged", lambda *a, **k: KEY_FLAGGED)
    monkeypatch.setattr(score, "load_loaded", lambda sql, ids: set(LOADED))
    console = Console(record=True, width=140)
    args = Namespace(append=False, rerun=False, run=False, mode=None)
    assert score._main_production(console, None, args, None) == 0
    assert "recall (key-noise corrected) ≥ 0.85: PENDING (key audit not labelled)" in (
        console.export_text())


# -- review fixes before labelling -------------------------------------------------------------


def test_appended_corrected_gate_line_says_it_is_a_point_estimate(tmp_path):
    path = tmp_path / "e.md"
    m = score.production_metrics(KEY_FLAGGED, LOADED, set(), KEY_LABELS | {500: "ok"},
                                 loaded=LOADED, flip_audit=KEY_LABELS)
    score.append_production_report(path, m, live_run(tested=5, missing=5, inserted=5,
                                                     pack_rows=5), "w", 0, agreement=AGREEMENT)
    line = next(ln for ln in path.read_text().splitlines()
                if ln.startswith("recall (key-noise corrected)"))
    assert line.endswith("(point estimate, LLM-labelled; see the Wilson interval of "
                         "recall vs audited-real)")


def test_agreement_lines_print_an_undefined_kappa_as_na():
    ag = {"precision_audit": AGREEMENT["precision_audit"] | {"kappa": None}}
    assert "kappa n/a (one label only)" in score.agreement_lines(ag)[0]


@pytest.mark.parametrize("bad", [
    [],
    {"key_audit": "x"},
    {"key_audit": {"n": 1, "agreement": 1.0, "kappa": 1.0, "tie": "real"}},  # no disagreements
    {"key_audit": AGREEMENT["key_audit"] | {"tie": "maybe"}},
    {"precision_audit": {k: v for k, v in AGREEMENT["precision_audit"].items() if k != "n"}},
    {"precision_audit": AGREEMENT["precision_audit"] | {"kappa": "high"}},
])
def test_agreement_lines_reject_a_malformed_file_with_a_clear_message(bad):
    with pytest.raises(ValueError, match="agreement"):
        score.agreement_lines(bad)


def test_read_agreement_rejects_invalid_json_and_names_the_file(tmp_path):
    p = tmp_path / "production_audit_agreement.json"
    p.write_text("{not json")
    with pytest.raises(ValueError, match="production_audit_agreement.json"):
        score.read_agreement(p)


def test_main_production_reports_a_malformed_agreement_file_as_a_clear_exit(tmp_path,
                                                                           monkeypatch):
    from argparse import Namespace

    from rich.console import Console

    flips = tmp_path / "flips.csv"
    flips.write_text("id,original_stars,planted_stars\n1,5,1\n")
    bad = tmp_path / "a.json"
    bad.write_text(json.dumps({"key_audit": {"n": 3}}))
    for name, value in dict(FLIPS_PATH=flips, LABELS_PATH=tmp_path / "l.csv",
                            FLIP_LABELS_PATH=tmp_path / "fl.csv", AGREEMENT_PATH=bad,
                            AUDIT_SAMPLE_PATH=tmp_path / "none.csv").items():
        monkeypatch.setattr(score, name, value)
    monkeypatch.setattr(score, "_obtain_run", lambda *a, **k: (live_run(), None))
    monkeypatch.setattr(score, "load_flagged", lambda *a, **k: {1})
    monkeypatch.setattr(score, "load_loaded", lambda sql, ids: {1})
    with pytest.raises(SystemExit, match="agreement"):
        score._main_production(Console(record=True), None,
                               Namespace(append=False, rerun=False, run=False, mode=None), None)


def test_read_audit_labels_rejects_duplicates_and_extra_columns(tmp_path):
    p = tmp_path / "labels.csv"
    p.write_text("id,label\n1,real\n1,ok\n")
    with pytest.raises(ValueError, match="duplicate"):
        score.read_audit_labels(p)
    p.write_text("id,label,jev_p\n1,real,0.9\n")
    with pytest.raises(ValueError, match="columns"):
        score.read_audit_labels(p)


def test_an_unlabelled_sample_does_not_shadow_the_labels_file(tmp_path):
    import os

    labels, sample = tmp_path / "labels.csv", tmp_path / "sample.csv"
    labels.write_text("id,label\n1,ok\n2,real\n")
    _sample(sample, [(1, ""), (2, "")])
    os.utime(labels, (1_000, 1_000))
    os.utime(sample, (2_000, 2_000))  # newer, but nothing is labelled in it
    got = score.resolve_audit_labels(labels, sample)
    assert got.labels == {1: "ok", 2: "real"} and got.source == "labels" and got.pending is None
    _sample(sample, [(1, "real"), (2, "")])  # partly labelled and newer: still pending
    os.utime(sample, (3_000, 3_000))
    assert "1 of 2" in score.resolve_audit_labels(labels, sample).pending


def test_pending_message_names_the_r26_flow(tmp_path):
    got = score.resolve_audit_labels(tmp_path / "l.csv", tmp_path / "sample.csv")
    assert "audit_sample.py" in got.pending and "--labeller-copies" in got.pending
    assert "audit_merge.py" in got.pending and "label it" not in got.pending
