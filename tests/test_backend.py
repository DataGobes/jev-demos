import asyncio
import json
from types import SimpleNamespace

from typesafe_sdk import TypeSafeError

from jevdbt.backend import DemoBackend, JevBackend, make_backend
from jevdbt.questions import Question


class FakeClient:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def system_one(self, state, questions):
        self.calls.append((state, questions))
        if self.fail:
            raise TypeSafeError("boom")
        answers = {qid: SimpleNamespace(noul=0.25 + i / 100) for i, qid in enumerate(questions)}
        return SimpleNamespace(answers=answers, usage=SimpleNamespace(input_tokens=123))

    async def aclose(self):
        pass


def run(coro):
    return asyncio.run(coro)


def test_jev_single_sends_record_as_state_with_criteria():
    fake = FakeClient()
    b = JevBackend(client=fake)
    q = Question("Contradicts `reason_code`", "t-desc", "f-desc")
    res = run(b.judge(['{"comment":"burnt","reason_code":"late"}'], q))
    assert res.values == [0.25] and res.input_tokens == 123
    state, questions = fake.calls[0]
    assert state == {"comment": "burnt", "reason_code": "late"}
    noul = questions["q"]
    assert noul.instructions == "Contradicts `reason_code`"
    assert noul.criteria == {"true": "t-desc", "false": "f-desc"}


def test_jev_packed_uses_rows_state_and_scoped_questions():
    fake = FakeClient()
    b = JevBackend(client=fake)
    res = run(b.judge(['{"a":1}', '{"a":2}', '{"a":3}'], Question("Check `a`")))
    assert res.values == [0.25, 0.26, 0.27]
    state, questions = fake.calls[0]
    assert state == {"rows": {"r000": {"a": 1}, "r001": {"a": 2}, "r002": {"a": 3}}}
    assert "`rows.r001.a`" in questions["r001"].instructions
    assert questions["r001"].criteria is None


def test_jev_error_yields_none_and_records_error():
    b = JevBackend(client=FakeClient(fail=True))
    res = run(b.judge(['{"a":1}', '{"a":2}'], Question("x")))
    assert res.values == [None, None] and res.input_tokens == 0
    assert "boom" in b.last_error


def test_demo_is_deterministic_bounded_and_simulated():
    b = DemoBackend()
    states = [json.dumps({"i": i}) for i in range(500)]
    r1 = run(b.judge(states, Question("x")))
    r2 = run(b.judge(states, Question("x")))
    assert r1.values == r2.values
    assert all(0.0 <= v <= 1.0 for v in r1.values)
    assert 0 < sum(v >= 0.8 for v in r1.values) < 50  # a few % flagged, like real data
    assert b.simulated and b.name == "demo"


def test_make_backend():
    assert isinstance(make_backend("demo", "jev-latest"), DemoBackend)
    live = make_backend("live", "jev-latest")
    assert isinstance(live, JevBackend) and not live.simulated and live.name == "jev-latest"
