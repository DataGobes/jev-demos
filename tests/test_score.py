import importlib.util
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("score", ROOT / "scripts" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

GOLD = {1: "defect", 2: "defect", 3: "hard_negative", 4: "defect"}


def test_metrics():
    m = score.metrics({1, 2, 3, 9}, GOLD)
    assert (m.flagged, m.tp, m.fp, m.fn, m.hard_neg_flagged) == (4, 2, 2, 1, 1)
    assert m.precision == 0.5 and round(m.recall, 3) == 0.667


def test_metrics_nothing_flagged():
    m = score.metrics(set(), GOLD)
    assert (m.precision, m.recall, m.f1) == (0.0, 0.0, 0.0)


def test_parse_summary_strips_ansi():
    out = "\x1b[0m19:26:50  Jev · 1,300 judgments · 0% cached · 1,300 requests · 64.2 s · $0.004 · LIVE jev-latest pack=1\n"  # noqa: E501
    assert score.parse_summary(out).startswith("Jev · 1,300 judgments")
    assert score.parse_summary("nothing") is None


def test_gate():
    good = score.metrics({1, 2, 4}, GOLD)
    weak = score.metrics({1}, GOLD)
    live = "Jev · 10 judgments · LIVE jev-latest pack=1"
    ok, reasons = score.gate({"t": (good, weak)}, live)
    assert ok and reasons == []
    ok, reasons = score.gate({"t": (good, weak)}, live.replace("LIVE", "SIMULATED"))
    assert not ok
    ok, reasons = score.gate({"t": (weak, good)}, live)
    assert not ok and any("recall" in r for r in reasons)
    ok, _ = score.gate({"t": (good, weak)}, live + " · 2 errors")
    assert not ok


def test_read_last_run_summary_missing_table(tmp_path):
    con = duckdb.connect(str(tmp_path / "x.duckdb"))
    try:
        assert score.read_last_run_summary(con) is None
    finally:
        con.close()


def test_read_last_run_summary_present(tmp_path):
    con = duckdb.connect(str(tmp_path / "x.duckdb"))
    try:
        con.execute("create schema main_dbt_test__audit")
        payload = json.dumps({"summary": "Jev · 1 judgments · LIVE jev-latest pack=1"})
        con.execute(
            "create table main_dbt_test__audit.jev_last_run as select ? as stats", [payload]
        )
        assert score.read_last_run_summary(con) == "Jev · 1 judgments · LIVE jev-latest pack=1"
    finally:
        con.close()


def test_scorecard_title_simulated_or_missing_vs_live():
    assert score.scorecard_title(None) == "SIMULATED backend vs regex baseline"
    assert (
        score.scorecard_title("Jev · 1 judgments · SIMULATED demo pack=1")
        == "SIMULATED backend vs regex baseline"
    )
    assert score.scorecard_title("Jev · 1 judgments · LIVE jev-latest pack=1") == (
        "Jev vs regex baseline"
    )


def test_simulated_banner_simulated_or_missing_vs_live():
    assert score.simulated_banner(None) is not None
    assert "SIMULATED" in score.simulated_banner(None)
    assert score.simulated_banner("Jev · 1 judgments · SIMULATED demo pack=1") is not None
    assert score.simulated_banner("Jev · 1 judgments · LIVE jev-latest pack=1") is None
