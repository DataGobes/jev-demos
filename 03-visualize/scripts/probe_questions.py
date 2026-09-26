"""THROWAWAY probe: how many Score questions fit in one Jev request, and how fast?"""

import asyncio
import time

from dotenv import load_dotenv

from jevviz.backend import JevBackend
from jevviz.types import Question

LEVELS = (
    "The panel shows columns that have nothing to do with what was asked.",
    "The panel uses relevant columns, but its form hides what was asked.",
    "The panel partly answers the question: right measure, missing a breakdown.",
    "The panel directly answers the question in a form that makes the pattern visible.",
)
STATE = {"sql": "SELECT region, month, sum(revenue) AS revenue FROM orders GROUP BY ALL",
         "columns": {"region": {"kind": "nominal", "distinct": 5}, "month": {"kind": "temporal", "distinct": 24},
                     "revenue": {"kind": "quantitative"}}, "row_count": 120}
FORMS = ["Line chart", "Bar chart", "Pie chart", "Heatmap", "Scatter plot", "Histogram"]


def questions(n: int) -> dict[str, Question]:
    return {f"i0.c{i:02d}": Question("score",
            f'The analyst asked: "how are regions trending". Proposed panel: "{FORMS[i % 6]} of `revenue` variant {i}." '
            "How well would this panel answer what the analyst asked?", LEVELS) for i in range(n)}


async def main() -> None:
    load_dotenv()
    backend = JevBackend()
    for n in (1, 24, 48, 72, 144):
        t0 = time.perf_counter()
        try:
            res = await backend.judge(STATE, questions(n))
            ms = (time.perf_counter() - t0) * 1000
            print(f"n={n:4d}  answered={len(res.answers):4d}  {ms:7.0f} ms  tokens={res.input_tokens}  error={res.error}")
        except Exception as exc:  # noqa: BLE001 - throwaway probe: keep going so later n rows aren't lost
            ms = (time.perf_counter() - t0) * 1000
            print(f"n={n:4d}  answered={0:4d}  {ms:7.0f} ms  tokens={0}  error={type(exc).__name__}: {exc}")
    await backend.aclose()


asyncio.run(main())
