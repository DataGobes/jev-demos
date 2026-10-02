import argparse
import importlib.util
import re
from pathlib import Path

import pytest

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
    assert score.refuse_reasons("demo", "jev", {"a"}, {}, {}) == ["SIMULATED runs are never logged"]
    assert "stored failures from more than one invocation" in score.refuse_reasons(
        "live", "jev", {"a", "b"}, {}, {})[0]
    assert score.refuse_reasons("live", "jev", {"a"}, {}, {}) == []
    assert score.refuse_reasons("live", "jev", set(), {}, {}) == ["no stored failures read"]


def test_scoring_excludes_unjudged_rows_from_tp_fn_and_tn():
    uni, pos = {"a", "b", "c", "d", "e"}, {"a", "b"}
    s, judged, pos_j = score.judged_scores(flagged={"a"}, unjudged={"b", "e"}, pos=pos, uni=uni)
    assert judged == {"a", "c", "d"} and pos_j == {"a"}
    assert (s.tp, s.fp, s.fn, s.tn) == (1, 0, 0, 2)   # b (unjudged positive) is not a miss


def test_more_than_one_percent_unjudged_is_not_a_result():
    t = "banking_query_not_about_intent"
    ok = score.refuse_reasons("live", "jev", {"a"}, {t: 20}, {t: 2000})       # 1.0%: accepted
    assert ok == []
    bad = score.refuse_reasons("live", "jev", {"a"}, {t: 21}, {t: 2000})      # 1.05%: refused
    assert len(bad) == 1 and t in bad[0] and "21" in bad[0] and "2,000" in bad[0]
    assert "rerun" in bad[0]
    assert score.UNJUDGED_TOLERANCE == 0.01


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
    assert "common universe: 4 ids judged live by every judge" in md
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
    win = ("2026-10-02T07:12:44", "2026-10-02T07:20:02")
    md = score.refused_md("2026-10-02T07:20:03Z", "pass 1", "databricks-gpt-oss-20b",
                          {"i1", "i2"}, 0.5, ["dbt exited 1"], win)
    assert md.startswith("## 2026-10-02T07:20:03Z · refused · pass 1 · databricks-gpt-oss-20b")
    assert "- llm cost $0.500 (estimated)" in md
    assert "- invocation refused-20261002T072003Z" in md          # never without an invocation
    assert "- window 2026-10-02T07:12:44 2026-10-02T07:20:02 (UTC)" in md
    assert evallog.llm_spend(md) == 0.5
    one = score.refused_md("s", "pilot", "jev", {"i1"}, 0.0, ["a", "b"], win)
    assert "- not a result: a; b" in one and "- invocation i1" in one
    assert score.unmeasured(md) == [("refused · pass 1", "databricks-gpt-oss-20b",
                                     "refused-20261002T072003Z")]


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


# ---------------------------------------------------------------- run(): guard, logging, prereg
LLM = "databricks-gpt-oss-20b"
DIGEST = "ab" * 32
UUID = "0f0e0d0c-0b0a-4908-" + "8706-050403020100"  # split: not a workspace GUID


def _args(**kw):
    base = dict(run=True, judge=LLM, scope="sample", pass_=1, mode="live", append=True,
                fresh=False)
    return argparse.Namespace(**(base | kw))


