"""The $15 LLM budget (Databricks pay-per-token, Azure Premium, $0.070/DBU; prices checked
2026-10-01, re-check before pass 1). Spend so far is read from the eval log's cost lines (a measured
entry written by `score.py --measure` replaces the estimate of its invocation; measured costs come
from system.serving.endpoint_usage attributed by time window). Before an LLM pass the guard refuses
when spend so far + MARGIN × the projected cost of the rows in scope passes the cap."""

DBU_USD = 0.070
# $ per 1M tokens (input, output), Azure Premium at DBU_USD, from the Databricks pricing pages
# (DBU per 1M: gpt-oss-20b 1.000 / 4.286, llama-3.3-70b 7.143 / 21.429).
# opus-5 is an ESTIMATE (S2 replaced sonnet-5-5, which ai_query rejects): verify before the pilot.
PRICES: dict[str, tuple[float, float]] = {
    "databricks-gpt-oss-20b": (0.07, 0.30),
    "databricks-meta-llama-3-3-70b-instruct": (0.50, 1.50),
    # ESTIMATE until verified before the pilot gate (Task 15 Step 5);
    # S2: no Sonnet works with ai_query
    "databricks-claude-opus-5": (5.00, 25.00),
}
CAP_USD = 15.0
MARGIN = 1.15  # on projections: tokens/row and prices are estimates until measured
SINCE = "2026-10-01"
# ESTIMATES (input, output tokens per row) until the pilot measures them
DEFAULT_TOKENS_PER_ROW: dict[str, tuple[int, int]] = {
    "banking_query_not_about_intent": (300, 250),
    "pairs_describe_same_product": (450, 250),
    "wanderbricks_comment_contradicts_rating": (270, 250),
}


class BudgetExceeded(Exception):
    pass


def cost_usd(endpoint: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES[endpoint]
    return round((input_tokens * pin + output_tokens * pout) / 1_000_000, 6)


def project(endpoint: str, rows: int, per_row: tuple[int, int]) -> float:
    return cost_usd(endpoint, rows * per_row[0], rows * per_row[1])


def check(spent: float, projected: float, cap: float = CAP_USD) -> None:
    if spent + MARGIN * projected > cap:
        raise BudgetExceeded(f"spent ${spent:.2f} + {MARGIN} × projected ${projected:.2f} = "
                             f"${spent + MARGIN * projected:.2f} > cap ${cap:.2f}")


def _lit(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def usage_sql(since: str, until: str | None = None) -> str:
    """This user's foundation-model usage per served entity in [since, until). S2 (spec §4):
    served_entities has no rows for the pay-per-token endpoints, so usage is attributed by time
    window (the scorer runs one judge at a time), not by endpoint name."""
    until_sql = f" and request_time < timestamp{_lit(until)}" if until else ""
    return ("select served_entity_id, count(*) as requests, "
            "coalesce(sum(input_token_count), 0) as input_tokens, "
            "coalesce(sum(output_token_count), 0) as output_tokens "
            "from system.serving.endpoint_usage "
            f"where requester = current_user() and request_time >= timestamp{_lit(since)}"
            f"{until_sql} group by served_entity_id")


def window_cost(endpoint: str, rows: list) -> tuple[float, int, int, int] | None:
    """Cost of one judge's window, or None unless exactly one served entity was used (usage not
    landed yet — it lags ~2 h — or another model ran in the same window)."""
    if len(rows) != 1:
        return None
    _, n, i, o = rows[0]
    return cost_usd(endpoint, int(i), int(o)), int(n), int(i), int(o)
