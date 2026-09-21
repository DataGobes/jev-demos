"""Deterministic column profiling. All numeric judgment lives here, never in Jev."""

from __future__ import annotations

from datetime import date, datetime

from jevviz.db import QueryResult
from jevviz.types import Column, Profile

_NUMERIC = ("INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "REAL")
_TEMPORAL = ("DATE", "TIMESTAMP")
_BOOL_STR = ("VARCHAR", "BOOLEAN")


def _parses_as_date(v: object) -> bool:
    if isinstance(v, (date, datetime)):
        return True
    if isinstance(v, int):
        return 1900 <= v <= 2100
    if isinstance(v, str):
        try:
            datetime.fromisoformat(v)
        except ValueError:
            return False
        return True
    return False


def _kind(type_name: str, values: list, distinct: int) -> tuple[str, ...]:
    t = type_name.upper()
    if any(t.startswith(x) for x in _TEMPORAL):
        return ("temporal",)
    is_numeric = any(x in t for x in _NUMERIC)
    is_int_like = is_numeric and all(isinstance(v, int) or float(v).is_integer() for v in values)
    if values and (not is_numeric or is_int_like):
        share = sum(_parses_as_date(int(v) if is_int_like else v) for v in values) / len(values)
        if share >= 0.95:
            return ("temporal",)
    if is_numeric:
        return ("nominal", "quantitative") if is_int_like and distinct <= 12 else ("quantitative",)
    return ("nominal",)


def _evenly_spaced(sorted_vals: list) -> bool:
    if len(sorted_vals) < 3:
        return False
    try:
        gaps = {sorted_vals[i + 1] - sorted_vals[i] for i in range(len(sorted_vals) - 1)}
    except TypeError:
        return False
    return len(gaps) == 1


def profile(result: QueryResult) -> Profile:
    cols = []
    n = len(result.rows)
    for pos, (name, type_name) in enumerate(zip(result.columns, result.types)):
        raw = [row[pos] for row in result.rows]
        values = [v for v in raw if v is not None]
        uniq = sorted(set(values), key=lambda v: (str(type(v)), v))
        kind = _kind(type_name, values, len(uniq))
        ordered = kind != ("nominal",) and bool(uniq)
        cols.append(Column(
            name=name, kind=kind, distinct=len(uniq),
            null_share=round((n - len(values)) / n, 4) if n else 0.0,
            min=uniq[0] if ordered else None, max=uniq[-1] if ordered else None,
            samples=tuple(uniq[:3]), evenly_spaced=_evenly_spaced(uniq) if ordered else False, position=pos,
        ))
    return Profile(columns=tuple(cols), row_count=result.row_count)
