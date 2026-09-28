import importlib.util
from pathlib import Path

from rich.console import Console

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("pc", ROOT / "scripts" / "packing_compare.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

GOLD = {name: {1: "defect", 2: "defect"} for name in pc.SHORT_NAMES}


def run(pack, requests, seconds, tokens, flagged=(1, 2), **extra):
    stats = dict(pack=pack, requests=requests, wall_seconds=seconds, input_tokens=tokens,
                 errors=0, unique=10, sent=10, simulated=False)
    stats.update(extra)
    return {"stats": stats, "flagged": {name: list(flagged) for name in pc.SHORT_NAMES}}


def test_speedup_is_computed_from_the_two_runs():
    rows, speedup = pc.comparison(run(1, 1057, 54.0, 403_000), run(64, 18, 1.2, 150_000), GOLD)
    assert speedup == "45× faster · 59× fewer requests · 2.7× cheaper"
    assert ("requests", "1,057", "18") in rows
    assert ("returns  P / R", "1.00 / 1.00", "1.00 / 1.00") in rows


def test_pack_label():
    assert pc.pack_label({"pack": 1}) == "1 row / request"
    assert pc.pack_label({"pack": 64}) == "64 rows / request"


def test_warnings_flag_simulated_errors_and_cache():
    assert pc.warnings(run(1, 1, 1, 1), run(64, 1, 1, 1)) == []
    sim = pc.warnings(run(1, 1, 1, 1, simulated=True), run(64, 1, 1, 1))
    assert any("SIMULATED" in w for w in sim)
    bad = run(64, 1, 1, 1)
    bad["stats"].update(errors=2, sent=5)
    out = pc.warnings(run(1, 1, 1, 1), bad)
    assert any("2 errors" in w for w in out) and any("cache" in w for w in out)


def test_render_marks_simulated_speedup_line():
    console = Console(record=True, width=100)
    pc.render(console, run(1, 10, 2.0, 100, simulated=True), run(64, 1, 1.0, 50), GOLD)
    text = console.export_text()
    assert text.count("SIMULATED") >= 2  # banner and the speed-up line


def test_from_bench_flags_rows_at_each_tests_threshold():
    names = list(pc.SHORT_NAMES)
    bench = {"pack": 1, "requests": 3, "seconds": 5.0, "input_tokens": 900, "errors": 0,
             "tests": {n: {"1": 0.9, "2": 0.5, "3": None} for n in names}}
    thresholds = dict.fromkeys(names, 0.5)
    thresholds[names[0]] = 0.8
    run = pc.from_bench(bench, thresholds)
    assert run["flagged"][names[0]] == [1]
    assert run["flagged"][names[1]] == [1, 2]
    assert run["stats"]["logged"] and not run["stats"]["simulated"]
    assert pc.pack_label(run["stats"]) == "1 row / request (logged)"
    assert pc.recap_line(run) == "3 requests · 5.0 s · <$0.001"


def test_reference_run_is_committed_and_matches_the_logged_numbers():
    ref = pc.load_run(str(pc.REFERENCE.relative_to(pc.ROOT)))
    assert pc.recap_line(ref) == "1,057 requests · 54.9 s · $0.017"
