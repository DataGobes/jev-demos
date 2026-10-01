import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("show", ROOT / "scripts" / "show.py")
show = importlib.util.module_from_spec(spec)
spec.loader.exec_module(show)

MD = (
    "## 2026-10-05T09:00:00Z · pass 1 · jev\n"
    "\n"
    "- invocation a\n"
    "\n"
    "| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |\n"
    "|---|---|---|---|---|---|---|---|\n"
    "| banking_query_not_about_intent | 2,000 | 150 | 140 | 0.90 (0.84–0.94) | 0.84 (0.77–0.89) | 0.87 | 0 |\n"  # noqa: E501
    "\n"
    "## 2026-10-05T10:00:00Z · pass 1 · databricks-gpt-oss-20b\n"
    "\n"
    "- invocation b\n"
    "- llm cost $0.410 (measured)\n"
    "\n"
    "| test | rows | positives | flagged | P (95% CI) | R (95% CI) | F1 | unjudged |\n"
    "|---|---|---|---|---|---|---|---|\n"
    "| banking_query_not_about_intent | 2,000 | 150 | 150 | 0.80 (0.73–0.86) | 0.80 (0.73–0.86) | 0.80 | 2 |\n"  # noqa: E501
)


def test_board_reads_the_latest_entry_per_judge_from_the_log_only():
    assert show.board_rows(MD) == [
        ("jev", "banking_query_not_about_intent", "0.87", "-"),
        ("databricks-gpt-oss-20b", "banking_query_not_about_intent", "0.80", "$0.410 (measured)"),
    ]
