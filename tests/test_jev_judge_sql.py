import re

import pytest

from tests.dbt_helpers import render


@pytest.fixture(scope="module")
def sql():
    return render("jev_render_judge", {"model_name": "stg_reviews"})


def _sections(text):
    return dict(re.findall(r"-- (\w+)\n(.*?)(?=\n-- \w+\n|\Z)", text, re.S))


@pytest.mark.slow
def test_three_statements(sql):
    assert set(_sections(sql)) == {"count", "insert", "inserted"}


@pytest.mark.slow
def test_insert_packs_by_token_budget_and_row_cap(sql):
    ins = _sections(sql)["insert"]
    assert ins.lstrip().startswith("insert into jev_demo.jev.judgments (")
    assert "left anti join" in ins and "where p is not null" in ins          # cache
    assert "/ 3.0) + 20" in ins                                              # token estimate
    assert "/ 48000)" in ins and "/ 256)" in ins                              # budget, row cap
    assert "REPARTITION(4)" in ins                                            # concurrency
    assert "jev_demo.jev.noul_pack(transform(items, x -> x.state)" in ins     # one call per pack
    assert ins.count("noul_pack(") == 1
    assert "posexplode(items)" in ins and "r.values[pos]" in ins
    assert "est > 30000" in ins and "row exceeds token limit" in ins          # oversized rows


@pytest.mark.slow
def test_cache_read_is_scoped_to_this_question(sql):
    # Unscoped, concurrent hooks (dbt threads) failed on the dev warehouse with
    # DELTA_CONCURRENT_APPEND.ROW_LEVEL_CHANGES: every INSERT reads judgments, and Delta checks
    # that read's predicate against rows other hooks append meanwhile. The key contains the
    # question, so scoping the read to it changes no result and removes the conflict.
    sections = _sections(sql)
    question = re.search(r"x -> x\.state\), ('(?:[^'\\]|\\.)*')", sections["insert"]).group(1)
    for name in ("count", "insert"):
        read = re.search(r"left anti join \((.*?)\) done", sections[name], re.S).group(1)
        assert read.split() == ["select", "key", "from", "jev_demo.jev.judgments", "where", "p",
                                "is", "not", "null", "and", "question", "="] + question.split()


@pytest.mark.slow
def test_key_matches_the_test_macro(sql):
    ins = _sections(sql)["insert"]
    assert "sha2(concat_ws(chr(31), 'jev-1.13.0', 'live', 'nested', " in ins
    assert "to_json(named_struct('body', " in ins and "'stars', " in ins


@pytest.mark.slow
def test_demo_mode_uses_demo_function():
    demo = render("jev_render_judge", {"model_name": "stg_reviews"}, env={"JEV_MODE": "demo"})
    assert "jev_demo.jev.noul_pack_demo(" in demo and "'demo', 'nested'" in demo


@pytest.mark.slow
def test_model_without_semantic_tests_renders_nothing():
    assert render("jev_render_judge", {"model_name": "stg_orders"}).strip() == ""
