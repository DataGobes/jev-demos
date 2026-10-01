import pytest

from jevdbx import budget


def test_prices_per_endpoint():
    assert budget.cost_usd("databricks-gpt-oss-20b", 1_000_000, 1_000_000) == pytest.approx(0.37)
    assert budget.cost_usd("databricks-claude-opus-5", 1_000_000, 0) == pytest.approx(5.0)


def test_projection_and_guard():
    p = budget.project("databricks-meta-llama-3-3-70b-instruct", 2000, (300, 25))
    assert p == pytest.approx(2000 * (300 * 0.50 + 25 * 1.50) / 1e6)
    budget.check(spent=10.0, projected=4.9)
    with pytest.raises(budget.BudgetExceeded):
        budget.check(spent=10.0, projected=5.1)


def test_usage_sql_reads_my_endpoint_usage_in_a_window():
    sql = budget.usage_sql("2026-10-01", "2026-10-02T10:00:00")
    assert "system.serving.endpoint_usage" in sql and "served_entities" not in sql
    assert "requester = current_user()" in sql and "group by served_entity_id" in sql
    assert ">= timestamp'2026-10-01'" in sql and "< timestamp'2026-10-02T10:00:00'" in sql


def test_window_cost_needs_exactly_one_served_entity():
    rows = [["e1", "3", "600", "90"]]
    assert budget.window_cost("databricks-gpt-oss-20b", rows) == (
        budget.cost_usd("databricks-gpt-oss-20b", 600, 90), 3, 600, 90)
    assert budget.window_cost("databricks-gpt-oss-20b", []) is None
    assert budget.window_cost("databricks-gpt-oss-20b", [*rows, ["e2", "1", "5", "5"]]) is None
