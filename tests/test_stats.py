from __future__ import annotations

import threading
import time

from semsql.stats import PRICE_PER_MTOK_USD, Stats


def test_snapshot_starts_at_zero() -> None:
    stats = Stats()
    snap = stats.snapshot()
    assert snap.rows == 0
    assert snap.cache_hits == 0
    assert snap.requests == 0
    assert snap.input_tokens == 0
    assert snap.errors == 0
    assert snap.rows_per_s == 0.0
    assert snap.cost_usd == 0.0


def test_add_accumulates() -> None:
    stats = Stats()
    stats.add(rows=10, cache_hits=3, requests=2, input_tokens=1000, errors=1)
    stats.add(rows=5, requests=1, input_tokens=500)
    snap = stats.snapshot()
    assert snap.rows == 15
    assert snap.cache_hits == 3
    assert snap.requests == 3
    assert snap.input_tokens == 1500
    assert snap.errors == 1


def test_cost_math() -> None:
    stats = Stats()
    stats.add(input_tokens=1_000_000)
    snap = stats.snapshot()
    assert snap.cost_usd == PRICE_PER_MTOK_USD

    stats2 = Stats()
    stats2.add(input_tokens=500_000)
    assert stats2.snapshot().cost_usd == PRICE_PER_MTOK_USD / 2


def test_rows_per_s() -> None:
    stats = Stats()
    stats.add(rows=100)
    time.sleep(0.05)
    snap = stats.snapshot()
    assert snap.elapsed_s > 0
    assert snap.rows_per_s == snap.rows / snap.elapsed_s


def test_reset_restarts_clock_and_zeros_counters() -> None:
    stats = Stats()
    stats.add(rows=10, requests=1)
    time.sleep(0.02)
    stats.reset()
    snap = stats.snapshot()
    assert snap.rows == 0
    assert snap.requests == 0
    assert snap.elapsed_s < 0.02


def test_thread_safety_under_concurrent_add() -> None:
    stats = Stats()
    iterations = 2000
    threads_n = 8

    def worker() -> None:
        for _ in range(iterations):
            stats.add(rows=1, requests=1, input_tokens=1)

    threads = [threading.Thread(target=worker) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = stats.snapshot()
    assert snap.rows == iterations * threads_n
    assert snap.requests == iterations * threads_n
    assert snap.input_tokens == iterations * threads_n
