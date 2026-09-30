import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("audit_sample", ROOT / "scripts/audit_sample.py")
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)


def test_pick_audit_excludes_planted_is_sorted_and_deterministic():
    flagged = set(range(1, 501))
    planted = set(range(1, 101))
    a = au.pick_audit(flagged, planted, 100, 42)
    assert a == au.pick_audit(flagged, planted, 100, 42)
    assert len(a) == 100 and a == sorted(a)
    assert not set(a) & planted and set(a) <= flagged


def test_pick_audit_returns_everything_when_short():
    assert au.pick_audit({5, 3, 9}, {9}, 100, 42) == [3, 5]
    assert au.pick_audit(set(), set(), 10, 42) == []


def test_pick_audit_does_not_depend_on_set_iteration_order():
    flagged = set(range(1000, 0, -1))
    assert au.pick_audit(flagged, set(), 50, 7) == au.pick_audit(set(sorted(flagged)), set(), 50, 7)


def test_flagged_query_skips_unjudged_rows_and_never_selects_the_score():
    sql = au.flagged_query("cat.sch.tbl").lower()
    select_list, _, rest = sql.partition(" from ")
    assert "jev_p" not in select_list and "jev_p is not null" in rest
    assert rest.startswith("cat.sch.tbl") and "review_id" in select_list


def test_flagged_query_reads_live_rows_only_and_never_exports_provenance():
    sql = au.flagged_query("cat.sch.tbl").lower()
    select_list, _, rest = sql.partition(" from ")
    assert "jev_mode = 'live'" in rest
    for col in ("jev_p", "jev_mode", "jev_invocation_id"):
        assert col not in select_list


def test_provenance_query_counts_rows_that_are_not_live():
    q = au.provenance_query("cat.sch.tbl").lower()
    assert "from cat.sch.tbl" in q and "jev_mode is distinct from 'live'" in q
    assert "count(distinct jev_invocation_id)" in q


def test_refuses_a_table_with_simulated_or_mixed_rows():
    assert au.provenance_problem(0, 1) is None
    assert "SIMULATED" in au.provenance_problem(3, 1)
    assert "invocations" in au.provenance_problem(0, 2)
