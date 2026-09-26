import itertools
from datetime import date

from jevviz.backend import DemoBackend
from jevviz.cache import Cache
from jevviz.db import QueryResult
from jevviz.pipeline import visualize
from jevviz.types import JudgeResult

ROWS = [(date(2024, m, 1), r, float(m * (i + 1))) for m in range(1, 13) for i, r in enumerate(["EMEA", "APAC", "NA"])]
RESULT = QueryResult(["month", "region", "revenue"], ["DATE", "VARCHAR", "DOUBLE"], ROWS, len(ROWS), False)
SQL = "SELECT month, region, revenue FROM t"


async def test_demo_pipeline_picks_a_time_chart_for_a_trend_intent():
    out = await visualize(SQL, RESULT, ["how does revenue change over time per region"], DemoBackend(), None, 72)
    assert out.error is None and out.simulated is True
    assert out.panels[0]["chosen"]["kind"] in ("multi_line", "line")
    assert set(out.ms) == {"profile", "enumerate", "jev"} and out.cache == "miss"
    assert out.scored.endswith(f"of {out.scored.split(' of ')[1]}")


async def test_second_run_is_a_cache_hit_with_zero_tokens(tmp_path):
    cache = Cache(tmp_path / "c.sqlite")
    await visualize(SQL, RESULT, ["trend"], DemoBackend(), cache, 72)
    again = await visualize(SQL, RESULT, ["trend"], DemoBackend(), cache, 72)
    assert again.cache == "hit" and again.input_tokens == 0


async def test_questions_are_chunked_when_over_the_limit():
    calls = []

    class Counting(DemoBackend):
        async def judge(self, state, questions):
            calls.append(len(questions))
            return await super().judge(state, questions)

    await visualize(SQL, RESULT, ["a", "b", "c"], Counting(), None, 10)
    assert len(calls) > 1 and max(calls) <= 10


async def test_backend_failure_degrades_to_table_with_error():
    class Broken(DemoBackend):
        async def judge(self, state, questions):
            return JudgeResult(answers={}, input_tokens=0, error="RateLimitError: slow down")

    out = await visualize(SQL, RESULT, ["trend"], Broken(), None, 72)
    assert out.error == "RateLimitError: slow down"
    assert out.panels[0]["chosen"]["kind"] == "table" and out.panels[0]["match"] == "none"


def _wide_result() -> QueryResult:
    cats1, cats2, cats3, cats4 = ["a", "b", "c"], ["x", "y", "z"], ["p", "q"], ["m", "n"]
    rows = [
        (c1, c2, c3, c4, float(i), float(i * 1.5 + 1))
        for i, (c1, c2, c3, c4) in enumerate(itertools.product(cats1, cats2, cats3, cats4), start=1)
    ]
    columns = ["c1", "c2", "c3", "c4", "q1", "q2"]
    types = ["VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR", "DOUBLE", "DOUBLE"]
    return QueryResult(columns, types, rows, len(rows), False)


def _scored_pair(out) -> tuple[int, int]:
    left, right = out.scored.split(" of ")
    return int(left), int(right)


async def test_scored_reads_scored_of_non_table_total_never_off_by_one():
    # RESULT fixture: nothing is truncated by the per-rule or global cap, so every
    # non-table candidate the rules produced is the one that got scored.
    out = await visualize(SQL, RESULT, ["trend"], DemoBackend(), None, 72)
    left, right = _scored_pair(out)
    assert left == right

    # A wide result produces far more non-table candidates than the cap allows,
    # so what actually got scored is smaller than what the rules produced.
    wide = _wide_result()
    wide_out = await visualize("SELECT * FROM t", wide, ["trend"], DemoBackend(), None, 72)
    wide_left, wide_right = _scored_pair(wide_out)
    assert wide_left < wide_right
