"""DuckDB arrow UDFs: jev_noul, jev_score, jev_score_levels, jev_choice."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Any

import duckdb
import pyarrow as pa
from duckdb.func import FunctionNullHandling, PythonUDFType

from semsql.engine import Scorer
from semsql.questions import Question


def _group_and_score(
    scorer: Scorer,
    texts: list[str | None],
    keys: list[Hashable | None],
    make_question: Callable[[Any], Question],
) -> list[float | str | None]:
    """Group rows by their (constant-per-chunk) key and run one score_many per group."""
    groups: dict[Hashable, list[int]] = {}
    for i, key in enumerate(keys):
        groups.setdefault(key, []).append(i)
    out: list[float | str | None] = [None] * len(texts)
    for key, idxs in groups.items():
        if key is None:
            continue
        question = make_question(key)
        group_texts = [texts[i] for i in idxs]
        values = scorer.score_many(group_texts, question)
        for i, value in zip(idxs, values):
            out[i] = value
    return out


def register(con: duckdb.DuckDBPyConnection, scorer: Scorer, rubrics: dict[str, Question]) -> None:
    """Register jev_noul, jev_score, jev_score_levels, jev_choice on `con`."""

    def jev_noul(text_col, question_col):
        texts = text_col.to_pylist()
        questions = question_col.to_pylist()
        values = _group_and_score(
            scorer, texts, questions, lambda q: Question(kind="noul", instructions=q)
        )
        return pa.array(values, type=pa.float64())

    def jev_score(text_col, rubric_col):
        texts = text_col.to_pylist()
        names = rubric_col.to_pylist()
        unknown = sorted({n for n in names if n is not None and n not in rubrics})
        if unknown:
            available = ", ".join(sorted(rubrics)) or "(none)"
            raise duckdb.InvalidInputException(
                f"unknown rubric(s) {unknown}; available rubrics: {available}"
            )
        values = _group_and_score(scorer, texts, names, lambda n: rubrics[n])
        return pa.array(values, type=pa.float64())

    def jev_score_levels(text_col, instructions_col, levels_col):
        texts = text_col.to_pylist()
        instructions = instructions_col.to_pylist()
        levels_lists = levels_col.to_pylist()
        keys = [
            (instr, tuple(levels)) if instr is not None and levels is not None else None
            for instr, levels in zip(instructions, levels_lists)
        ]
        values = _group_and_score(
            scorer,
            texts,
            keys,
            lambda key: Question(kind="score", instructions=key[0], levels=key[1]),
        )
        return pa.array(values, type=pa.float64())

    def jev_choice(text_col, instructions_col, options_col):
        texts = text_col.to_pylist()
        instructions = instructions_col.to_pylist()
        options_lists = options_col.to_pylist()
        keys = [
            (instr, tuple(options)) if instr is not None and options is not None else None
            for instr, options in zip(instructions, options_lists)
        ]
        values = _group_and_score(
            scorer,
            texts,
            keys,
            lambda key: Question(kind="choice", instructions=key[0], options=key[1]),
        )
        return pa.array(values, type=pa.string())

    common = {
        "type": PythonUDFType.ARROW,
        "null_handling": FunctionNullHandling.SPECIAL,
        "side_effects": False,
    }
    con.create_function("jev_noul", jev_noul, ["VARCHAR", "VARCHAR"], "DOUBLE", **common)
    con.create_function("jev_score", jev_score, ["VARCHAR", "VARCHAR"], "DOUBLE", **common)
    con.create_function(
        "jev_score_levels",
        jev_score_levels,
        ["VARCHAR", "VARCHAR", "VARCHAR[]"],
        "DOUBLE",
        **common,
    )
    con.create_function(
        "jev_choice", jev_choice, ["VARCHAR", "VARCHAR", "VARCHAR[]"], "VARCHAR", **common
    )
