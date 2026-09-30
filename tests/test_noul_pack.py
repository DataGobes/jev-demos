import json

import pytest

from jevdbx import noul_pack

KEY = "tsk-test-SECRET-value-123"
Q = json.dumps({
    "instructions": "`record.body` contradicts `record.stars`",
    "criteria": {"true": "clearly contradicts", "false": "matches"},
})
RECS = [json.dumps({"body": "Loved it", "stars": 1}), json.dumps({"body": "Meh", "stars": 3})]


class FakeHttp:
    """Scripted responses: each item is (status, body_dict_or_bytes, headers) or an Exception."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, body, headers, timeout):
        call_info = {"url": url, "body": json.loads(body), "headers": headers, "timeout": timeout}
        self.calls.append(call_info)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        status, payload, hdrs = item
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return status, raw, hdrs


def ok(values, tokens=120, model="jev-1.13.0"):
    answers = {f"r{i:03d}": {"type": "noul", "noul": v} for i, v in enumerate(values)}
    return (200, {"model": model, "answers": answers, "usage": {"input_tokens": tokens}}, {})


def run(script, records=RECS, **kw):
    http, sleeps, clock = FakeHttp(script), [], iter(range(1000, 2000))
    out = noul_pack.handler(
        records, Q, "jev-1.13.0",
        get_key=lambda: KEY, post=http, sleep=sleeps.append,
        now=lambda: float(next(clock)), new_id=lambda: "uuid-1", **kw,
    )
    return json.loads(out), http, sleeps, out


def test_build_request_nested_layout_empty_state():
    req = noul_pack.build_request(RECS, Q, "jev-1.13.0")
    assert req["model"] == "jev-1.13.0" and req["state"] == ""
    assert list(req["questions"]) == ["r000", "r001"]
    q0 = req["questions"]["r000"]
    assert q0["type"] == "noul"
    assert list(q0["instructions"]) == ["record", "question"]  # record first, question last
    assert q0["instructions"]["record"] == {"body": "Loved it", "stars": 1}
    assert q0["instructions"]["question"] == "`record.body` contradicts `record.stars`"
    assert q0["criteria"] == {"true": "clearly contradicts", "false": "matches"}


def test_build_request_without_criteria_omits_key():
    req = noul_pack.build_request(RECS[:1], json.dumps({"instructions": "x"}), "m")
    assert "criteria" not in req["questions"]["r000"]


def test_success_shape_and_request():
    res, http, sleeps, _ = run([ok([0.91, 0.12], tokens=300)])
    assert res["values"] == [0.91, 0.12]
    assert res["input_tokens"] == 300 and res["model"] == "jev-1.13.0"
    assert res["error"] is None and res["attempts"] == 1 and res["retries"] == []
    assert res["pack_uuid"] == "uuid-1" and res["finished"] >= res["started"]
    call = http.calls[0]
    assert call["url"] == "https://api.typesafe.ai/v1/systemone"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["headers"]["Content-Type"] == "application/json"
    assert sleeps == []


def test_empty_records_makes_no_call():
    res, http, _, _ = run([], records=[])
    assert res["values"] == [] and res["input_tokens"] == 0 and http.calls == []


@pytest.mark.parametrize("status", [429, 529, 500, 503])
def test_retries_then_succeeds(status):
    res, http, sleeps, _ = run([(status, b"busy", {}), ok([0.5, 0.5])])
    assert res["values"] == [0.5, 0.5] and res["attempts"] == 2
    assert [r["status"] for r in res["retries"]] == [status]
    assert len(http.calls) == 2 and len(sleeps) == 1


def test_connection_error_is_retried_with_status_none():
    res, _, _, _ = run([TimeoutError("read timed out"), ok([0.1, 0.2])])
    assert res["attempts"] == 2 and res["retries"][0]["status"] is None


def test_retry_after_header_is_honoured():
    _, _, sleeps, _ = run([(429, b"slow down", {"retry-after": "7"}), ok([0.1, 0.2])])
    assert 7 * 0.5 <= sleeps[0] <= 7 * 1.5


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_client_errors_are_not_retried(status):
    res, http, sleeps, _ = run([(status, b'{"error_type": "bad"}', {})])
    assert res["values"] is None and res["attempts"] == 1 and len(http.calls) == 1
    assert res["error"].startswith(f"HTTP {status}: ") and sleeps == []


def test_gives_up_after_six_attempts():
    res, http, sleeps, _ = run([(429, b"busy", {})] * 6)
    assert res["values"] is None and res["attempts"] == 6
    assert len(http.calls) == 6 and len(sleeps) == 5
    assert res["error"].startswith("HTTP 429: ")


def test_missing_answer_is_an_error_not_a_crash():
    res, _, _, _ = run([(200, {"model": "m", "answers": {}, "usage": {"input_tokens": 5}}, {})])
    assert res["values"] is None and "KeyError" in res["error"]


def test_error_body_is_truncated():
    res, _, _, _ = run([(400, b"x" * 5000, {})])
    assert len(res["error"]) < 400


def test_key_never_appears_in_any_output():
    scripts = [
        [ok([0.1, 0.2])],
        [(401, b"invalid key", {})],
        [(429, b"busy", {})] * 6,
        [ConnectionError("reset by peer")] * 6,
        [(200, b"not json", {})],
    ]
    for script in scripts:
        _, _, _, raw = run(script)
        assert KEY not in raw


def test_backoff_bounds():
    assert noul_pack.backoff_seconds(1, None, 0.5) == pytest.approx(1.5)
    assert noul_pack.backoff_seconds(3, None, 0.5) == pytest.approx(6.0)
    assert noul_pack.backoff_seconds(10, None, 0.5) == pytest.approx(20.0)  # capped
    assert noul_pack.backoff_seconds(1, "4", 0.0) == pytest.approx(2.0)  # 4 * 0.5
    assert noul_pack.backoff_seconds(1, "garbage", 0.5) == pytest.approx(1.5)


def test_source_is_embeddable():
    src = open(noul_pack.__file__).read()
    assert "from __future__" not in src and "$$" not in src