def _ids(test, n):
    return {f"{test[:4]}{i:04d}" for i in range(n)}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """score.run() with every warehouse read and dbt call faked: 200 rows per test, 20 positives,
    18 caught + 2 false alarms, `unjudged` rows per test without a judgment, one invocation."""
    log = tmp_path / "eval-results.md"
    log.write_text(f"# Eval results\n\n{score.evallog.PREREG}\n\n- frozen digest {DIGEST}\n")
    ev = tmp_path / "eval"
    ev.mkdir()
    for name in score.GROUND_TRUTH:
        (ev / name).write_text("x\n")
    st = {"calls": [], "judge_rc": 0, "unjudged": 2, "invs": {UUID}, "raise_on_flags": None,
          "usage": [], "fresh_log": log}

    def fake_dbt(*args):
        st["calls"].append(args)
        return st["judge_rc"] if "+tag:semantic" in args else 0

    def uni(sql, spec):
        return _ids(spec.name, 200)

    def pos(sql, spec):
        return set(sorted(_ids(spec.name, 200))[:20])

    def flags(sql, spec, judge, is_llm):
        if st["raise_on_flags"]:
            raise st["raise_on_flags"]
        ids = sorted(_ids(spec.name, 200))
        unjudged = set(ids[-st["unjudged"]:]) if st["unjudged"] else set()
        return set(ids[:18] + ids[100:102]), unjudged, set(st["invs"])

    def stats(sql, inv, is_llm):
        per = {t: {"judged": 200, "wall_s": 2.0, "est_tokens": 1000, "jev_cost": 0.001}
               for t in score.TESTS}
        return {"requests": 600 if is_llm else 3, "judged": 600, "wall_s": 6.0, "tokens": 12345,
                "per_test": per}

    class Sql:
        def run(self, text, timeout_s=900):
            if "system.serving.endpoint_usage" in text:
                return _Res(rows=st["usage"])
            return _Res()

    monkeypatch.setattr(score, "LOG", log)
    monkeypatch.setattr(score, "EVAL", ev)
    monkeypatch.setattr(score, "Sql", Sql)
    monkeypatch.setattr(score, "dbt", fake_dbt)
    monkeypatch.setattr(score, "frozen_dirty", lambda: False)
    monkeypatch.setattr(score, "frozen_digest", lambda: DIGEST)
    monkeypatch.setattr(score, "preflight", lambda sql: [])
    monkeypatch.setattr(score, "universe", uni)
    monkeypatch.setattr(score, "positives", pos)
    monkeypatch.setattr(score, "stored_flags", flags)
    monkeypatch.setattr(score, "baseline_flags", lambda sql, spec: set())
    monkeypatch.setattr(score, "natural_ids", lambda sql, spec: _ids(spec.name, 200))
    monkeypatch.setattr(score, "_csv", lambda name: [])
    monkeypatch.setattr(score, "run_stats", stats)
    monkeypatch.setattr(score, "window_judged",
                        lambda sql, judge, since, until=None: {t: 200 for t in score.TESTS})
    return st


def _judging_builds(st):
    return [c for c in st["calls"] if "+tag:semantic" in c]


def _entries(st):
    """Logged entries after the pre-registration."""
    return [e for e in st["fresh_log"].read_text().split("\n## ")[1:]
            if not e.startswith("Pre-registration")]


def test_live_llm_run_without_append_is_refused_before_any_build(env, capsys):
    assert score.run(_args(append=False)) == 1
    assert env["calls"] == []
    assert "live LLM runs must be logged: pass --append" in capsys.readouterr().out


@pytest.mark.parametrize("problem", ["missing", "dirty", "mismatch"])
def test_live_append_needs_the_preregistration_and_its_frozen_digest(env, monkeypatch, capsys,
                                                                     problem):
    if problem == "missing":
        env["fresh_log"].write_text("# Eval results\n")
    elif problem == "dirty":
        monkeypatch.setattr(score, "frozen_dirty", lambda: True)
    else:
        monkeypatch.setattr(score, "frozen_digest", lambda: "cd" * 32)
    assert score.run(_args(judge="jev")) == 1
    assert env["calls"] == []
    out = capsys.readouterr().out
    assert {"missing": "no pre-registration", "dirty": "uncommitted changes",
            "mismatch": "changed since pre-registration"}[problem] in out


def test_missing_polarity_file_is_refused_before_the_billed_build(env, capsys):
    (score.EVAL / "wanderbricks_polarity.csv").unlink()
    assert score.run(_args()) == 1
    assert _judging_builds(env) == []
    assert "eval/wanderbricks_polarity.csv" in capsys.readouterr().out


def test_failed_preflight_refuses_before_the_billed_build(env, monkeypatch):
    monkeypatch.setattr(score, "preflight", lambda sql: ["3 comments have no polarity label"])
    assert score.run(_args()) == 1
    assert len(env["calls"]) == 1 and _judging_builds(env) == []


