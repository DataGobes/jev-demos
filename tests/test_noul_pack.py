import io
import json
from pathlib import Path

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
    assert res["error"] is None
    assert [r["status"] for r in res["retries"]] == [status]
    assert res["retries"][0]["attempt"] == 1
    assert isinstance(res["retries"][0]["t"], float)
    assert len(http.calls) == 2 and len(sleeps) == 1


def test_connection_error_is_retried_with_status_none():
    res, _, _, _ = run([TimeoutError("read timed out"), ok([0.1, 0.2])])
    assert res["attempts"] == 2 and res["retries"][0]["status"] is None


def test_retry_after_header_is_honoured():
    _, _, sleeps, _ = run([(429, b"slow down", {"retry-after": "7"}), ok([0.1, 0.2])])
    assert 7 <= sleeps[0] <= 10.5  # retry_after is floor: 7 * (1.0 + 0.5*rand), rand in [0, 1)


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

    # Ruling R7: key in connection error message is redacted
    http_conn_error = FakeHttp([ConnectionError(f"reset {KEY}")] * 6)
    out = noul_pack.handler(
        RECS, Q, "jev-1.13.0",
        get_key=lambda: KEY, post=http_conn_error, sleep=lambda _: None,
        now=lambda: 1.0, new_id=lambda: "uuid-1",
    )
    assert KEY not in out

    # Ruling R7: key in server error body is redacted
    http_key_in_body = FakeHttp([(401, b"bad key " + KEY.encode(), {})])
    out = noul_pack.handler(
        RECS, Q, "jev-1.13.0",
        get_key=lambda: KEY, post=http_key_in_body, sleep=lambda _: None,
        now=lambda: 1.0, new_id=lambda: "uuid-1",
    )
    assert KEY not in out


def test_backoff_bounds():
    assert noul_pack.backoff_seconds(1, None, 0.5) == pytest.approx(1.5)
    assert noul_pack.backoff_seconds(3, None, 0.5) == pytest.approx(6.0)
    # exponential capped at 20
    assert noul_pack.backoff_seconds(10, None, 0.5) == pytest.approx(20.0)
    # retry_after floor: 4 * 1.0
    assert noul_pack.backoff_seconds(1, "4", 0.0) == pytest.approx(4.0)
    # unparsable → exponential
    assert noul_pack.backoff_seconds(1, "garbage", 0.5) == pytest.approx(1.5)
    # retry_after capped at 60
    assert noul_pack.backoff_seconds(1, "3600", 0.0) == pytest.approx(60.0)
    # negative → exponential
    assert noul_pack.backoff_seconds(1, "-5", 0.5) == pytest.approx(1.5)
    # nan → exponential
    assert noul_pack.backoff_seconds(1, "nan", 0.5) == pytest.approx(1.5)
    # inf → exponential
    assert noul_pack.backoff_seconds(1, "inf", 0.5) == pytest.approx(1.5)


def test_urllib_post(monkeypatch):
    import urllib.error
    import urllib.request

    # Success case: 200 response
    class FakeResponse:
        status = 200

        def read(self):
            return b"hello"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        @property
        def headers(self):
            return {"Content-Type": "application/json", "Retry-After": "5"}

    def fake_urlopen_200(req, timeout=None):
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen_200)
    status, body, headers = noul_pack.urllib_post(
        "https://example.com", b"body", {"Auth": "Bearer x"}, 10.0
    )
    assert status == 200 and body == b"hello"
    assert headers == {"content-type": "application/json", "retry-after": "5"}

    # Error case: 429 HTTPError
    def fake_urlopen_429(req, timeout=None):
        raise urllib.error.HTTPError(
            "https://example.com", 429, "busy",
            {"Retry-After": "3"},
            io.BytesIO(b"slow"),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen_429)
    status, body, headers = noul_pack.urllib_post(
        "https://example.com", b"body", {"Auth": "Bearer x"}, 10.0
    )
    assert status == 429 and body == b"slow"
    assert headers == {"retry-after": "3"}


def test_build_request_malformed_record_or_question():
    # Malformed record JSON
    http = FakeHttp([])
    sleeps = []
    clock = iter(range(1000, 2000))
    out = noul_pack.handler(
        ["{invalid json"], Q, "jev-1.13.0",
        get_key=lambda: KEY, post=http, sleep=sleeps.append,
        now=lambda: float(next(clock)), new_id=lambda: "uuid-1",
    )
    parsed = json.loads(out)
    assert parsed["values"] is None
    assert parsed["error"].startswith("bad input:")
    assert len(http.calls) == 0

    # Missing instructions key
    http = FakeHttp([])
    sleeps = []
    clock = iter(range(1000, 2000))
    out = noul_pack.handler(
        RECS, json.dumps({}), "jev-1.13.0",
        get_key=lambda: KEY, post=http, sleep=sleeps.append,
        now=lambda: float(next(clock)), new_id=lambda: "uuid-1",
    )
    parsed = json.loads(out)
    assert parsed["values"] is None
    assert parsed["error"].startswith("bad input:")
    assert len(http.calls) == 0


def test_source_is_embeddable():
    src = Path(noul_pack.__file__).read_text()
    assert "from __future__" not in src and "$$" not in src


# -- F8: redaction happens before truncation; an empty key is never "redacted" ------------------


def _call(script, key=KEY):
    http = FakeHttp(script)
    return json.loads(noul_pack.handler(
        RECS, Q, "jev-1.13.0", get_key=lambda: key, post=http, sleep=lambda _: None,
        now=lambda: 1.0, new_id=lambda: "uuid-1"))


def test_a_body_that_echoes_the_key_is_redacted_with_a_marker():
    res = _call([(401, b"invalid key: " + KEY.encode(), {})])
    assert "[redacted]" in res["error"] and KEY not in res["error"]


def test_a_key_straddling_the_truncation_point_leaves_no_prefix():
    body = b"x" * (noul_pack.ERROR_BODY_CHARS - 5) + KEY.encode() + b" tail"
    res = _call([(401, body, {})])
    detail = res["error"].removeprefix("HTTP 401: ")
    assert len(detail) == noul_pack.ERROR_BODY_CHARS
    # redacted first, then cut: the cut lands inside the marker, never inside the key
    assert not any(detail.endswith(KEY[:k]) for k in range(1, len(KEY) + 1))
    assert detail.endswith("[reda")


def test_an_empty_key_produces_no_redaction_markers():
    res = _call([(401, b"no key configured", {})], key="")
    assert res["error"] == "HTTP 401: no key configured"
    res = _call([ConnectionError("x")] * 6, key="")
    assert "[redacted]" not in res["error"]
