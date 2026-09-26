from helpers import make_profile

from jevviz.rules import enumerate_candidates
from jevviz.rules.titles import humanise


def kinds(profile):
    return [c.kind for c in enumerate_candidates(profile)[0]]


def test_humanise_strips_aggregates():
    assert humanise("sum_revenue") == "Revenue"
    assert humanise("avg(order_value)") == "Order Value"
    assert humanise("region") == "Region"


def test_time_series_with_breakdown():
    ks = kinds(make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 500.0)))
    assert "line" in ks and "multi_line" in ks and "bar" in ks and ks[-1] == "table"


def test_int_year_column_is_ordinal_x_but_date_column_is_temporal():
    # F1: an integer-year temporal column must not be encoded as Vega `temporal`
    # (which compiles to epoch-ms and smears every year onto a 1970 axis).
    year_cands, _ = enumerate_candidates(
        make_profile(signup_year=("ty", 11, 2015, 2025), customers=("q", 11, 1.0, 50.0))
    )
    year_line = next(c for c in year_cands if c.kind == "line")
    assert year_line.vega["encoding"]["x"]["field"] == "signup_year"
    assert year_line.vega["encoding"]["x"]["type"] == "ordinal"

    date_cands, _ = enumerate_candidates(make_profile(month=("t", 24), revenue=("q", 24, 0.0, 9.0)))
    date_line = next(c for c in date_cands if c.kind == "line")
    assert date_line.vega["encoding"]["x"]["type"] == "temporal"


def test_multi_line_blocked_by_high_cardinality():
    assert "multi_line" not in kinds(make_profile(month=("t", 24), sku=("n", 40), revenue=("q", 90, 0.0, 9.0)))


def test_multi_line_aggregates_like_line():
    # F6: multi_line's y encoding must aggregate (sum), matching line, so it
    # doesn't draw a zig-zag polyline through duplicate x values.
    cands, _ = enumerate_candidates(make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 500.0)))
    ml = next(c for c in cands if c.kind == "multi_line")
    assert ml.vega["encoding"]["y"]["aggregate"] == "sum"


def test_pie_needs_few_nonnegative_slices():
    assert "pie" in kinds(make_profile(row_count=4, channel=("n", 4), revenue=("q", 4, 10.0, 90.0)))
    assert "pie" not in kinds(make_profile(row_count=4, channel=("n", 4), profit=("q", 4, -5.0, 90.0)))
    assert "pie" not in kinds(make_profile(row_count=9, channel=("n", 9), revenue=("q", 9, 1.0, 9.0)))


def test_bar_blocked_above_30_and_horizontal_above_8():
    assert "bar" not in kinds(make_profile(sku=("n", 31), revenue=("q", 31, 0.0, 9.0)))
    cands, _ = enumerate_candidates(make_profile(row_count=12, country=("n", 12), revenue=("q", 12, 0.0, 9.0)))
    bar = next(c for c in cands if c.kind == "bar")
    assert bar.vega["encoding"]["y"]["field"] == "country"


def test_kpi_only_for_single_row():
    assert "kpi" in kinds(make_profile(row_count=1, total=("q", 1, 5.0, 5.0)))
    assert "kpi" not in kinds(make_profile(row_count=2, total=("q", 2, 5.0, 6.0)))


def test_ids_titles_descriptions_and_data_binding():
    cands, total = enumerate_candidates(make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 9.0)))
    assert [c.id for c in cands] == [f"c{i:02d}" for i in range(len(cands))] and total == len(cands)
    ml = next(c for c in cands if c.kind == "multi_line")
    assert ml.title == "Revenue over Month by Region"
    assert "`revenue`" in ml.description and "over time" in ml.description
    assert ml.measures == ("revenue",) and set(ml.columns) == {"month", "region", "revenue"}
    assert all(c.vega.get("data") == {"name": "rows"} for c in cands if c.kind not in ("table", "kpi"))


def test_cap_and_per_rule_limit():
    wide = make_profile(**{f"d{i}": ("n", 5) for i in range(4)}, **{f"m{i}": ("q", 50, 0.0, 9.0) for i in range(5)})
    cands, total = enumerate_candidates(wide)
    assert total > len(cands)
    assert sum(c.kind not in ("table", "kpi") for c in cands) <= 24
    assert sum(c.kind == "bar" for c in cands) <= 4
    assert next(c for c in cands if c.kind == "bar").columns == ("d0", "m0")   # SELECT order wins


def test_pie_aggregates_theta_into_one_arc_per_slice():
    """Without an aggregate, Vega-Lite stacks `theta` and draws one arc *per row*,
    which only looks like a pie because the per-row arcs sit flush against each
    other. The totals are right either way, so this is invisible until something
    strokes or hit-tests a slice - then a 3-channel pie over 72 rows turns into 72
    slivers. Aggregating makes the mark count match the slice count."""
    cands, _ = enumerate_candidates(
        make_profile(row_count=72, month=("t", 24), channel=("n", 3), revenue=("q", 70, 0.0, 9.0))
    )
    pie = next(c for c in cands if c.kind == "pie")
    assert pie.vega["encoding"]["theta"]["aggregate"] == "sum"


def test_bar_aggregates_the_measure_into_one_rect_per_category():
    """Same defect as the pie: unaggregated, Vega-Lite stacks `y` and emits one
    rect per row, so a 2000-row result draws 2000 one-pixel segments per column
    and the bar renders visibly hatched. Aggregating also makes the `-y`/`-x`
    sort meaningful, since there is now a single value per category to sort by."""
    cands, _ = enumerate_candidates(
        make_profile(row_count=2000, segment=("n", 3), revenue=("q", 1800, 0.0, 9.0))
    )
    bar = next(c for c in cands if c.kind == "bar")
    assert bar.vega["encoding"]["y"]["aggregate"] == "sum"
