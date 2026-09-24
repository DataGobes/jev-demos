import asyncio
import threading
import time

from jevdbt.backend import BatchResult
from jevdbt.cache import Cache
from jevdbt.questions import Question
from jevdbt.scorer import Scorer
from jevdbt.stats import Stats


class Recorder:
    name = "rec"
    simulated = True
    last_error = None

    def __init__(self, fail_on=None):
        self.chunks = []
        self.fail_on = fail_on
        self._lock = threading.Lock()

    async def judge(self, states, question):
        await asyncio.sleep(0)
        with self._lock:
            self.chunks.append(list(states))
        vals = [None if s == self.fail_on else len(s) / 100 for s in states]
        return BatchResult(vals, 10 * len(states))

    async def aclose(self):
        pass


Q = Question("x")


def test_dedupes_preserves_order_and_nulls():
    b, st = Recorder(), Stats()
    s = Scorer(b, st, rpm=0)
    out = s.score_many(['{"a":1}', None, '{"a":1}', '{"b":22}'], Q)
    s.close()
    assert out == [0.07, None, 0.07, 0.08]
    assert sorted(x for c in b.chunks for x in c) == ['{"a":1}', '{"b":22}']
    snap = st.snapshot()
    assert (snap.judgments, snap.sent, snap.requests, snap.input_tokens) == (3, 2, 2, 20)


def test_packs_into_chunks():
    b, st = Recorder(), Stats()
    s = Scorer(b, st, pack=3, rpm=0)
    states = [f'{{"i":{i}}}' for i in range(7)]
    out = s.score_many(states, Q)
    s.close()
    assert sorted(len(c) for c in b.chunks) == [1, 3, 3]
    assert out == [len(x) / 100 for x in states]
    assert st.snapshot().requests == 3


def test_cache_hits_skip_backend(tmp_path):
    cache = Cache(tmp_path / "c.sqlite")
    b1, st1 = Recorder(), Stats()
    s1 = Scorer(b1, st1, cache, rpm=0)
    s1.score_many(['{"a":1}', '{"a":2}'], Q)
    s1.close()
    b2, st2 = Recorder(), Stats()
    s2 = Scorer(b2, st2, cache, rpm=0)
    out = s2.score_many(['{"a":1}', '{"a":2}', '{"a":3}'], Q)
    s2.close()
    assert out == [0.07, 0.07, 0.07]
    assert b2.chunks == [['{"a":3}']]
    snap = st2.snapshot()
    assert (snap.judgments, snap.sent) == (3, 1)


def test_cache_key_is_pack_aware(tmp_path):
    """A pack=1 cache entry and a pack=3 cache entry for the same backend must not cross over:
    packed requests batch several states into one call, which can shift the judged probability,
    so serving a pack=1 answer to a pack=3 scorer (or vice versa) would be silently wrong."""
    cache = Cache(tmp_path / "c.sqlite")

    b1, st1 = Recorder(), Stats()
    s1 = Scorer(b1, st1, cache, pack=1, rpm=0)
    s1.score_many(['{"a":1}'], Q)
    s1.close()

    # pack=3 must not be served from the pack=1 entry
    b3, st3 = Recorder(), Stats()
    s3 = Scorer(b3, st3, cache, pack=3, rpm=0)
    out3 = s3.score_many(['{"a":1}'], Q)
    s3.close()
    assert out3 == [0.07]
    assert b3.chunks == [['{"a":1}']]

    # and a fresh pack=1 scorer must still be served from the original pack=1 entry, not pack=3's
    b1b, st1b = Recorder(), Stats()
    s1b = Scorer(b1b, st1b, cache, pack=1, rpm=0)
    out1b = s1b.score_many(['{"a":1}'], Q)
    s1b.close()
    assert out1b == [0.07]
    assert b1b.chunks == []


def test_failed_values_not_cached_and_counted(tmp_path):
    cache = Cache(tmp_path / "c.sqlite")
    b, st = Recorder(fail_on='{"bad":1}'), Stats()
    s = Scorer(b, st, cache, rpm=0)
    out = s.score_many(['{"bad":1}', '{"ok":1}'], Q)
    s.close()
    assert out == [None, 0.08]
    assert st.snapshot().errors == 1
    assert cache.get_many("rec", Q, ['{"bad":1}']) == {}


def test_thread_safe_concurrent_calls():
    b, st = Recorder(), Stats()
    s = Scorer(b, st, rpm=0)
    results = {}

    def work(n):
        results[n] = s.score_many([f'{{"n":{n}}}'], Q)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    s.close()
    assert len(results) == 8 and st.snapshot().judgments == 8


def test_rpm_pacing_spaces_request_starts():
    b, st = Recorder(), Stats()
    s = Scorer(b, st, pack=1, rpm=600)
    start = time.monotonic()
    out = s.score_many([f'{{"s":{i}}}' for i in range(4)], Q)
    elapsed = time.monotonic() - start
    s.close()
    assert len(out) == 4
    assert elapsed >= 0.28 and elapsed < 2.0


class SlowRecorder(Recorder):
    """Like Recorder, but each chunk takes real wall time, so a poller on another thread can
    observe `stats` mid-call -- proving judgments/sent/requests move chunk by chunk instead of
    jumping from 0 to the total only once the whole score_many() call returns."""

    async def judge(self, states, question):
        time.sleep(0.05)
        with self._lock:
            self.chunks.append(list(states))
        vals = [len(s) / 100 for s in states]
        return BatchResult(vals, 10 * len(states))


def test_stats_move_progressively_as_chunks_complete():
    b, st = SlowRecorder(), Stats()
    # concurrency=1 forces the 4 chunks to complete one at a time, ~50ms apart.
    s = Scorer(b, st, pack=1, concurrency=1, rpm=0)
    states = [f'{{"i":{i}}}' for i in range(4)]

    seen: list[int] = []

    def poll():
        for _ in range(30):
            seen.append(st.snapshot().judgments)
            time.sleep(0.01)

    poller = threading.Thread(target=poll)
    poller.start()
    s.score_many(states, Q)
    poller.join()
    s.close()

    assert seen[-1] == 4  # final total is unchanged
    # at least one poll caught a partial value -- neither the initial 0 nor the final 4 --
    # proving the count grew during the wait rather than only at the very end.
    assert any(0 < v < 4 for v in seen)
