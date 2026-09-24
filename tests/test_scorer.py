import asyncio
import threading

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
