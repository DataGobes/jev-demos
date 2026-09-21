"""Templated titles and Vega-Lite helpers. Jev never writes text; these do."""

from __future__ import annotations

import re

_AGG = re.compile(r"^(sum|avg|mean|count|min|max|total|median)[_(\s]+", re.IGNORECASE)


def humanise(name: str) -> str:
    n = _AGG.sub("", name.strip()).strip("()\"` ")
    return re.sub(r"[_\s]+", " ", n).title() or name


def vl(mark: str | dict, encoding: dict, **extra) -> dict:
    return {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "data": {"name": "rows"},
            "mark": mark, "encoding": encoding, "width": "container", "height": 280, **extra}


def enc(field: str, type_: str, **kw) -> dict:
    return {"field": field, "type": type_, "title": humanise(field), **kw}


def time_enc(col) -> dict:
    """Encode a `kind == ("temporal",)` column for an x-axis.

    A real date/timestamp (or a date-like string) gets Vega-Lite `temporal`. A
    column of bare year integers (e.g. `signup_year`) gets `ordinal` instead:
    Vega-Lite's `temporal` type calls `toDate()` on the raw value, so an int
    like 2015 becomes 2015ms after the epoch and every year collapses onto a
    "1970" axis (F1). `col.min` is only a plain `int` (not a `date`/`datetime`,
    which profile.py always classifies temporal for real calendar columns, and
    not a `str`) when the column's values are themselves bare integers.
    """
    if isinstance(col.min, int) and not isinstance(col.min, bool):
        return {"field": col.name, "type": "ordinal", "title": humanise(col.name), "sort": "ascending"}
    return enc(col.name, "temporal")