def test_failed_judging_build_appends_a_refused_entry_with_window_invocation_and_cost(env):
    env["judge_rc"], env["invs"] = 1, set()
    assert score.run(_args()) == 1
    (entry,) = _entries(env)
    assert entry.split("\n")[0].endswith(f"· refused · pass 1 · {LLM}")
    assert "dbt exited 1" in entry and "no stored failures read" in entry
    assert re.search(r"^- invocation refused-\d{8}T\d{6}Z$", entry, re.M)
    assert re.search(r"^- window \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d \S+ \(UTC\)$", entry, re.M)
    cost = float(re.search(r"^- llm cost \$([0-9.]+) \(estimated\)$", entry, re.M)[1])
    projected = sum(score.budget.project(LLM, 200, score.budget.DEFAULT_TOKENS_PER_ROW[t])
                    for t in score.TESTS)
    assert cost == pytest.approx(projected, abs=1e-3) and cost > 0  # never $0 for a billed run


def test_an_exception_after_the_build_still_appends_a_refused_entry_and_reraises(env):
    env["raise_on_flags"] = RuntimeError("query failed: FAILED: boom")
    with pytest.raises(RuntimeError, match="boom"):
        score.run(_args())
    (entry,) = _entries(env)
    assert "· refused · pass 1 ·" in entry.split("\n")[0]
    assert "RuntimeError: query failed: FAILED: boom" in entry
    assert re.search(r"^- invocation refused-\d{8}T\d{6}Z$", entry, re.M)
    assert re.search(r"^- window ", entry, re.M)
    assert float(re.search(r"^- llm cost \$([0-9.]+)", entry, re.M)[1]) > 0


def test_a_stale_invocation_already_in_the_log_is_never_reused(env):
    env["fresh_log"].write_text(env["fresh_log"].read_text()
                                + f"\n## s · pass 1 · {LLM}\n\n- invocation {UUID}\n"
                                  "- llm cost $0.400 (estimated)\n")
    env["judge_rc"] = 1
    assert score.run(_args()) == 1
    entry = _entries(env)[-1]
    assert re.search(r"^- invocation refused-\d{8}T\d{6}Z$", entry, re.M)


def test_too_many_unjudged_rows_are_refused_and_logged_as_spend(env):
    env["unjudged"] = 3                                     # 3 of 200 = 1.5% > 1%
    assert score.run(_args()) == 1
    (entry,) = _entries(env)
    assert "· refused ·" in entry.split("\n")[0] and "3 of 200" in entry
    assert f"- invocation {UUID}" in entry


def test_llm_result_entry_scores_judged_rows_and_records_window_and_tokens(env):
    assert score.run(_args()) == 0
    (entry,) = _entries(env)
    assert entry.split("\n")[0].endswith(f"· pass 1 · {LLM}")
    assert f"- invocation {UUID}" in entry and re.search(r"^- window \S+ \S+ \(UTC\)$", entry, re.M)
    assert "- tokens in ~3,000 (estimated)" in entry
    assert "- scope sample · 600 rows in scope · scored on judged rows" in entry
    # 2 unjudged (negatives) excluded: 198 judged rows, 20 positives, 18 + 2 flagged
    assert "| banking_query_not_about_intent | 198 | 20 | 20 | 0.90" in entry
    assert entry.rstrip().endswith("| 2 |")


def test_llm_usage_counts_as_measured_only_when_it_covers_the_judged_rows(env):
    env["usage"] = [["e1", "599", "300000", "90000"]]       # 599 requests < 600 judged now
    assert score.run(_args()) == 0
    entry = _entries(env)[-1]
    assert "(estimated)" in entry and "- usage requests 599 vs judged 600" in entry
    assert "- tokens in ~3,000 (estimated)" in entry


def test_usage_verdict():
    m = (0.1, 600, 300_000, 90_000)
    assert score.usage_verdict(None, 600) == (False, [])
    assert score.usage_verdict(m, 600) == (True, ["- usage requests 600 vs judged 600"])
    assert score.usage_verdict(m, 601)[0] is False                    # usage not landed yet
    assert score.usage_verdict(m, 0)[0] is False                      # nothing judged: never
    ok, lines = score.usage_verdict((0.1, 700, 1, 1), 600)            # > 1.05 x judged
    assert ok and lines[1] == ("- usage check: 700 requests for 600 judged rows "
                               "(possible duplicate evaluation)")


