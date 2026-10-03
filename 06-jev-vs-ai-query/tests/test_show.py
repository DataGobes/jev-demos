import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


show = _load("show")
score = _load("score")

MD = (
    "## 2026-10-05T09:00:00Z · pass 1 · jev\n"
    "\n"
    "- invocation a\n"
    "- scope sample · 2,000 rows in scope\n"
    "\n"
    "| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |\n"
    "|---|---|---|---|---|---|---|---|\n"
    "| banking_query_not_about_intent | 2,000 | 150 | 140 | 0.90 (0.84–0.94) | 0.84 (0.77–0.89) | 0.87 | 0 |\n"  # noqa: E501
    "\n"
    "## 2026-10-05T10:00:00Z · pass 1 · databricks-gpt-oss-20b\n"
    "\n"
    "- invocation b\n"
    "- scope sample · 2,000 rows in scope\n"
    "- llm cost $0.410 (measured)\n"
    "\n"
    "| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |\n"
    "|---|---|---|---|---|---|---|---|\n"
    "| banking_query_not_about_intent | 2,000 | 150 | 150 | 0.80 (0.73–0.86) | 0.80 (0.73–0.86) | 0.80 | 2 |\n"  # noqa: E501
)


def test_board_reads_the_latest_entry_per_judge_from_the_log_only():
    assert show.board_rows(MD) == [
        ("jev", "sample", "banking_query_not_about_intent", "0.87", "-"),
        ("databricks-gpt-oss-20b", "sample", "banking_query_not_about_intent", "0.80",
         "$0.410 (measured)"),
    ]


LLM = "databricks-gpt-oss-20b"
T = "banking_query_not_about_intent"


def _row(f1, name=T):
    return f"| {name} | 2,000 | 150 | 140 | 0.90 (0.84–0.94) | 0.84 (0.77–0.89) | {f1} | 0 |"


def _entry(stamp, label, judge, inv, scope, f1, cost=0.0, rows=None):
    return score.entry_md(stamp, label, judge, inv, rows or [_row(f1)], cost, "estimated", {},
                          [f"- scope {scope} · 2,000 rows in scope · scored on judged rows"])


LOG = "# Eval results\n\n" + "\n".join([
    "## Pre-registration (frozen before pass 1)\n\n- frozen digest " + "ab" * 32 + "\n",
    _entry("t1", "pass 1", "jev", "j1", "sample", "0.70"),
    _entry("t2", "pass 1", LLM, "l1", "sample", "0.60", 0.4),
    _entry("t3", "pass 1", "jev", "j2", "sample", "0.71",
           rows=[_row("0.71"), _row("0.10", "baseline_banking_keyword")]),
    _entry("t4", "pass 3", "jev", "j3", "full", "0.90"),
    _entry("t5", "pass 2", LLM, "l2", "sample", "0.55", 0.4),
    score.refused_md("2026-10-02T07:20:03Z", "pass 1", LLM, set(), 0.9, ["dbt exited 1"],
                     ("a", "b")),
    "## t7 · measured cost · pass 1 · " + LLM + "\n\n- invocation l1\n"
    "- llm cost $0.350 (measured)\n",
])


def test_default_board_is_pass_1_sample_latest_entry_per_judge():
    assert show.board_rows(LOG) == [
        ("jev", "sample", T, "0.71", "-"),
        (LLM, "sample", T, "0.60", "$0.350 (measured)"),   # the later measurement replaces it
    ]


def test_board_selects_pass_and_scope():
    assert show.board_rows(LOG, pass_=3, scope="full") == [("jev", "full", T, "0.90", "-")]
    assert show.board_rows(LOG, pass_=2) == [(LLM, "sample", T, "0.55", "$0.400 (estimated)")]
    assert show.board_rows(LOG, pass_=3) == []


def test_usage_on_no_or_unknown_subcommand(capsys):
    assert show.main([]) == 2
    assert show.main(["boards"]) == 2
    assert "usage: show.py tests | board [--pass N] [--scope" in capsys.readouterr().err
