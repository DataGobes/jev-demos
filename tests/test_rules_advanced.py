from helpers import make_profile

from jevviz.rules import enumerate_candidates


def kinds(profile):
    return {c.kind for c in enumerate_candidates(profile)[0]}


def test_two_dimensions_and_a_measure():
    ks = kinds(make_profile(row_count=15, region=("n", 5), channel=("n", 3), revenue=("q", 15, 0.0, 9.0)))
    assert {"grouped_bar", "stacked_bar", "heatmap"} <= ks


def test_grouping_blocked_when_inner_dimension_too_wide():
    ks = kinds(make_profile(row_count=90, region=("n", 9), country=("n", 10), revenue=("q", 90, 0.0, 9.0)))
    assert "grouped_bar" not in ks and "stacked_bar" not in ks and "heatmap" in ks


def test_scatter_needs_ten_rows_and_two_measures():
    assert "scatter" in kinds(make_profile(row_count=200, price=("q", 150, 1.0, 9.0), rating=("q", 40, 1.0, 5.0)))
    assert "scatter" not in kinds(make_profile(row_count=6, price=("q", 6, 1.0, 9.0), rating=("q", 6, 1.0, 5.0)))


def test_histogram_needs_volume_and_spread():
    assert "histogram" in kinds(make_profile(row_count=500, revenue=("q", 400, 0.0, 9.0)))
    assert "histogram" not in kinds(make_profile(row_count=500, rating=("nq", 5, 1, 5)))
    assert "histogram" not in kinds(make_profile(row_count=20, revenue=("q", 20, 0.0, 9.0)))