def test_jev_full_scope_entry_has_ledger_tokens_and_the_jaccard_train_label(env):
    assert score.run(_args(judge="jev", scope="full")) == 0
    (entry,) = _entries(env)
    assert "- tokens in 12,345 (ledger)" in entry
    assert "| baseline_pairs_jaccard (threshold fit on train; train in scope) |" in entry
    assert "| baseline_banking_keyword |" in entry
    assert "- llm cost" not in entry and "- window" not in entry


def test_the_guard_uses_the_margin_before_the_billed_build(env, capsys):
    projected = sum(score.budget.project(LLM, 200, score.budget.DEFAULT_TOKENS_PER_ROW[t])
                    for t in score.TESTS)                    # ~$0.059 for the 600 rows in scope
    spent = 14.94                                            # 14.94 + 0.059 <= 15 < 14.94 + 1.15 x
    assert spent + projected <= 15 < spent + 1.15 * projected
    env["fresh_log"].write_text(env["fresh_log"].read_text()
                                + f"\n## s · pass 1 · {LLM}\n\n- invocation i0\n"
                                  f"- llm cost ${spent:.3f} (measured)\n")
    with pytest.raises(score.budget.BudgetExceeded):
        score.run(_args())
    assert _judging_builds(env) == [] and len(_entries(env)) == 1
    assert "1.15 × projected $0.06" in capsys.readouterr().out


# ---------------------------------------------------------------- pre-registration
@pytest.fixture
def prereg_env(tmp_path, monkeypatch):
    log = tmp_path / "eval-results.md"
    log.write_text("# Eval results\n")
    ev = tmp_path / "eval"
    ev.mkdir()
    (ev / "banking77_swaps.csv").write_text("query_id,in_sample\nq1,True\n")
    (ev / "abt_buy_jaccard.txt").write_text("0.2115\n")
    for name in ("wanderbricks_polarity.csv", "wanderbricks_flips.csv"):
        (ev / name).write_text("x\n")
    st = {"rc": 0, "calls": []}
    monkeypatch.setattr(score, "LOG", log)
    monkeypatch.setattr(score, "EVAL", ev)
    monkeypatch.setattr(score, "frozen_dirty", lambda: False)
    monkeypatch.setattr(score, "frozen_digest", lambda: DIGEST)
    monkeypatch.setattr(score, "_git", lambda *a: "abc1234")
    monkeypatch.setattr(score, "dbt", lambda *a: st["calls"].append(a) or st["rc"])
    return st


def test_preregister_records_the_frozen_digest_tolerance_and_margin(prereg_env):
    assert score.preregister() == 0
    md = score.LOG.read_text()
    assert f"- frozen digest {DIGEST}" in md
    assert ("- unjudged tolerance 1% of in-scope rows per test (more is not a result; "
            "rerun to fill)") in md
    assert "- budget margin 1.15 on projections" in md and "- dbt compile exit 0" in md
    assert score.prereg_reasons(md) == []


@pytest.mark.parametrize("problem", ["dirty", "polarity", "flips", "compile"])
def test_preregister_refuses_dirty_paths_missing_keys_and_compile_failure(prereg_env, monkeypatch,
                                                                          problem):
    if problem == "dirty":
        monkeypatch.setattr(score, "frozen_dirty", lambda: True)
    elif problem == "compile":
        prereg_env["rc"] = 2
    else:
        (score.EVAL / f"wanderbricks_{problem}.csv").unlink()
    assert score.preregister() == 1
    assert not score.evallog.has_preregistration(score.LOG.read_text())


def test_frozen_digest_hashes_the_index_of_the_frozen_paths():
    assert score.FROZEN == ["bench/macros", "bench/models", "bench/seeds", "bench/tests",
                            "bench/dbt_project.yml", "eval"]
    d = score.frozen_digest()
    assert re.fullmatch(r"[0-9a-f]{64}", d) and d == score.frozen_digest()


