import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("score", ROOT / "scripts" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def test_three_tests_with_id_and_state_columns():
    assert set(score.TESTS) == {"banking_query_not_about_intent", "pairs_describe_same_product",
                                "wanderbricks_comment_contradicts_rating"}
    assert score.TESTS["banking_query_not_about_intent"].state_cols == ["query", "intent"]
    assert score.TESTS["pairs_describe_same_product"].state_cols == ["left_record", "right_record"]


def test_state_expr_matches_the_macro():
    # the macro renders to_json(named_struct('query', `query`, 'intent', `intent`))
    assert score.state_expr(["query", "intent"]) == \
        "to_json(named_struct('query', `query`, 'intent', `intent`))"


def test_simulated_or_mixed_runs_are_refused_for_append():
    assert score.refuse_reasons("demo", "jev", {"a"}, 0) == ["SIMULATED runs are never logged"]
    assert "stored failures from more than one invocation" in score.refuse_reasons(
        "live", "jev", {"a", "b"}, 0)[0]
    assert score.refuse_reasons("live", "jev", {"a"}, 0) == []


def test_entry_names_pass_judge_and_cost_source():
    md = score.entry_md(stamp="2026-10-05T09:00:00Z", label="pass 1",
                        judge="databricks-gpt-oss-20b", invocation="inv-1", rows=[], cost=0.41,
                        cost_source="estimated", tokens_per_row={},
                        extra=["- requests 4,615 · wall time 812.4 s"])
    assert md.startswith("## 2026-10-05T09:00:00Z · pass 1 · databricks-gpt-oss-20b")
    assert "- invocation inv-1" in md and "- llm cost $0.410 (estimated)" in md
    assert "- requests 4,615 · wall time 812.4 s" in md


def test_unmeasured_lists_estimates_without_a_later_measurement():
    md = ("# Eval results\n"
          "## s1 · pilot · databricks-gpt-oss-20b\n\n- invocation inv-1\n"
          "- llm cost $0.010 (estimated)\n"
          "## s2 · pass 1 · jev\n\n- invocation inv-2\n"
          "## s3 · pass 1 · databricks-gpt-oss-20b\n\n- invocation inv-3\n"
          "- llm cost $0.400 (estimated)\n"
          "## s4 · measured cost · pass 1 · databricks-gpt-oss-20b\n\n- invocation inv-3\n"
          "- llm cost $0.350 (measured)\n")
    assert score.unmeasured(md) == [("pilot", "databricks-gpt-oss-20b", "inv-1")]


def test_swap_recall_splits_random_and_near_miss():
    swaps = [{"query_id": "a", "swap_type": "random"}, {"query_id": "b", "swap_type": "random"},
             {"query_id": "c", "swap_type": "near_miss"}]
    assert score.swap_recall({"a", "c", "z"}, {"a", "b", "c"}, swaps) == {
        "random": (1, 2), "near_miss": (1, 1)}


def test_false_alarms_count_flags_on_clean_natural_states_only():
    assert score.false_alarms({"a", "b", "x"}, natural={"a", "b", "c", "d"},
                              positives={"b"}) == (1, 3)


def test_thresholds_in_schema_match_the_scorer():
    import yaml
    doc = yaml.safe_load((ROOT / "bench" / "models" / "staging" / "schema.yml").read_text())
    found = [t["jev_expect"]["arguments"]["threshold"] for m in doc["models"]
             for c in m.get("columns", []) for t in c.get("data_tests", [])
             if isinstance(t, dict) and "jev_expect" in t]
    assert found == [score.THRESHOLD] * 3


def test_side_md_reports_calibration_thresholded_f1_agreement_and_key_errors():
    uni = {"a", "b", "c", "d"}
    pos = {"a", "b"}
    per_judge = {
        "jev": {"a": (0.95, None), "b": (0.4, None), "c": (0.9, None), "d": (0.1, None)},
        "databricks-gpt-oss-20b": {"a": (0.9, True), "b": (0.9, True), "c": (0.6, True),
                                   "d": (0.2, False)},
    }
    md = score.side_md("t", per_judge, pos, uni)
    assert "| jev | 0.30 |" in md                   # Brier = (0.0025+0.36+0.81+0.01)/4
    llm_line = next(x for x in md.splitlines() if x.startswith("| databricks-gpt-oss-20b |"))
    assert llm_line.endswith("| 1.00 |")             # p >= 0.8 flags exactly a, b
    assert "possible key errors (flagged by every judge, not in the key): c" in md
    assert ("agreement on positives: all 1 · some 0 · none 0 · only jev 0 · "
            "only databricks-gpt-oss-20b 1") in md


class _Res:
    def __init__(self, state="SUCCEEDED", rows=None, error=None):
        self.state, self.rows, self.error = state, rows or [], error


class _FakeSql:
    """Answers each query with the rows of the first registered fragment it contains."""

    def __init__(self, answers):
        self.answers, self.seen = answers, []

    def run(self, text, timeout_s=900):
        self.seen.append(text)
        for fragment, res in self.answers:
            if fragment in text:
                return res
        return _Res()


def test_q_raises_on_a_failed_statement_and_returns_a_good_one(monkeypatch):
    import pytest
    monkeypatch.setattr(score, "_csv", lambda name: [])  # the key files are not under test
    bad = _FakeSql([("select", _Res("FAILED", error="x" * 500))])
    with pytest.raises(RuntimeError, match=r"^query failed: FAILED: x{300}$"):
        score._q(bad, "select 1")
    good = _FakeSql([("select", _Res(rows=[[1]]))])
    assert score._q(good, "select 1").rows == [[1]]
    spec = score.TESTS["pairs_describe_same_product"]
    for read in (score.universe, score.natural_ids, score.baseline_flags, score.judged_rows):
        with pytest.raises(RuntimeError, match="query failed"):
            read(bad, spec)
    with pytest.raises(RuntimeError, match="query failed"):
        score.positives(bad, score.TESTS["wanderbricks_comment_contradicts_rating"])
    with pytest.raises(RuntimeError, match="query failed"):
        score.stored_flags(bad, spec, "jev", False)
    with pytest.raises(RuntimeError, match="query failed"):
        score.run_stats(bad, "inv-1", False)


def test_refused_md_is_a_cost_only_entry_the_guard_counts():
    from jevdbx import evallog
    md = score.refused_md("s", "pass 1", "databricks-gpt-oss-20b", {"i1", "i2"}, 0.5,
                          ["dbt exited 1"])
    assert md.startswith("## s · refused · pass 1 · databricks-gpt-oss-20b")
    assert "- llm cost $0.500 (estimated)" in md and "- invocation" not in md
    assert evallog.llm_spend(md) == 0.5
    one = score.refused_md("s", "pilot", "jev", {"i1"}, 0.0, ["a", "b"])
    assert "- not a result: a; b" in one and "- invocation i1" in one
    assert score.unmeasured(md) == []


def test_headline2_llm_splits_cost_by_estimated_tokens_per_test():
    per = {"t1": {"judged": 100, "wall_s": 12.0, "est_tokens": 300},
           "t2": {"judged": 50, "wall_s": 3.5, "est_tokens": 100}}
    assert score.headline2_lines(per, 1.0, "measured", True) == [
        "- headline 2 · t1 · judged now 100 · wall time 12.0 s · cost per 1,000 judged rows "
        "$7.5000 (measured, split by estimated tokens)",
        "- headline 2 · t2 · judged now 50 · wall time 3.5 s · cost per 1,000 judged rows "
        "$5.0000 (measured, split by estimated tokens)"]


def test_headline2_jev_uses_the_ledger_and_cached_tests_say_so():
    per = {"t1": {"judged": 1000, "wall_s": 40.0, "jev_cost": 0.21},
           "t2": {"judged": 0, "wall_s": 0.0, "jev_cost": 0.0}}
    assert score.headline2_lines(per, 0.21, "ledger", False) == [
        "- headline 2 · t1 · judged now 1,000 · wall time 40.0 s · cost per 1,000 judged rows "
        "$0.2100 (ledger)",
        "- headline 2 · t2 · judged now 0 · wall time 0.0 s · cost per 1,000 judged rows "
        "n/a (all cached)"]


def test_run_stats_wall_is_first_start_to_last_end_and_splits_by_test():
    sql = _FakeSql([
        ("jev_demo.bench.requests", _Res(rows=[["t1", 4, 1_000_000]])),
        ("group by test_name", _Res(rows=[["t1", 100, 10.5], ["t2", 0, 0.0]])),
        ("from jev_demo.bench.hook_runs", _Res(rows=[[100, 42.0]])),
    ])
    st = score.run_stats(sql, "inv-1", False)
    assert st["judged"] == 100 and st["wall_s"] == 42.0 and st["requests"] == 4
    assert st["per_test"]["t1"] == {"judged": 100, "wall_s": 10.5,
                                    "jev_cost": score.pricing.cost_usd(1_000_000)}
    assert st["per_test"]["t2"]["jev_cost"] == 0.0
    hook_sql = next(q for q in sql.seen if "hook_runs" in q and "group by" not in q)
    assert "unix_micros(max(finished_at)) - unix_micros(min(started_at))" in hook_sql
