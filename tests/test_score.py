import importlib.util
from pathlib import Path

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