# ---------------------------------------------------------------- measure and compare
def test_measure_settles_a_refused_entry_from_its_window_and_validates_ids(tmp_path, monkeypatch,
                                                                         capsys):
    log = tmp_path / "e.md"
    log.write_text(
        "# Eval results\n"
        f"\n## 2026-10-02T07:20:03Z · refused · pass 1 · {LLM}\n\n- not a result: dbt exited 1\n"
        "- invocation refused-20261002T072003Z\n"
        "- window 2026-10-02T07:12:44 2026-10-02T07:20:02 (UTC)\n- llm cost $0.900 (estimated)\n"
        f"\n## s2 · pass 1 · {LLM}\n\n- invocation x';drop--\n"
        "- llm cost $0.100 (estimated)\n")
    usage = _Res(rows=[["e1", "600", "1000000", "100000"]])
    sql = _FakeSql([("system.serving.endpoint_usage", usage),
                    ("hook_runs", _Res(rows=[["banking_query_not_about_intent", 600]]))])
    monkeypatch.setattr(score, "LOG", log)
    monkeypatch.setattr(score, "Sql", lambda: sql)
    assert score.measure(True) == 1                  # one entry skipped: invalid invocation id
    assert "invalid invocation id" in capsys.readouterr().out
    usage = next(q for q in sql.seen if "endpoint_usage" in q)
    assert ">= timestamp'2026-10-02T07:12:44'" in usage
    assert "< timestamp'2026-10-02T07:20:02'" in usage
    assert not any("drop" in q for q in sql.seen)
    md = log.read_text()
    assert "· measured cost · refused · pass 1 ·" in md
    assert "- usage requests 600 vs judged 600" in md
    assert score.evallog.llm_spend(md) == pytest.approx(
        score.budget.cost_usd(LLM, 1_000_000, 100_000) + 0.1)   # the refused estimate is replaced


def test_measure_keeps_the_estimate_when_usage_does_not_cover_the_judged_rows(tmp_path,
                                                                            monkeypatch):
    log = tmp_path / "e.md"
    log.write_text(f"# Eval results\n\n## s · pass 1 · {LLM}\n\n- invocation {UUID}\n"
                   "- window 2026-10-02T07:12:44 2026-10-02T07:20:02 (UTC)\n"
                   "- llm cost $0.400 (estimated)\n")
    sql = _FakeSql([("system.serving.endpoint_usage", _Res(rows=[["e1", "10", "1000", "100"]])),
                    ("hook_runs", _Res(rows=[[600]]))])
    monkeypatch.setattr(score, "LOG", log)
    monkeypatch.setattr(score, "Sql", lambda: sql)
    assert score.measure(True) == 0
    assert "measured cost" not in log.read_text()


def test_compare_universe_is_the_ids_every_judge_judged():
    per = {"jev": {"a": (0.9, None), "b": (0.1, None), "c": (0.5, None)},
           LLM: {"a": (None, True), "b": (None, False)}}
    assert score.common_universe(per, ["jev", LLM]) == {"a", "b"}


def test_compare_refuses_more_than_one_question_per_test():
    spec = score.TESTS["pairs_describe_same_product"]
    with pytest.raises(RuntimeError, match="2 distinct questions"):
        score.one_question(_FakeSql([("count(distinct question)", _Res(rows=[["2"]]))]), spec)
    score.one_question(_FakeSql([("count(distinct question)", _Res(rows=[["1"]]))]), spec)


def test_side_md_llm_without_probabilities_prints_na_and_bins_join_with_semicolons():
    per = {"jev": {"a": (0.95, None), "b": (0.1, None)},
           LLM: {"a": (None, True), "b": (None, False)}}
    md = score.side_md("t", per, {"a"}, {"a", "b"})
    llm_line = next(x for x in md.splitlines() if x.startswith(f"| {LLM} |"))
    assert llm_line == f"| {LLM} | n/a |  | n/a |"
    jev_line = next(x for x in md.splitlines() if x.startswith("| jev |"))
    assert "0.0-0.2: 0.00, 1; 0.8-1.0: 1.00, 1" in jev_line
