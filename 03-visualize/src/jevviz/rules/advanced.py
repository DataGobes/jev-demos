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
               # MODEL-FACING. `stacked_bar` and `grouped_bar` both used to say they show one
               # measure broken down by two dimensions, leaving them within 0.01 of each other
               # (and of `heatmap`) on every two-dimension intent. They are now split on what
               # the reader can actually do: compare individual values (grouped, common
               # baseline) vs read category totals (stacked, only the bottom segment is
               # baselined). Same perceptual asymmetry that separates `bar` from `pie`.
               f"Grouped bar chart of `{q.name}` for each `{a.name}`, with side-by-side bars per `{b.name}`. "
               f"Every bar starts at the same axis, so any {humanise(b.name).lower()} value can be compared "
               f"with any other, within one {humanise(a.name).lower()} or across them. Does not show "
               f"{humanise(a.name).lower()} totals.",
               # One rect per (category, group), not one per row - see `bar` and `pie`.
               # `stacked_bar` below already aggregates; this keeps the pair consistent.
               vl("bar", {"x": enc(a.name, "nominal"), "xOffset": {"field": b.name, "type": "nominal"},
                          "y": enc(q.name, "quantitative", aggregate="sum"), "color": enc(b.name, "nominal")}))
            for a, b, q in _two_dims(p) if a.distinct <= 30 and b.distinct <= 6]


@rule
def stacked_bar(p: Profile) -> list[Candidate]:
    return [_c("stacked_bar", [a.name, b.name, q.name], [q.name],
               f"{humanise(q.name)} by {humanise(a.name)}, stacked by {humanise(b.name)}",
               # MODEL-FACING - see the note on `grouped_bar`.
               # Leads with what it is FOR. Run 6 closed on the baseline caveat and Run 7 showed
               # the cost: on a pure composition intent the caveat out-worked the claim and the
               # stacked bar fell out of the top 3. The caveat is now a trailing qualifier.
               f"Stacked bar chart of `{q.name}` for each `{a.name}`, stacked by `{b.name}`. "
               f"The chart for composition: how each {humanise(a.name).lower()}'s total breaks down, what "
               f"mix of {humanise(b.name).lower()} makes it up, and how that mix and total differ from one "
               f"{humanise(a.name).lower()} to the next. Less exact for comparing a single "
               f"{humanise(b.name).lower()}'s values across {humanise(a.name).lower()}, since only the "
               f"bottom segment starts at the axis.",
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
                      # MODEL-FACING. The last of the two-dimension trio to say what it cannot do;
                      # until it did, it absorbed composition intents the other two had disclaimed.
                      f"Heatmap of `{q.name}` with `{a.name}` across and `{b.name}` down, darker cells meaning higher values. "
                      f"Shows which combinations of the two are strongest and weakest across the whole grid. "
                      f"Reads each cell's level only: no totals per {humanise(a.name).lower()} or per "
                      f"{humanise(b.name).lower()}, and nothing about how a total is made up.",
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
