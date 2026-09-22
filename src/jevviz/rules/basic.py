"""table, kpi, bar, pie, line, multi_line."""

from __future__ import annotations

from itertools import product

from jevviz.rules import rule
from jevviz.rules.titles import enc, humanise, time_enc, vl
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
        # Aggregated for the same reason as `pie`: unaggregated, Vega-Lite stacks the
        # value channel and emits one rect per row, so a 2000-row result renders each
        # bar as thousands of hairline segments. It also gives the `-x`/`-y` sort a
        # single value per category to order by.
        cat = enc(n.name, "nominal", sort="-x" if n.distinct > 8 else "-y")
        val = enc(q.name, "quantitative", aggregate="sum")
        encoding = {"y": cat, "x": val} if n.distinct > 8 else {"x": cat, "y": val}
        out.append(_c("bar", [n.name, q.name], [q.name], f"{humanise(q.name)} by {humanise(n.name)}",
                      # MODEL-FACING. `bar` and `pie` both used to say they "compare categories",
                      # which is why Jev rated them within 0.01 on ranking intents and often
                      # picked the pie. These two descriptions are now split along the axis that
                      # actually separates them: ranking (bar) vs share of a whole (pie).
                      f"Bar chart of `{q.name}` for each `{n.name}`, sorted from largest to smallest. "
                      f"Ranks the {humanise(n.name).lower()} values against a common axis, so which is "
                      f"highest, which is lowest, and how far apart they are can all be read off directly.",
                      vl("bar", encoding)))
    return out


@rule
def pie(p: Profile) -> list[Candidate]:
    out = []
    for n, q in product(p.by_kind("nominal"), p.by_kind("quantitative")):
        if n.name == q.name or n.distinct > 6 or q.min is None or q.min < 0:
            continue
        out.append(_c("pie", [n.name, q.name], [q.name], f"Share of {humanise(q.name)} by {humanise(n.name)}",
                      # MODEL-FACING - see the note on `bar`.
                      f"Pie chart of `{q.name}` split by `{n.name}`. "
                      f"Shows how the total divides up: what share of the whole each "
                      f"{humanise(n.name).lower()} accounts for. Slices are judged by angle, so "
                      f"values that are close together cannot be put in order by eye.",
                      vl({"type": "arc", "innerRadius": 50},
                         # Aggregated so each slice is one arc. Unaggregated, Vega-Lite
                         # stacks `theta` and emits one arc per row, which merely groups
                         # by colour - the totals look right until a stroke or a hover
                         # reveals the per-row slivers underneath.
                         {"theta": enc(q.name, "quantitative", aggregate="sum"), "color": enc(n.name, "nominal")})))
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
                         {"x": time_enc(t), "y": enc(q.name, "quantitative", aggregate="sum")})))
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
                      vl("line", {"x": time_enc(t), "y": enc(q.name, "quantitative", aggregate="sum"),
                                  "color": enc(n.name, "nominal")})))
    return out
