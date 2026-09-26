import asyncio
import json
from types import SimpleNamespace

import pytest
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
    b = JevBackend(client=fake, pack_style="single")
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
    b = JevBackend(client=fake, pack_style="rows")
    res = run(b.judge(['{"a":1}', '{"a":2}', '{"a":3}'], Question("Check `a`")))
    assert res.values == [0.25, 0.26, 0.27]
    state, questions = fake.calls[0]
    assert state == {"rows": {"r000": {"a": 1}, "r001": {"a": 2}, "r002": {"a": 3}}}
    assert "`rows.r001.a`" in questions["r001"].instructions
    assert questions["r001"].criteria is None


def test_jev_nested_puts_each_record_in_its_own_question_with_empty_state():
    fake = FakeClient()
    b = JevBackend(client=fake)  # nested is the default
    q = Question("`comment` contradicts `reason_code`", "unlike `reason_code`", None)
    states = ['{"comment":"burnt","reason_code":"late"}', '{"comment":"slow","reason_code":"late"}']
    res = run(b.judge(states, q))
    assert res.values == [0.25, 0.26]
    state, questions = fake.calls[0]
    assert state == ""
    noul = questions["r001"]
    assert noul.instructions == {
        "record": {"comment": "slow", "reason_code": "late"},
        "question": "`record.comment` contradicts `record.reason_code`",
    }
    assert noul.criteria == {"true": "unlike `record.reason_code`", "false": None}


def test_jev_nested_keeps_its_layout_for_a_trailing_single_record():
    """A pack's last chunk can hold one record; it must be judged in the same layout as the
    rest, or its probability would depend on where it fell in the table."""
    fake = FakeClient()
    run(JevBackend(client=fake).judge(['{"a":1}'], Question("Check `a`")))
    state, questions = fake.calls[0]
    assert state == "" and questions["r000"].instructions["record"] == {"a": 1}


def test_jev_inline_sends_question_verbatim_beside_the_columns():
    fake = FakeClient()
    run(JevBackend(client=fake, pack_style="inline").judge(['{"a":1}'], Question("Check `a`")))
    _, questions = fake.calls[0]
    assert questions["r000"].instructions == {"a": 1, "question": "Check `a`"}


def test_jev_inline_rejects_a_question_column():
    b = JevBackend(client=FakeClient(), pack_style="inline")
    with pytest.raises(ValueError, match="nested"):
        run(b.judge(['{"question":"x"}'], Question("Check `question`")))


def test_unknown_pack_style_is_rejected():
    with pytest.raises(ValueError, match="pack_style"):
        JevBackend(client=FakeClient(), pack_style="sideways")


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
