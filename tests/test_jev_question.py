import json
import re

import pytest

from tests.dbt_helpers import render

FAILS_IF = "The customer's `query` is not about its labelled `intent`."
CRITERIA = {"true": "The `query` asks about another topic", "false": "Fits `intent`"}
ARGS = {"column_name": "query", "context": ["intent"], "fails_if": FAILS_IF, "criteria": CRITERIA}
LLM = "databricks-claude-opus-5"


@pytest.mark.slow
def test_prompt_carries_the_same_sentence_and_criteria_as_jev_question():
    q = json.loads(render("jev_render_question", {"fails_if": FAILS_IF, "criteria": CRITERIA}))
    prompt = render("jev_render_prompt", ARGS)
    # the literals in the SQL escape quotes as \' ; compare after unescaping
    flat = prompt.replace("\\'", "'")
    assert q["instructions"] in flat
    assert q["criteria"]["true"] in flat and q["criteria"]["false"] in flat
    # identifier quoting is adapter-specific (backticks on Databricks, double quotes on the
    # offline DuckDB render target), so match either
    qt = "[`\"]"
    assert re.search(
        rf"to_json\(named_struct\('query', {qt}query{qt}, 'intent', {qt}intent{qt}\)\)", prompt
    )
    assert "record.query" in flat  # backticked fields are rewritten exactly as for Jev


@pytest.mark.slow
def test_key_depends_on_judge_layout_and_prompt_version():
    jev = render("jev_render_key", ARGS)
    llm = render("jev_render_key", ARGS, vars={"judge": LLM})
    assert "'jev-1.13.0'" in jev and "'nested'" in jev and "'p1'" in jev
    assert f"'{LLM}'" in llm and "'row'" in llm
    assert jev != llm


@pytest.mark.slow
def test_unknown_judge_is_rejected():
    from tests.dbt_helpers import dbt
    out = dbt("run-operation", "jev_render_llm_call", "--vars", json.dumps({"judge": "gpt-9"}))
    assert out.returncode != 0 and "judge must be 'jev' or one of" in out.stdout


@pytest.mark.slow
def test_llm_call_live_uses_ai_query_with_schema_temperature_and_no_fail():
    call = render("jev_render_llm_call", {}, vars={"judge": "databricks-gpt-oss-20b"})
    assert call.startswith("ai_query('databricks-gpt-oss-20b', 'P'")
    assert "responseFormat => '{\"type\": \"json_schema\"" in call
    assert "named_struct('temperature', 0.0, 'reasoning_effort', 'low')" in call
    assert call.endswith("failOnError => false)")
    sonnet = render("jev_render_llm_call", {}, vars={"judge": LLM})
    assert "reasoning_effort" not in sonnet


@pytest.mark.slow
def test_llm_call_demo_uses_the_simulated_stand_in():
    call = render("jev_render_llm_call", {}, env={"JEV_MODE": "demo"}, vars={"judge": LLM})
    assert call == f"jev_demo.bench.llm_demo('{LLM}', 'P')"
