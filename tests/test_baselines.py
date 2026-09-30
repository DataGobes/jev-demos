"""The Spark port must use exactly demo 04's patterns: same regexes, same conditions."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DEMO4 = Path.home() / "Projects/jev-demo-4/jaffle_shop/tests/baseline"
NAMES = ["customers_full_name_is_a_person", "returns_comment_matches_reason_code",
         "reviews_body_matches_stars", "tickets_body_has_no_pii"]

_LIT = re.compile(r"'((?:[^']|'')*)'")


def _patterns(sql: str, spark: bool) -> list[str]:
    pats = [m.group(1) for m in _LIT.finditer(sql)]
    return [p.replace("\\\\", "\\") if spark else p for p in pats]


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
    extract_all = r"(size\(regexp_extract_all\(lower\(body\), '(?:[^']|'')*')\)"
    ported = re.sub(extract_all, r"\1, 0)", ported)
    assert _normalize(ours) == ported
