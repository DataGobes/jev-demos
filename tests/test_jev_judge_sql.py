import re

import pytest

from tests.dbt_helpers import BENCH, dbt, render

LLM = "databricks-meta-llama-3-3-70b-instruct"
MODEL = "stg_wanderbricks_reviews"
TEST = "wanderbricks_comment_contradicts_rating"


def _sections(text):
    return dict(re.findall(r"-- (\w+)\n(.*?)(?=\n-- \w+\n|\Z)", text, re.S))


@pytest.mark.slow
def test_jev_path_is_demo05s_pack_path_with_judge_column():
    ins = _sections(render("jev_render_judge", {"model_name": MODEL}))["insert"]
    assert ins.lstrip().startswith("insert into jev_demo.bench.judgments (")
    assert "key, judge, test_name" in ins and "p, decision, requested_model" in ins
    assert "jev_demo.jev.noul_pack(transform(items, x -> x.state)" in ins
    assert "(p is not null or decision is not null)" in ins
    assert "ai_query(" not in ins


@pytest.mark.slow
def test_llm_path_is_one_row_wise_ai_query_statement():
    s = _sections(render("jev_render_judge", {"model_name": MODEL}, vars={"judge": LLM}))
    ins = s["insert"]
    assert ins.count("ai_query(") == 1 and "noul_pack" not in ins
    assert "from_json(r.result, 'decision BOOLEAN, probability DOUBLE')" in ins
    assert "unparseable response" in ins and "r.errorMessage" in ins
    assert "'row'" in ins and f"'{LLM}'" in ins
    assert "count_if(false) as oversized" in s["count"]


@pytest.mark.slow
def test_llm_demo_path_calls_llm_demo():
    ins = _sections(render("jev_render_judge", {"model_name": MODEL},
                           env={"JEV_MODE": "demo"}, vars={"judge": LLM}))["insert"]
    assert f"jev_demo.bench.llm_demo('{LLM}', concat(" in ins and "ai_query(" not in ins


@pytest.mark.slow
def test_expect_compiles_with_judge_specific_flag_rule():
    jev = dbt("compile", "--select", TEST)
    assert jev.returncode == 0, jev.stdout
    llm = dbt("compile", "--select", TEST, "--vars", f"{{judge: {LLM}}}")
    assert llm.returncode == 0, llm.stdout
    assert "judged.p >= 0.8" in jev.stdout and "judged.decision = true" in llm.stdout


@pytest.mark.slow
@pytest.mark.parametrize("dups, verdict", [(0, "OK"), (2, "VIOLATED")])
def test_llm_summary_counts_duplicate_keys_in_once_per_row(dups, verdict):
    out = render("jev_render_llm_summary", {"inserted": 5, "missing": 5, "dups": dups},
                 vars={"judge": LLM})
    line = f"LLM · once-per-row {verdict} · LIVE: 5 inserted = 5 missing · {dups} duplicate keys"
    assert line in out
    assert f"ok={dups == 0}" in out


def test_summary_reads_duplicate_keys_before_the_judge_branch():
    text = (BENCH / "macros" / "jev_summary.sql").read_text()
    dup = text.index("having count(*) > 1")
    assert text.index("set hooks") < text.index("hooks == 0") < dup < text.index("if jev_is_llm()")
    assert "where p is not null or decision is not null group by key" in text
