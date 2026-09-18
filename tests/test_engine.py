from __future__ import annotations

import asyncio
import threading
import time

import pytest

from semsql.backend import BatchResult
from semsql.cache import Cache
from semsql.engine import Scorer
from semsql.questions import Question
from semsql.stats import Stats


class RecordingBackend:
    """Fake backend: returns len(text) as a float, records every judge() call."""

    def __init__(self, latency: float = 0.0, fail_texts: set[str] | None = None) -> None:
        self.name = "fake"
        self.simulated = True
        self.calls: list[list[str]] = []
        self._latency = latency
        self._fail_texts = fail_texts or set()
        self.closed = False
        self._lock = threading.Lock()

    async def judge(self, texts: list[str], question: Question) -> BatchResult:
        with self._lock:
            self.calls.append(list(texts))
        if self._latency:
            await asyncio.sleep(self._latency)
        if any(t in self._fail_texts for t in texts):
            return BatchResult(values=[None] * len(texts), input_tokens=0)
        return BatchResult(values=[float(len(t)) for t in texts], input_tokens=len(texts) * 10)

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def question() -> Question:
    return Question(kind="noul", instructions="how long is this text?")


def _make_scorer(backend, cache=None, **kwargs) -> Scorer:
    stats = Stats()
    return Scorer(backend, stats, cache, **kwargs)


def test_order_is_preserved(question) -> None:
    backend = RecordingBackend()
    scorer = _make_scorer(backend, pack=1)
    try:
        texts = ["a", "bb", "ccc", "dddd"]
        values = scorer.score_many(texts, question)
        assert values == [1.0, 2.0, 3.0, 4.0]
    finally:
        scorer.close()


def test_dedupe_identical_texts_one_backend_call(question) -> None:
    backend = RecordingBackend()
    scorer = _make_scorer(backend, pack=8)
    try:
        texts = ["same"] * 5
        values = scorer.score_many(texts, question)
        assert values == [4.0] * 5
        assert sum(len(c) for c in backend.calls) == 1
    finally:
        scorer.close()


def test_none_and_empty_passthrough(question) -> None:
    backend = RecordingBackend()
    scorer = _make_scorer(backend)
    try:
        texts = [None, "hi", "", "bye"]
        values = scorer.score_many(texts, question)
        assert values == [None, 2.0, None, 3.0]
        assert sum(len(c) for c in backend.calls) == 2
    finally:
        scorer.close()


def test_cache_hit_on_second_call_zero_new_requests(question) -> None:
    backend = RecordingBackend()
    cache = Cache(":memory:")
    scorer = _make_scorer(backend, cache=cache)
    try:
        texts = ["alpha", "beta"]
        first = scorer.score_many(texts, question)
        assert first == [5.0, 4.0]
        assert len(backend.calls) == 2  # pack=1 default

        backend.calls.clear()
        second = scorer.score_many(texts, question)
        assert second == [5.0, 4.0]
        assert backend.calls == []
    finally:
        scorer.close()
        cache.close()


def test_pack_chunks_correctly(question) -> None:
    backend = RecordingBackend()
    scorer = _make_scorer(backend, pack=4)
    try:
        texts = [f"text{i}" for i in range(10)]
        scorer.score_many(texts, question)
        sizes = sorted(len(c) for c in backend.calls)
        assert sizes == [2, 4, 4]
    finally:
        scorer.close()


def test_failure_rows_not_cached_and_errors_incremented(question) -> None:
    backend = RecordingBackend(fail_texts={"bad"})
    cache = Cache(":memory:")
    stats = Stats()
    scorer = Scorer(backend, stats, cache, pack=1)
    try:
        values = scorer.score_many(["good", "bad"], question)
        assert values == [4.0, None]
        assert stats.snapshot().errors == 1
        assert cache.get_many(backend.name, question, ["bad"]) == {}
        assert cache.get_many(backend.name, question, ["good"]) == {"good": 4.0}

        backend.calls.clear()
        values2 = scorer.score_many(["good", "bad"], question)
        assert values2 == [4.0, None]
        # "good" served from cache, "bad" retried against the backend
        assert sum(len(c) for c in backend.calls) == 1
    finally:
        scorer.close()
        cache.close()


def test_failed_request_with_multiple_rows_marks_one_error(question) -> None:
    backend = RecordingBackend(fail_texts={"x"})
    stats = Stats()
    scorer = Scorer(backend, stats, cache=None, pack=4)
    try:
        scorer.score_many(["x", "y", "z"], question)
        assert stats.snapshot().errors == 1
        assert stats.snapshot().requests == 1
    finally:
        scorer.close()


def test_stats_progress_during_query(question) -> None:
    backend = RecordingBackend(latency=0.05)
    stats = Stats()
    scorer = Scorer(backend, stats, cache=None, pack=1, concurrency=8)
    try:
        texts = [f"t{i}" for i in range(4)]
        thread = threading.Thread(target=scorer.score_many, args=(texts, question))
        thread.start()
        time.sleep(0.08)
        mid_requests = stats.snapshot().requests
        thread.join()
        final_requests = stats.snapshot().requests
        assert 0 < mid_requests <= final_requests == 4
    finally:
        scorer.close()


def test_concurrent_score_many_from_multiple_threads(question) -> None:
    backend = RecordingBackend()
    cache = Cache(":memory:")
    stats = Stats()
    scorer = Scorer(backend, stats, cache, pack=2, concurrency=8)
    results: dict[int, list] = {}

    def worker(i: int) -> None:
        texts = [f"thread{i}-{j}" for j in range(5)]
        results[i] = scorer.score_many(texts, question)

    try:
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(4):
            expected = [float(len(f"thread{i}-{j}")) for j in range(5)]
            assert results[i] == expected
    finally:
        scorer.close()
        cache.close()


def test_close_is_idempotent_and_closes_backend(question) -> None:
    backend = RecordingBackend()
    scorer = _make_scorer(backend)
    scorer.score_many(["a"], question)
    scorer.close()
    scorer.close()
    assert backend.closed is True


def test_rpm_zero_disables_pacing(question) -> None:
    backend = RecordingBackend()
    scorer = _make_scorer(backend, rpm=0, pack=1)
    try:
        start = time.monotonic()
        scorer.score_many([f"t{i}" for i in range(20)], question)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0
    finally:
        scorer.close()
