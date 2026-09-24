"""DuckDB UDFs: jev_noul(state, question) -> probability, jev_stats() -> JSON."""

from __future__ import annotations

import time

import duckdb
import pyarrow as pa
from duckdb.func import PythonUDFType

from jevdbt.questions import Question
from jevdbt.runtime import Runtime


def register(con: duckdb.DuckDBPyConnection, runtime: Runtime) -> None:
    def jev_noul(state_col: pa.Array, question_col: pa.Array) -> pa.Array:
        started = time.perf_counter()
        states = state_col.to_pylist()
        raw_questions = question_col.to_pylist()
        out: list[float | None] = [None] * len(states)
        groups: dict[str, list[int]] = {}
        for i, (s, q) in enumerate(zip(states, raw_questions, strict=True)):
            if s is not None and q is not None:
                groups.setdefault(q, []).append(i)
        for raw, idxs in groups.items():
            try:
                question = Question.from_json(raw)
            except ValueError as exc:
                raise duckdb.InvalidInputException(f"jev_noul: bad question: {exc}") from exc
            values = runtime.scorer.score_many([states[i] for i in idxs], question)
            for i, v in zip(idxs, values, strict=True):
                out[i] = v
        runtime.stats.add(udf_seconds=time.perf_counter() - started)
        return pa.array(out, type=pa.float64())

    con.create_function(
        "jev_noul",
        jev_noul,
        ["VARCHAR", "VARCHAR"],
        "DOUBLE",
        type=PythonUDFType.ARROW,
        side_effects=True,
    )
    con.create_function("jev_stats", runtime.stats_json, [], "VARCHAR", side_effects=True)
