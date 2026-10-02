"""The Spark port must use exactly demo 04's patterns: same regexes, same conditions."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DEMO4 = Path.home() / "Projects/jev-demo-4/jaffle_shop/tests/baseline"
NAMES = ["customers_full_name_is_a_person", "returns_comment_matches_reason_code",
         "reviews_body_matches_stars", "tickets_body_has_no_pii"]

_LIT_DUCK = re.compile(r"'((?:[^']|'')*)'")
_LIT_SPARK = re.compile(r"'((?:[^'\\]|\\.|'')*)'")  # also accepts \' and \\ inside a literal
_LIT_STRICT = re.compile(r"'((?:[^'\\]|\\.)*)'")  # how Databricks reads it: '' is not an escape


def _patterns(sql: str, spark: bool) -> list[str]:
    """The regex strings each engine actually receives, after its own literal unescaping."""
    sql = re.sub(r"--[^\n]*", "", sql)  # comments never reach the engine
    if spark:  # SQL-unescape: \X -> X for any X
        return [re.sub(r"\\(.)", r"\1", m.group(1)) for m in _LIT_SPARK.finditer(sql)]
    return [m.group(1).replace("''", "'") for m in _LIT_DUCK.finditer(sql)]


def _normalize(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = sql.replace("regexp_matches(", "regexp(")
    sql = sql.replace("len(regexp_extract_all(", "size(regexp_extract_all(")
    return re.sub(r"\s+", " ", sql)


@pytest.mark.skipif(not DEMO4.exists(), reason="demo 04 checkout not present")
@pytest.mark.parametrize("name", NAMES)
def test_same_patterns_as_demo04(name):
    ours = (ROOT / f"jaffle_shop/tests/baseline/baseline_{name}.sql").read_text()
    theirs = (DEMO4 / f"baseline_{name}.sql").read_text()
    assert _patterns(ours, spark=True) == _patterns(theirs, spark=False)


@pytest.mark.parametrize("name", NAMES)
def test_no_duckdb_only_functions_left(name):
    sql = (ROOT / f"jaffle_shop/tests/baseline/baseline_{name}.sql").read_text()
    assert "regexp_matches(" not in sql and "len(" not in sql
    assert re.search(r"(?<!\\)\\[bdsw.]", sql.replace("\\\\", "")) is None  # every \ doubled


@pytest.mark.skipif(not DEMO4.exists(), reason="demo 04 checkout not present")
@pytest.mark.parametrize("name", NAMES)
def test_only_the_dialect_changed(name):
    """Beyond the regexes: same conditions, same config, same structure (modulo dialect)."""
    ours = (ROOT / f"jaffle_shop/tests/baseline/baseline_{name}.sql").read_text()
    theirs = (DEMO4 / f"baseline_{name}.sql").read_text()
    ported = _normalize(theirs).replace("\\", "\\\\")
    ported = ported.replace("''", "\\'")  # '' is not a quote escape on Databricks; \' is
    extract_all = r"(size\(regexp_extract_all\(lower\(body\), '(?:[^']|'')*')\)"
    ported = re.sub(extract_all, r"\1, 0)", ported)
    assert _normalize(ours) == ported


@pytest.mark.parametrize("name", NAMES)
def test_no_doubled_quote_inside_a_literal(name):
    """Databricks reads '' as two adjacent literals, silently dropping the quote."""
    sql = (ROOT / f"jaffle_shop/tests/baseline/baseline_{name}.sql").read_text()
    sql = re.sub(r"--[^\n]*", "", sql)
    for m in _LIT_STRICT.finditer(sql):
        assert sql[m.end():m.end() + 1] != "'", f"adjacent literals after {m.group(0)!r}"


def test_returns_pattern_keeps_the_apostrophe():
    sql = (ROOT / "jaffle_shop/tests/baseline/baseline_returns_comment_matches_reason_code.sql")
    assert any("don't need" in p for p in _patterns(sql.read_text(), spark=True))
