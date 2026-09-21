"""grouped_bar, stacked_bar, scatter, histogram, heatmap."""

from __future__ import annotations

from itertools import combinations, permutations, product

from jevviz.rules import rule
from jevviz.rules.titles import enc, humanise, vl
from jevviz.types import Candidate, Profile


def _c(kind, columns, measures, title, description, vega) -> Candidate:
    return Candidate("", kind, tuple(columns), tuple(measures), title, description, vega)


def _two_dims(p: Profile):
    for (a, b), q in product(permutations(p.by_kind("nominal"), 2), p.by_kind("quantitative")):
        if len({a.name, b.name, q.name}) == 3:
            yield a, b, q


@rule
def grouped_bar(p: Profile) -> list[Candidate]:
    return [_c("grouped_bar", [a.name, b.name, q.name], [q.name],
               f"{humanise(q.name)} by {humanise(a.name)} and {humanise(b.name)}",
               f"Grouped bar chart of `{q.name}` for each `{a.name}`, with side-by-side bars per `{b.name}`. "
               f"Shows how {humanise(b.name).lower()} values compare within each {humanise(a.name).lower()}.",
               vl("bar", {"x": enc(a.name, "nominal"), "xOffset": {"field": b.name, "type": "nominal"},
                          "y": enc(q.name, "quantitative"), "color": enc(b.name, "nominal")}))
            for a, b, q in _two_dims(p) if a.distinct <= 30 and b.distinct <= 6]


@rule
def stacked_bar(p: Profile) -> list[Candidate]:
    return [_c("stacked_bar", [a.name, b.name, q.name], [q.name],
               f"{humanise(q.name)} by {humanise(a.name)}, stacked by {humanise(b.name)}",
               f"Stacked bar chart of `{q.name}` for each `{a.name}`, stacked by `{b.name}`. "
               f"Shows each {humanise(a.name).lower()}'s total and how much each {humanise(b.name).lower()} contributes to it.",
               vl("bar", {"x": enc(a.name, "nominal"), "y": enc(q.name, "quantitative", aggregate="sum"),
                          "color": enc(b.name, "nominal")}))
            for a, b, q in _two_dims(p) if a.distinct <= 30 and b.distinct <= 6 and (q.min is None or q.min >= 0)]


@rule
def heatmap(p: Profile) -> list[Candidate]:
    seen, out = set(), []
    for a, b, q in _two_dims(p):
        key = (frozenset((a.name, b.name)), q.name)
        if key in seen or a.distinct > 30 or b.distinct > 30:
            continue
        seen.add(key)
        out.append(_c("heatmap", [a.name, b.name, q.name], [q.name],
                      f"{humanise(q.name)} by {humanise(a.name)} and {humanise(b.name)}",
                      f"Heatmap of `{q.name}` with `{a.name}` across and `{b.name}` down, darker cells meaning higher values. "
                      "Shows which combinations of the two are strongest and weakest.",
                      vl("rect", {"x": enc(a.name, "nominal"), "y": enc(b.name, "nominal"),
                                  "color": enc(q.name, "quantitative", aggregate="sum")})))
    return out


@rule
def scatter(p: Profile) -> list[Candidate]:
    if p.row_count < 10:
        return []
    out = []
    for x, y in combinations(p.by_kind("quantitative"), 2):
        out.append(_c("scatter", [x.name, y.name], [x.name, y.name], f"{humanise(y.name)} against {humanise(x.name)}",
                      f"Scatter plot of `{y.name}` against `{x.name}`, one point per row. "
                      "Shows the relationship or correlation between the two quantities and any outliers.",
                      vl({"type": "point", "filled": True, "opacity": 0.6},
                         {"x": enc(x.name, "quantitative"), "y": enc(y.name, "quantitative")})))
    return out


@rule
def histogram(p: Profile) -> list[Candidate]:
    if p.row_count < 30:
        return []
    return [_c("histogram", [q.name], [q.name], f"Distribution of {humanise(q.name)}",
               f"Histogram of `{q.name}`, counting rows in each value range. "
               "Shows the distribution and spread of values: where most fall and how long the tails are.",
               vl("bar", {"x": enc(q.name, "quantitative", bin={"maxbins": 30}),
                          "y": {"aggregate": "count", "type": "quantitative", "title": "Rows"}}))
            for q in p.by_kind("quantitative") if q.distinct > 12]
