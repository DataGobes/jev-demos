import pytest

from jevviz.parse import VizSyntaxError, extract_viz


def test_no_clause():
    assert extract_viz("SELECT 1") == ("SELECT 1", None)


def test_single_intent_case_insensitive_and_semicolon():
    sql, intents = extract_viz("SELECT a FROM t\nvisualize 'how is a trending';")
    assert sql == "SELECT a FROM t"
    assert intents == ["how is a trending"]


def test_multiple_intents_and_escaped_quote():
    _, intents = extract_viz("SELECT 1 VISUALIZE 'what''s up', 'second'")
    assert intents == ["what's up", "second"]


def test_bare_clause():
    assert extract_viz("SELECT 1 VISUALIZE") == ("SELECT 1", [])


def test_keyword_inside_string_or_comment_is_ignored():
    q = "SELECT 'VISUALIZE ''x''' AS s -- VISUALIZE 'nope'\n/* VISUALIZE 'no' */"
    assert extract_viz(q) == (q, None)


def test_keyword_as_part_of_identifier_is_ignored():
    assert extract_viz("SELECT visualize_me FROM t")[1] is None


def test_garbage_after_clause_raises():
    with pytest.raises(VizSyntaxError):
        extract_viz("SELECT 1 VISUALIZE 'a' LIMIT 5")


def test_too_many_intents_raises():
    with pytest.raises(VizSyntaxError):
        extract_viz("SELECT 1 VISUALIZE " + ", ".join(f"'i{n}'" for n in range(7)))
