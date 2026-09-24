from jevdbt.stats import Stats, StatsSnapshot, format_summary


def test_add_and_snapshot():
    s = Stats()
    s.add(judgments=10, sent=4, requests=1, input_tokens=1_000_000, udf_seconds=0.5)
    s.add(judgments=2, errors=1)
    snap = s.snapshot()
    assert (snap.judgments, snap.sent, snap.requests, snap.errors) == (12, 4, 1, 1)
    assert snap.cached_fraction == 1 - 4 / 12
    assert round(snap.cost_usd, 6) == 0.042


def _snap(**kw):
    base = dict(
        judgments=1312,
        sent=813,
        requests=164,
        input_tokens=95_000,
        errors=0,
        udf_seconds=7.94,
    )
    base.update(kw)
    return StatsSnapshot(**base)


def test_format_summary_live():
    line = format_summary(_snap(), simulated=False, model="jev-latest", pack=8)
    expected = (
        "Jev · 1,312 judgments · 38% cached · 164 requests · 7.9 s · $0.004 · "
        "LIVE jev-latest pack=8"
    )
    assert line == expected


def test_format_summary_simulated_with_errors_and_tiny_cost():
    line = format_summary(_snap(input_tokens=10, errors=3), simulated=True, model="demo", pack=1)
    assert "SIMULATED demo pack=1" in line
    assert "<$0.001" in line
    assert line.endswith(" · 3 errors")


def test_cached_fraction_zero_judgments():
    assert _snap(judgments=0, sent=0).cached_fraction == 0.0
