"""table, kpi, bar, pie, line, multi_line."""

from __future__ import annotations

from itertools import product

from jevviz.rules import rule
from jevviz.rules.titles import enc, humanise, vl
from jevviz.types import Candidate, Profile


def _c(kind, columns, measures, title, description, vega) -> Candidate:
    return Candidate("", kind, tuple(columns), tuple(measures), title, description, vega)


@rule
def table(p: Profile) -> list[Candidate]:
    names = [c.name for c in p.columns]
    return [_c("table", names, (), "Result table",
               "Plain table of every row and column in the result. Shows exact values without revealing any pattern.",
               {"columns": names})]


@rule
def kpi(p: Profile) -> list[Candidate]:
    qs = p.by_kind("quantitative")
    if p.row_count != 1 or not 1 <= len(qs) <= 4:
        return []
    return [_c("kpi", [q.name], [q.name], humanise(q.name),
               f"Single headline number for `{q.name}`. Shows one total value with no breakdown.",
               {"field": q.name}) for q in qs]


@rule
def bar(p: Profile) -> list[Candidate]:
    out = []
    for n, q in product(p.by_kind("nominal"), p.by_kind("quantitative")):
        if n.name == q.name or n.distinct > 30:
            continue
        cat, val = enc(n.name, "nominal", sort="-x" if n.distinct > 8 else "-y"), enc(q.name, "quantitative")
        encoding = {"y": cat, "x": val} if n.distinct > 8 else {"x": cat, "y": val}
        out.append(_c("bar", [n.name, q.name], [q.name], f"{humanise(q.name)} by {humanise(n.name)}",
                      f"Bar chart of `{q.name}` for each `{n.name}`, sorted from largest to smallest. "
                      f"Shows which {humanise(n.name).lower()} values are highest and lowest and lets them be compared.",
                      vl("bar", encoding)))
    return out


@rule
def pie(p: Profile) -> list[Candidate]:
    out = []
    for n, q in product(p.by_kind("nominal"), p.by_kind("quantitative")):
        if n.name == q.name or n.distinct > 6 or q.min is None or q.min < 0:
            continue
        out.append(_c("pie", [n.name, q.name], [q.name], f"Share of {humanise(q.name)} by {humanise(n.name)}",
                      f"Pie chart of `{q.name}` split by `{n.name}`. "
                      f"Shows each {humanise(n.name).lower()}'s share of the whole, as a proportion.",
                      vl({"type": "arc", "innerRadius": 50},
                         {"theta": enc(q.name, "quantitative"), "color": enc(n.name, "nominal")})))
    return out


@rule
def line(p: Profile) -> list[Candidate]:
    out = []
    for t, q in product(p.by_kind("temporal"), p.by_kind("quantitative")):
        if t.name == q.name or t.distinct < 3:
            continue
        out.append(_c("line", [t.name, q.name], [q.name], f"{humanise(q.name)} over {humanise(t.name)}",
                      f"Line chart of `{q.name}` over `{t.name}`. "
                      "Shows how the overall value changes over time, including trends and seasonal peaks.",
                      vl({"type": "line", "point": True},
                         {"x": enc(t.name, "temporal"), "y": enc(q.name, "quantitative", aggregate="sum")})))
    return out


@rule
def multi_line(p: Profile) -> list[Candidate]:
    out = []
    for t, q, n in product(p.by_kind("temporal"), p.by_kind("quantitative"), p.by_kind("nominal")):
        if len({t.name, q.name, n.name}) < 3 or t.distinct < 3 or n.distinct > 8:
            continue
        out.append(_c("multi_line", [t.name, n.name, q.name], [q.name],
                      f"{humanise(q.name)} over {humanise(t.name)} by {humanise(n.name)}",
                      f"Multi-series line chart of `{q.name}` over `{t.name}`, one line per `{n.name}`. "
                      f"Shows how each {humanise(n.name).lower()}'s value changes over time and lets them be compared.",
                      vl("line", {"x": enc(t.name, "temporal"), "y": enc(q.name, "quantitative"),
                                  "color": enc(n.name, "nominal")})))
    return out
