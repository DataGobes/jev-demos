"""Helpers for the notebook's results-only mode and for reading docs/eval-results.md.

Pure functions: they build SQL text and format numbers; the notebook runs the SQL with `spark.sql`
(no token needed) and calls no Jev function. Stdlib only.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from jevdbx.deploy import sql_string
from jevdbx.pricing import PRICE_PER_MTOK_USD, cost_usd

LEDGER = "jev_demo.jev"
AUDIT = "jev_demo.jaffle_shop_dbt_test__audit"  # where store_failures writes the failing rows

# Same names as scripts/score.py (TESTS, PROD_TEST); a test keeps them equal.
YARDSTICK_TESTS = [
    "customers_full_name_is_a_person",
    "returns_comment_matches_reason_code",
    "reviews_body_matches_stars",
    "tickets_body_has_no_pii",
]
PRODUCTION_TESTS = ["product_reviews_body_matches_stars"]

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def scored_tests(selection: str) -> list[str]:
    if selection == "yardstick":
        return list(YARDSTICK_TESTS)
    if selection == "production":
        return list(PRODUCTION_TESTS)
    raise ValueError(f"selection must be yardstick or production, got {selection!r}")


def entry_for(md: str, invocation: str) -> str | None:
    """The `## ...` block of `md` whose own `- invocation <id>` line names `invocation`, verbatim
    (heading through the line before the next `## ` heading), or None. Only that exact line
    matches: an id quoted elsewhere in an entry (cached judgments) or in prose does not."""
    invocation = invocation.strip()
    if not invocation:
        return None
    wanted = f"- invocation {invocation}"
    block: list[str] = []
    for line in md.splitlines():
        if line.startswith("## "):
            if block and any(b.rstrip() == wanted for b in block):
                break
            block = [line]
        elif block:
            block.append(line)
    else:
        if not any(b.rstrip() == wanted for b in block):
            return None
    return "\n".join(block).strip()


def _in_list(names: list[str]) -> str:
    for n in names:
        if not _IDENT.match(n):
            raise ValueError(f"not a safe test name: {n!r}")
    return ", ".join(sql_string(n) for n in names)


def latest_live_invocation_sql(tests: list[str]) -> str:
    """The newest live dbt invocation whose hook_runs cover every scored test (a partial
    invocation, or one in demo mode, never qualifies). Columns: invocation_id, recorded_micros."""
    return (
        "select invocation_id, unix_micros(max(recorded_at)) as recorded_micros "
        f"from {LEDGER}.hook_runs "
        f"where mode = 'live' and test_name in ({_in_list(tests)}) "
        f"group by invocation_id having count(distinct test_name) = {len(tests)} "
        "order by max(recorded_at) desc limit 1"
    )


def utc_stamp(micros: int) -> str:
    """An epoch-microseconds timestamp as UTC, to the second: 2026-10-01T03:54:19Z."""
    return datetime.fromtimestamp(int(micros) // 1_000_000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def figures_sql(invocation: str, tests: list[str]) -> str:
    """One row of ledger figures for exactly this invocation and these tests. Columns: tested,
    missing, unjudged, requests, tokens, retries, throttled (429s), span_s, model."""
    inv, names = sql_string(invocation), _in_list(tests)
    return (
        "select h.tested, h.missing, j.unjudged, r.requests, r.tokens, r.retries, r.throttled, "
        "r.span_s, r.model "
        "from (select coalesce(sum(tested), 0) as tested, coalesce(sum(missing), 0) as missing "
        f"from {LEDGER}.hook_runs where invocation_id = {inv} and test_name in ({names})) h "
        f"cross join (select count_if(p is null) as unjudged from {LEDGER}.judgments "
        f"where invocation_id = {inv} and test_name in ({names})) j "
        "cross join (select count(*) as requests, coalesce(sum(pack_tokens), 0) as tokens, "
        "coalesce(sum(greatest(attempts - 1, 0)), 0) as retries, "
        "coalesce(sum(greatest(size(filter(retry_statuses, s -> s = 429)), 0)), 0) as throttled, "
        "coalesce((unix_micros(max(finished_at)) - unix_micros(min(started_at))) / 1e6, 0) "
        "as span_s, max(answered_model) as model "
        f"from {LEDGER}.requests where invocation_id = {inv} and test_name in ({names})) r"
    )


@dataclass(frozen=True)
class Figures:
    tested: int
    missing: int
    unjudged: int
    requests: int
    tokens: int
    retries: int
    throttled: int
    span_s: float
    model: str

    @property
    def judgments(self) -> int:
        """Distinct (test, state) pairs with a successful judgment, as in the dbt summary line."""
        return self.tested - self.unjudged

    @property
    def cached_pct(self) -> float:
        return (self.tested - self.missing) * 100 / self.tested if self.tested else 0.0

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.tokens)


def figures_from_row(row) -> Figures:
    tested, missing, unjudged, requests, tokens, retries, throttled, span_s, model = row
    return Figures(int(tested), int(missing), int(unjudged), int(requests), int(tokens),
                   int(retries), int(throttled), float(span_s), model or "")


def figure_lines(invocation: str, f: Figures) -> list[str]:
    """The invocation's numbers, labelled LIVE (this mode only shows live runs)."""
    return [
        f"LIVE · invocation {invocation} · {f.model}",
        f"states judged  {f.judgments:,} ({f.cached_pct:.0f}% cached)",
        f"requests       {f.requests:,}",
        f"retries        {f.retries:,} ({f.throttled:,}× 429)",
        f"input tokens   {f.tokens:,}",
        f"Jev cost       ${f.cost_usd:.3f} (tokens × {PRICE_PER_MTOK_USD} / 1e6)",
        f"Jev span       {f.span_s:.1f} s",
    ]


def stored_failures_sql(test: str, invocation: str) -> str:
    """How many stored failing rows a test has, and how many of them were written by this
    invocation in live mode. Columns: total, matching."""
    if not _IDENT.match(test):
        raise ValueError(f"not a safe test name: {test!r}")
    return (
        "select count(*) as total, "
        f"count_if(jev_invocation_id = {sql_string(invocation)} and jev_mode = 'live') "
        f"as matching from {AUDIT}.{test}"
    )


def failure_rows_status(total: int, matching: int) -> str:
    """`show` when every stored row is the chosen live invocation's, `empty` when there are none,
    `mismatch` when any row comes from another run or mode."""
    if total == 0:
        return "empty"
    return "show" if matching == total else "mismatch"
