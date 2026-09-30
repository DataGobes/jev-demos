"""Body of the Unity Catalog function jev_demo.jev.noul_pack(records, question, model).

One call = one Jev request in the `nested` layout: an empty shared state and one Noul question
per record, each carrying its record next to the sentence ({"record": ..., "question": ...}).
See ~/Projects/jev-demo-4/docs/pack-layouts.md for why.

This source is embedded verbatim into a Databricks SQL CREATE FUNCTION statement by jevdbx.deploy,
which appends a shim binding the injected dependencies. No future imports, no SQL delimiters, no
top-level side effects. Everything is injected so pytest can run it without a network.
"""

import json
import random
import urllib.error
import urllib.request

API_URL = "https://api.typesafe.ai/v1/systemone"
RETRYABLE_STATUSES = (429, 529)
MAX_ATTEMPTS = 6
BACKOFF_BASE_S = 1.5
BACKOFF_CAP_S = 20.0
REQUEST_TIMEOUT_S = 120.0
ERROR_BODY_CHARS = 300


def build_request(records, question, model):
    """The request body: empty state, one Noul per record, record first, question last."""
    q = json.loads(question)
    criteria = q.get("criteria")
    questions = {}
    for i, rec in enumerate(records):
        noul = {
            "type": "noul",
            "instructions": {"record": json.loads(rec), "question": q["instructions"]},
        }
        if criteria:
            noul["criteria"] = criteria
        questions[f"r{i:03d}"] = noul
    return {"model": model, "state": "", "questions": questions}


def backoff_seconds(attempt, retry_after, rand):
    """Seconds to wait after failed attempt `attempt` (1-based), jittered by rand in [0, 1)."""
    try:
        base = float(retry_after) if retry_after is not None else None
    except ValueError:
        base = None
    if base is None:
        base = min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2 ** (attempt - 1))
    return base * (0.5 + rand)


def urllib_post(url, body, headers, timeout):
    """POST with urllib; returns (status, body, headers) for HTTP errors instead of raising."""
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in (e.headers or {}).items()}


def _retryable(status):
    return status is None or status in RETRYABLE_STATUSES or status >= 500


def handler(records, question, model, *, get_key, post, sleep, now, new_id, rand=random.random):
    started = now()
    out = {"values": None, "input_tokens": 0, "model": None, "error": None, "attempts": 0,
           "retries": [], "pack_uuid": new_id(), "started": started, "finished": started}
    if not records:
        out["values"] = []
        return json.dumps(out)
    body = json.dumps(build_request(records, question, model)).encode()
    headers = {"Authorization": "Bearer " + get_key(), "Content-Type": "application/json"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        out["attempts"] = attempt
        retry_after = None
        try:
            status, raw, resp_headers = post(API_URL, body, headers, REQUEST_TIMEOUT_S)
            retry_after = resp_headers.get("retry-after")
        except Exception as exc:  # noqa: BLE001 -- connection errors and timeouts are retried
            status, raw = None, f"{type(exc).__name__}: {exc}".encode()
        if status == 200:
            parsed = _parse(raw, len(records))
            out["values"], out["input_tokens"], out["model"], out["error"] = parsed
            break
        detail = raw.decode("utf-8", "replace")[:ERROR_BODY_CHARS]
        out["error"] = f"HTTP {status}: {detail}"
        if not _retryable(status) or attempt == MAX_ATTEMPTS:
            break
        out["retries"].append({"attempt": attempt, "status": status, "t": now()})
        sleep(backoff_seconds(attempt, retry_after, rand()))
    out["finished"] = now()
    return json.dumps(out)


def _parse(raw, n):
    """(values, input_tokens, model, error) from a 200 body; a malformed body is an error."""
    try:
        resp = json.loads(raw)
        values = [resp["answers"][f"r{i:03d}"]["noul"] for i in range(n)]
        return values, int(resp["usage"]["input_tokens"]), resp["model"], None
    except (ValueError, KeyError, TypeError) as exc:
        return None, 0, None, f"bad response: {type(exc).__name__}: {str(exc)[:ERROR_BODY_CHARS]}"
