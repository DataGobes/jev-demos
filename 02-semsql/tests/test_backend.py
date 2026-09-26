from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from typesafe_sdk import TypeSafeError

from semsql.backend import DemoBackend, JevBackend, make_backend
from semsql.questions import Question


class FakeClient:
    """Stands in for AsyncTypeSafeClient. Records calls, returns a canned response or raises."""

    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.calls: list[tuple] = []
        self._response = response
        self._error = error
        self.closed = False

    async def system_one(self, state, questions, **kwargs):
        self.calls.append((state, questions))
        if self._error is not None:
            raise self._error
        return self._response

    async def aclose(self) -> None:
        self.closed = True


def _fake_answer(kind: str, value):
    return SimpleNamespace(**{kind: value})


def _response(answers: dict, input_tokens: int = 100):
    return SimpleNamespace(
        answers=answers, usage=SimpleNamespace(input_tokens=input_tokens)
    )


def test_single_row_request_shape() -> None:
    backend = JevBackend(model="jev-latest")
    fake = FakeClient(
        response=_response({"q": _fake_answer("noul", 0.75)}, input_tokens=42)
    )
    backend._client = fake
    question = Question(kind="noul", instructions="Is the customer angry?")

    result = asyncio.run(backend.judge(["hello there"], question))

    assert result.values == [0.75]
    assert result.input_tokens == 42
    assert len(fake.calls) == 1
    state, questions = fake.calls[0]
    assert state == "hello there"
    assert set(questions) == {"q"}
    assert questions["q"].instructions == "Is the customer angry?"


def test_packed_request_shape() -> None:
    backend = JevBackend(model="jev-latest")
    fake = FakeClient(
        response=_response(
            {"r000": _fake_answer("noul", 0.1), "r001": _fake_answer("noul", 0.9)},
            input_tokens=80,
        )
    )
    backend._client = fake
    question = Question(kind="noul", instructions="Is the customer angry?")

    result = asyncio.run(backend.judge(["first text", "second text"], question))

    assert result.values == [0.1, 0.9]
    assert result.input_tokens == 80
    state, questions = fake.calls[0]
    assert state == {"rows": {"r000": "first text", "r001": "second text"}}
    assert set(questions) == {"r000", "r001"}
    assert questions["r000"].instructions == (
        "Judge ONLY the text in `rows.r000`, ignoring all other rows. Is the customer angry?"
    )
    assert questions["r001"].instructions == (
        "Judge ONLY the text in `rows.r001`, ignoring all other rows. Is the customer angry?"
    )


def test_packed_score_request_uses_same_criteria_per_row() -> None:
    backend = JevBackend(model="jev-latest")
    fake = FakeClient(
        response=_response(
            {"r000": _fake_answer("score", 1.0), "r001": _fake_answer("score", 2.0)},
        )
    )
    backend._client = fake
    question = Question(
        kind="score", instructions="How angry?", levels=("calm", "mild", "furious")
    )

    result = asyncio.run(backend.judge(["a", "b"], question))

    assert result.values == [1.0, 2.0]
    _, questions = fake.calls[0]
    assert questions["r000"].criteria == ["calm", "mild", "furious"]
    assert questions["r001"].criteria == ["calm", "mild", "furious"]


def test_choice_question_conversion() -> None:
    backend = JevBackend(model="jev-latest")
    fake = FakeClient(response=_response({"q": _fake_answer("choice", "yes")}))
    backend._client = fake
    question = Question(kind="choice", instructions="pick", options=("yes", "no"))

    result = asyncio.run(backend.judge(["text"], question))

    assert result.values == ["yes"]
    _, questions = fake.calls[0]
    assert questions["q"].criteria == {"yes": None, "no": None}


def test_error_yields_all_none_and_records_last_error() -> None:
    backend = JevBackend(model="jev-latest")
    fake = FakeClient(error=TypeSafeError("boom"))
    backend._client = fake
    question = Question(kind="noul", instructions="q")

    result = asyncio.run(backend.judge(["a", "b", "c"], question))

    assert result.values == [None, None, None]
    assert result.input_tokens == 0
    assert backend.last_error is not None
    assert "boom" in backend.last_error


