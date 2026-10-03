import pytest

from jevdbx import evallog

MD = """# Eval results
## 2026-10-03T10:00:00Z · pilot · databricks-gpt-oss-20b
- tokens/row banking_query_not_about_intent in 310 out 140 (measured)
- llm cost $0.012 (measured)
## 2026-10-03T11:00:00Z · pass 1 · databricks-gpt-oss-20b
- llm cost $0.40 (estimated)
"""


def test_spend_and_tokens_per_row():
    assert evallog.llm_spend(MD) == 0.412
    assert evallog.tokens_per_row(MD, "databricks-gpt-oss-20b",
                                  "banking_query_not_about_intent") == (310, 140)
    assert evallog.tokens_per_row(MD, "databricks-gpt-oss-20b", "other") is None


def test_measured_entry_replaces_the_estimate_of_its_invocation():
    md = ("## a · pass 1 · x\n- invocation inv-1\n- llm cost $0.40 (estimated)\n"
          "## b · measured cost · pass 1 · x\n- invocation inv-1\n- llm cost $0.31 (measured)\n"
          "## c · pass 1 · y\n- invocation inv-2\n- llm cost $0.10 (estimated)\n")
    assert evallog.llm_spend(md) == 0.41


def test_append_and_preregistration(tmp_path):
    p = tmp_path / "e.md"
    p.write_text("# Eval results\n")
    evallog.append(p, "## x\n- y\n")
    assert p.read_text().endswith("\n## x\n- y\n")
    assert not evallog.has_preregistration(p.read_text())
    assert evallog.has_preregistration("## Pre-registration (frozen before pass 1)\n")


@pytest.mark.parametrize("line", ["- llm cost $0.40 (estimated)\r", "- llm cost $0.40 (estimated) ",
                                  "- llm cost $0.40 (guessed)", "- llm cost 0.40 (measured)"])
def test_spend_fails_loudly_on_a_cost_line_it_cannot_parse(line):
    md = f"## a · pass 1 · x\n- invocation inv-1\n{line}\n"
    with pytest.raises(ValueError, match="llm cost"):
        evallog.llm_spend(md)
