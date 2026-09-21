from datetime import date

from jevviz.db import QueryResult
from jevviz.profile import profile


def result(columns, types, rows):
    return QueryResult(columns, types, rows, len(rows), False)


def test_kinds_and_stats():
    rows = [(date(2024, m, 1), "EMEA" if m % 2 else "APAC", float(m * 10) + 0.5) for m in range(1, 13)]
    p = profile(result(["month", "region", "revenue"], ["DATE", "VARCHAR", "DOUBLE"], rows))
    month, region, revenue = p.columns
    assert month.kind == ("temporal",) and month.evenly_spaced is False  # months differ in length
    assert region.kind == ("nominal",) and region.distinct == 2 and region.samples == ("APAC", "EMEA")
    assert revenue.kind == ("quantitative",) and revenue.min == 10.5 and revenue.max == 120.5
    assert p.row_count == 12 and [c.position for c in p.columns] == [0, 1, 2]


def test_integer_year_is_temporal():
    p = profile(result(["signup_year", "n"], ["INTEGER", "BIGINT"], [(y, y * 3) for y in range(2015, 2026)]))
    assert p.columns[0].kind == ("temporal",)


def test_double_year_values_are_not_temporal():
    # F1: the year heuristic must only fire for integral SQL types. A DOUBLE
    # column of whole numbers in range must not be classified temporal, since
    # the rules would then encode it as Vega `temporal` (epoch-ms) instead of
    # a plain quantitative/ordinal axis.
    p = profile(result(["yr", "n"], ["DOUBLE", "BIGINT"], [(float(y), y * 3) for y in range(2015, 2026)]))
    assert "temporal" not in p.columns[0].kind


def test_small_integer_domain_is_dual_tagged():
    p = profile(result(["rating"], ["INTEGER"], [(r,) for r in (1, 2, 3, 4, 5, 5, 4)]))
    assert p.columns[0].kind == ("nominal", "quantitative")


def test_distinct_count_boundary_at_twelve():
    twelve = profile(result(["v"], ["INTEGER"], [(n,) for n in range(10, 130, 10)]))  # 12 distinct
    thirteen = profile(result(["v"], ["INTEGER"], [(n,) for n in range(10, 140, 10)]))  # 13 distinct
    assert twelve.columns[0].kind == ("nominal", "quantitative")
    assert thirteen.columns[0].kind == ("quantitative",)


def test_date_strings_are_temporal_and_nulls_counted():
    p = profile(result(["d"], ["VARCHAR"], [("2024-01-01",), ("2024-02-01",), (None,), ("2024-03-01",)]))
    assert p.columns[0].kind == ("temporal",) and p.columns[0].null_share == 0.25


def test_profile_is_deterministic():
    rows = [("b", 2.0), ("a", 1.0), ("c", 3.0)]
    r = result(["k", "v"], ["VARCHAR", "DOUBLE"], rows)
    assert profile(r).hash() == profile(r).hash()
