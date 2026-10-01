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


def judging_invocations_sql(tests: list[str]) -> str:
    """The live invocations that made the successful judgments on record for `tests` (their latest
    question; judgments of an older wording do not count), oldest first. Columns: invocation_id,
    states (distinct judged states), requests, tokens, retries, throttled (429s), span_s,
    recorded_micros (when the invocation's hook rows were written). Same scope as score.py."""
    names = _in_list(tests)
    return (
        "with latest as (select test_name, max_by(question, judged_at) as q "
        f"from {LEDGER}.judgments where mode = 'live' and test_name in ({names}) "
        "group by test_name), "
        "src as (select j.invocation_id, count(distinct j.key) as states, "
        "min(j.judged_at) as first_at "
        f"from {LEDGER}.judgments j "
        "join latest l on j.test_name = l.test_name and j.question = l.q "
        "where j.p is not null and j.mode = 'live' group by j.invocation_id), "
        "req as (select invocation_id, count(*) as requests, "
        "coalesce(sum(pack_tokens), 0) as tokens, "
        "coalesce(sum(greatest(attempts - 1, 0)), 0) as retries, "
        "coalesce(sum(greatest(size(filter(retry_statuses, s -> s = 429)), 0)), 0) as throttled, "
        "coalesce((unix_micros(max(finished_at)) - unix_micros(min(started_at))) / 1e6, 0) "
        f"as span from {LEDGER}.requests where mode = 'live' and test_name in ({names}) "
        "group by invocation_id), "
        "hook as (select invocation_id, unix_micros(max(recorded_at)) as recorded_micros "
        f"from {LEDGER}.hook_runs where mode = 'live' and test_name in ({names}) "
        "group by invocation_id) "
        "select s.invocation_id, s.states, coalesce(r.requests, 0), coalesce(r.tokens, 0), "
        "coalesce(r.retries, 0), coalesce(r.throttled, 0), coalesce(r.span, 0), "
        "h.recorded_micros "
        "from src s left join req r on r.invocation_id = s.invocation_id "
        "left join hook h on h.invocation_id = s.invocation_id order by s.first_at"
    )


@dataclass(frozen=True)
class Judging:
    """One live invocation that judged rows now on record (or, for the total, all of them)."""

    invocation_id: str
    states: int
    requests: int
    tokens: int
    retries: int
    throttled: int
    span_s: float
    recorded_at: str

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.tokens)


def judging_from_rows(rows) -> list[Judging]:
    out = []
    for inv, states, requests, tokens, retries, throttled, span_s, micros in rows:
        out.append(Judging(str(inv), int(states), int(requests), int(tokens), int(retries),
                           int(throttled), float(span_s),
                           utc_stamp(micros) if micros not in (None, "") else "unknown"))
    return out


def judging_total(runs: list[Judging]) -> Judging:
    return Judging("total", sum(r.states for r in runs), sum(r.requests for r in runs),
                   sum(r.tokens for r in runs), sum(r.retries for r in runs),
                   sum(r.throttled for r in runs), sum(r.span_s for r in runs), "")


def judging_caption(runs: list[Judging]) -> str:
    rows = judging_total(runs).states
    return (f"These {rows:,} rows were judged in {len(runs)} live run(s) (listed below), logged "
            "in docs/eval-results.md; no Jev calls are made now.")


def _judging_row(r: Judging, span: bool = True) -> str:
    return (f"{r.invocation_id:<36}  {r.recorded_at:<20}  {r.states:>7,}  {r.requests:>8,}  "
            f"{r.tokens:>13,}  {'$' + format(r.cost_usd, '.3f'):>9}  "
            f"{f'{r.retries:,} ({r.throttled:,}× 429)':<14}  "
            f"{(format(r.span_s, '.1f') + ' s') if span else '':>8}").rstrip()


def judging_lines(runs: list[Judging]) -> list[str]:
    """A fixed-width table, one line per judging invocation and a total (the span is not summed:
    runs happened at different times). Labelled LIVE: this mode only shows live runs."""
    head = (f"{'LIVE · invocation':<36}  {'recorded (UTC)':<20}  {'states':>7}  {'requests':>8}  "
            f"{'input tokens':>13}  {'Jev cost':>9}  {'retries':<14}  {'Jev span':>8}").rstrip()
    return [head, *(_judging_row(r) for r in runs),
            _judging_row(judging_total(runs), span=False)]


COST_NOTE = f"Jev cost = input tokens × {PRICE_PER_MTOK_USD} / 1e6 (output tokens are free)"
NOT_APPENDED = "not found in eval-results.md — this run was not appended"


def entries_for_runs(md: str, runs: list[Judging]) -> list[tuple[str, str | None]]:
    """(invocation, its logged eval-results entry or None) for each judging invocation."""
    return [(r.invocation_id, entry_for(md, r.invocation_id)) for r in runs]


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
