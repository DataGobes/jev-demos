import pytest

from jevdbx import keys
from tests.dbt_helpers import dbt


@pytest.mark.slow
def test_project_parses_with_three_semantic_tests_and_two_baselines():
    out = dbt("ls", "--resource-type", "test", "--select", "tag:semantic tag:baseline")
    names = {line.split(".")[-1] for line in out.stdout.split() if line.startswith("bench.")}
    assert {"banking_query_not_about_intent", "pairs_describe_same_product",
            "wanderbricks_comment_contradicts_rating", "baseline_banking_keyword",
            "baseline_pairs_jaccard"} <= names


def test_python_tokens_match_the_sql_baseline_rule():
    # SQL: lower, drop '-', split on non [a-z0-9] runs, distinct
    assert keys.tokens("Sony KDL-40 Bravia, 40in") == {"sony", "kdl40", "bravia", "40in"}


def test_keyword_baseline_lowercases_the_intent_before_splitting():
    from pathlib import Path
    sql = (Path(__file__).parents[1] / "bench" / "tests" / "baseline"
           / "baseline_banking_keyword.sql").read_text()
    assert "split(lower(intent), '_')" in sql  # Refund_not_showing_up must match "refund"
