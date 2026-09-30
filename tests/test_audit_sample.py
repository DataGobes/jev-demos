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
