import json

from jevdbx import demo_pack, pricing

Q = json.dumps({"instructions": "x"})
RECS = [json.dumps({"body": f"text {i}"}) for i in range(50)]


def call(records=RECS, question=Q):
    return json.loads(demo_pack.handler(records, question, "jev-1.13.0",
                                        now=lambda: 5.0, new_id=lambda: "u"))


def test_shape_matches_live_contract():
    res = call()
    assert set(res) == {"values", "input_tokens", "model", "error", "attempts", "retries",
                        "pack_uuid", "started", "finished"}
    assert res["model"] == "demo:jev-1.13.0" and res["attempts"] == 1 and res["retries"] == []
    assert res["error"] is None and len(res["values"]) == 50


def test_deterministic_and_mostly_low():
    a, b = call()["values"], call()["values"]
    assert a == b and all(0.0 <= v <= 1.0 for v in a)
    assert sum(v >= 0.5 for v in a) < 15  # hash ** 6: a few percent high


def test_values_depend_on_question():
    assert call()["values"] != call(question=json.dumps({"instructions": "y"}))["values"]


def test_tokens_estimate_like_demo04():
    assert call(records=['{"a":"12345678"}'])["input_tokens"] == len('{"a":"12345678"}') // 4 + 40


def test_price():
    assert pricing.PRICE_PER_MTOK_USD == 0.042
    assert pricing.cost_usd(1_000_000) == 0.042


def test_source_is_embeddable():
    src = open(demo_pack.__file__).read()
    assert "from __future__" not in src and "$$" not in src
