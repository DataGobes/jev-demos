import pytest

from jevviz.backend import DemoBackend
from jevviz.data import generate
from jevviz.eval import load_golden, matches, run_eval


def test_matches_kind_and_required_columns():
    assert matches("multi_line", ("order_month", "region", "revenue"), ["multi_line:region+revenue"])
    assert not matches("multi_line", ("order_month", "channel", "revenue"), ["multi_line:region+revenue"])
    assert matches("bar", ("region", "revenue"), ["pie", "bar"])
    assert not matches("pie", ("region", "revenue"), ["bar"])


def test_golden_set_is_well_formed():
    cases = load_golden()
    assert len(cases) >= 10 and len({c.name for c in cases}) == len(cases)
    assert all(c.sql.strip() and c.intent.strip() and c.accept for c in cases)


@pytest.mark.asyncio
async def test_eval_runs_offline_and_reports_all_metrics(tmp_path):
    db = tmp_path / "e.duckdb"
    generate(db, n_orders=6_000)
    report = await run_eval(db, DemoBackend(), 72)
    assert 0.0 <= report.baseline_top1 <= 1.0 and 0.0 <= report.top1 <= report.top3 <= 1.0
    assert len(report.rows) == len(load_golden())
