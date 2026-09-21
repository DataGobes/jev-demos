from jevviz.backend import DemoBackend, JevBackend, make_backend
from jevviz.types import Question

LEVELS = ("unrelated", "hidden", "partly", "directly")


async def test_demo_backend_prefers_overlapping_description():
    qs = {
        "good": Question("score", 'The analyst asked: "revenue trend over time". Proposed panel: "Line chart of revenue over month. Shows change over time."', LEVELS),
        "bad": Question("score", 'The analyst asked: "revenue trend over time". Proposed panel: "Pie chart of rating share by category."', LEVELS),
    }
    res = await DemoBackend().judge({"sql": "select 1"}, qs)
    p = lambda a: a.probabilities[2] + a.probabilities[3]
    assert p(res.answers["good"]) > p(res.answers["bad"])
    assert abs(sum(res.answers["good"].probabilities.values()) - 1.0) < 1e-9


async def test_demo_backend_flags_identifier_columns():
    qs = {
        "id.customer_id": Question("noul", "Is `customer_id` an identifier, code or label rather than a quantity that is meaningful to sum or average?"),
        "id.revenue": Question("noul", "Is `revenue` an identifier, code or label rather than a quantity that is meaningful to sum or average?"),
    }
    res = await DemoBackend().judge({}, qs)
    assert res.answers["id.customer_id"].noul > 0.5
    assert res.answers["id.revenue"].noul < 0.5


def test_make_backend_without_key_is_simulated(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert make_backend().simulated is True


async def test_jev_backend_coerces_missing_input_tokens_to_zero():
    class _Usage:
        input_tokens = None

    class _Response:
        def __init__(self) -> None:
            self.answers = {}
            self.usage = _Usage()

    class _FakeClient:
        async def system_one(self, state, questions):
            return _Response()

    backend = JevBackend()
    backend._client = _FakeClient()

    result = await backend.judge({}, {})

    assert result.input_tokens == 0
    assert result.error is None