def test_aclose_closes_client_if_constructed() -> None:
    backend = JevBackend(model="jev-latest")
    fake = FakeClient(response=_response({"q": _fake_answer("noul", 0.5)}))
    backend._client = fake
    asyncio.run(backend.judge(["a"], Question(kind="noul", instructions="q")))
    asyncio.run(backend.aclose())
    assert fake.closed is True


def test_aclose_without_use_is_a_noop() -> None:
    backend = JevBackend(model="jev-latest")
    asyncio.run(backend.aclose())  # should not raise


def test_backend_metadata() -> None:
    jev = JevBackend(model="jev-latest")
    assert jev.name == "jev-latest"
    assert jev.simulated is False

    demo = DemoBackend()
    assert demo.name == "demo"
    assert demo.simulated is True


@pytest.mark.asyncio
async def test_demo_backend_deterministic_noul() -> None:
    backend = DemoBackend(latency=0.0)
    question = Question(
        kind="noul", instructions="Is the customer asking for a refund?"
    )
    r1 = await backend.judge(["I want my money back"], question)
    r2 = await backend.judge(["I want my money back"], question)
    assert r1.values == r2.values
    assert 0.0 <= r1.values[0] <= 1.0


@pytest.mark.asyncio
async def test_demo_backend_noul_rewards_overlap() -> None:
    backend = DemoBackend(latency=0.0)
    question = Question(kind="noul", instructions="refund money back")
    high = await backend.judge(["refund money back please"], question)
    low = await backend.judge(["completely unrelated sentence about weather"], question)
    assert high.values[0] > low.values[0]


@pytest.mark.asyncio
async def test_demo_backend_score_in_range() -> None:
    backend = DemoBackend(latency=0.0)
    question = Question(
        kind="score", instructions="anger", levels=("calm", "mild", "furious")
    )
    result = await backend.judge(
        ["I AM SO ANGRY!!! THIS IS UNACCEPTABLE!!!", "have a nice day"], question
    )
    for value in result.values:
        assert value in (0.0, 1.0, 2.0)
    assert result.values[0] >= result.values[1]


@pytest.mark.asyncio
async def test_demo_backend_choice_picks_overlapping_option() -> None:
    backend = DemoBackend(latency=0.0)
    question = Question(
        kind="choice", instructions="sentiment", options=("happy", "angry")
    )
    result = await backend.judge(["I am furious and angry about this"], question)
    assert result.values[0] == "angry"


@pytest.mark.asyncio
async def test_demo_backend_input_tokens_formula() -> None:
    backend = DemoBackend(latency=0.0)
    question = Question(kind="noul", instructions="q")
    texts = ["hello world", "another piece of text"]
    result = await backend.judge(texts, question)
    expected = sum(len(t) // 4 for t in texts) + 40 * len(texts)
    assert result.input_tokens == expected


@pytest.mark.asyncio
async def test_demo_backend_null_never_hits_network() -> None:
    backend = DemoBackend(latency=0.0)
    question = Question(kind="noul", instructions="q")
    result = await backend.judge([""], question)
    # DemoBackend.judge always returns a value for whatever text it's given;
    # callers (Scorer) are responsible for filtering out empty/None texts.
    assert isinstance(result.values[0], float)


def test_make_backend_auto_demo_without_key(monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    backend = make_backend()
    assert isinstance(backend, DemoBackend)


def test_make_backend_auto_live_with_key(monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    backend = make_backend(model="jev-latest")
    assert isinstance(backend, JevBackend)
    assert backend.name == "jev-latest"


def test_make_backend_explicit_demo_overrides_key(monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    backend = make_backend(demo=True)
    assert isinstance(backend, DemoBackend)


def test_make_backend_explicit_live_without_key(monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    backend = make_backend(demo=False)
    assert isinstance(backend, JevBackend)
