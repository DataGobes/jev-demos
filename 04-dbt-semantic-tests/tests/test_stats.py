import threading

from jevdbt.stats import Stats, StatsSnapshot, format_summary


def test_add_and_snapshot():
    s = Stats()
    s.add(judgments=10, unique=6, sent=4, requests=1, input_tokens=1_000_000)
    s.add(judgments=2, unique=2, errors=1)
    snap = s.snapshot()
    assert (snap.judgments, snap.unique, snap.sent, snap.requests, snap.errors) == (
        12,
        8,
        4,
        1,
        1,
    )
    assert snap.cache_hits == 4
    assert snap.cached_fraction == 4 / 8
    assert round(snap.cost_usd, 6) == 0.042


def test_wall_seconds_is_zero_with_no_calls():
    assert Stats().snapshot().wall_seconds == 0.0


def test_wall_seconds_is_span_not_sum():
    s = Stats()
    s.record_span(10.0, 11.0)  # 1.0 s
    s.record_span(10.5, 12.0)  # 1.5 s, overlapping the first
    # sum would be 2.5 s; the true wall-clock span is 10.0 -> 12.0 = 2.0 s
    assert s.snapshot().wall_seconds == 2.0


def test_wall_seconds_span_is_thread_safe():
    s = Stats()
    spans = [(0.0, 1.0), (0.5, 1.5), (0.2, 0.9), (0.8, 2.0)]

    def call(start: float, end: float) -> None:
        s.record_span(start, end)

    threads = [threading.Thread(target=call, args=span) for span in spans]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # earliest start across all threads (0.0) to latest end (2.0), not a sum of durations
    assert s.snapshot().wall_seconds == 2.0


def _snap(**kw):
    base = dict(
        judgments=1312,
        unique=1057,
        sent=813,
        requests=164,
        input_tokens=95_000,
        errors=0,
        wall_seconds=7.94,
    )
    base.update(kw)
    return StatsSnapshot(**base)


def test_format_summary_live():
    line = format_summary(
        _snap(), simulated=False, model="jev-latest", pack=8, pack_style="nested"
    )
    expected = (
        "Jev · 1,312 judgments · 1,057 unique · 23% cached · 164 requests · 7.9 s · $0.004 · "
        "LIVE jev-latest pack=8/nested"
    )
    assert line == expected


def test_format_summary_simulated_with_errors_and_tiny_cost():
    line = format_summary(_snap(input_tokens=10, errors=3), simulated=True, model="demo", pack=1)
    assert "SIMULATED demo pack=1" in line
    assert "<$0.001" in line
    assert line.endswith(" · 3 errors")


def test_cached_fraction_zero_unique():
    assert _snap(unique=0, sent=0).cached_fraction == 0.0
