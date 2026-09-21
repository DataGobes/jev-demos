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
