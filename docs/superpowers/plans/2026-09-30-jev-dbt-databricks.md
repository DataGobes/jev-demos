# Jev semantic dbt tests on Databricks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Demo 04's four English-sentence `jev_expect` dbt tests running on Databricks, with Jev
called from a Unity Catalog Python function, judgments cached in Delta, scored against demo 04's
golden key plus a ~100k-row real-review production run.

**Architecture:** A UC function `jev_demo.jev.noul_pack(records, question, model)` sends one
`nested` pack per call (key from a UC secret). A project-level dbt post-hook `jev_judge()` packs
the tested rows that have no judgment yet (token budget + row cap), calls the function once per
pack and appends to `jev_demo.jev.judgments`. `jev_expect` stays an ordinary dbt test: a SELECT
joining the model to `judgments`. The function's Python lives in `src/jevdbx/` as real modules,
rendered into `CREATE FUNCTION` by `jevdbx.deploy`.

**Tech Stack:** Python 3.13, uv, ruff, pytest, dbt-core 1.12.3 + dbt-databricks 1.12.5,
dbt-duckdb 1.11.0 (dev only: offline render target), databricks-sdk, pyarrow, rich.

**Spec:** `docs/superpowers/specs/2026-09-30-jev-dbt-databricks-design.md` (read it first).
Reference implementation: `~/Projects/jev-demo-4` (read its `CLAUDE.md`, `docs/pack-layouts.md`).

## Global Constraints

- Never read, print or log `.env`, secrets, tokens or the TypeSafe API key. The key exists only in
  the UC secret `jev_demo.jev.typesafe_api_key`, created by the user. Code refers to it by name.
- The UC function body must not contain `from __future__ import ...` or `$$` (it is embedded inside
  a function body between `$$` delimiters).
- `nested` layout, shared state `""`, record first then question: `{"record": {...}, "question": "..."}`.
- Pack cut by estimated tokens: `est = ceil((length(state) + length(question_json)) / 3.0) + 20`,
  budget `jev_pack_token_budget` = 48000, row cap `jev_pack_max_rows` = 256, row limit
  `jev_row_token_limit` = 30000, concurrency `jev_max_concurrency` = 4.
- Model pinned: `jev_model` = `jev-1.13.0`. Price: $0.042 per million input tokens.
- Cache key: `sha2(concat_ws(chr(31), requested_model, mode, 'nested', question_json, state), 256)`.
- A SIMULATED (demo mode) run always says `SIMULATED` and is never appended to
  `docs/eval-results.md` or reported as a result.
- Never edit `eval/golden_defects.csv`, `scripts/pools/*.toml` or the baseline logic to make Jev win.
- Every live Jev run needs the user's explicit OK. Queries on the 2X-Small warehouse `jev-demo-5`
  (DDL deploys, demo-mode runs) have a standing OK. Creating other warehouses, dataset downloads,
  enabling `system.billing`, dropping schemas: ask first.
- The public repo must not contain the workspace host or warehouse id: they come from env vars
  (`DATABRICKS_HOST`, `JEV_HTTP_PATH`, `JEV_WAREHOUSE`), printed by `scripts/jev_env.py`.
- Commands: `uv sync`, `uv run pytest -q`, `uv run ruff check`. Always the project's dbt:
  `uv run dbt ...` (the machine's global `dbt` is Fusion and is not used).
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File map

| File | Responsibility |
|---|---|
| `pyproject.toml` | deps, ruff, pytest (markers: `databricks`) |
| `src/jevdbx/noul_pack.py` | UC function body: request building, HTTP with retries, JSON result |
| `src/jevdbx/demo_pack.py` | UC demo function body: hash values, same result shape |
| `src/jevdbx/pricing.py` | price constant + `cost_usd` |
| `src/jevdbx/deploy.py` | renders platform DDL (schema, tables, view, both functions, production schema/volume) |
| `src/jevdbx/databricks.py` | Statement Execution client (databricks-sdk), warehouse lookup |
| `scripts/deploy.py` | CLI: print DDL, `--apply` runs it |
| `scripts/jev_env.py` | prints `export` lines for host / http path / warehouse id (no tokens) |
| `scripts/make_seeds.py`, `scripts/pools/` | copied from demo 04 |
| `jaffle_shop/…` | dbt project (macros `jev_question.sql`, `jev_expect.sql`, `jev_judge.sql`, `jev_summary.sql`, `jev_render.sql`) |
| `jaffle_shop/tests/baseline/` | demo 04 baselines ported to Spark SQL |
| `jaffle_shop/models/production/` | `stg_product_reviews` + its tests (enabled by var) |
| `scripts/fetch_reviews.py` | parse, sample, strip, plant flips, write parquet, upload |
| `scripts/audit_sample.py` | blind audit CSV |
| `scripts/score.py`, `scripts/show.py` | scorecards and recording views |
| `notebooks/jev_semantic_tests.py`, `databricks.yml` | dbt inside Databricks (serverless notebook, bundle) |
| `scripts/record.sh`, `README.md`, `CLAUDE.md`, `docs/eval-results.md` | recording, docs |

---

### Task 1: Scaffold the project and copy demo 04's yardstick assets

**Files:**
- Create: `pyproject.toml`, `src/jevdbx/__init__.py`, `tests/__init__.py` (empty), `tests/test_copied_assets.py`
- Copy from `~/Projects/jev-demo-4`: `scripts/make_seeds.py`, `scripts/pools/*.toml`,
  `jaffle_shop/seeds/*.csv`, `eval/golden_defects.csv`, `tests/test_make_seeds.py`, `tests/test_pools.py`

**Interfaces:**
- Produces: a synced uv env; `make_seeds.generate(seed) -> dict[str, list[dict]]`,
  `make_seeds.write(tables, seeds_dir, golden_path)` (unchanged from demo 04).

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "jevdbx"
version = "0.1.0"
description = "Semantic dbt tests backed by TypeSafe Jev, on Databricks + Unity Catalog (demo)"
requires-python = ">=3.13"
dependencies = [
    "dbt-databricks==1.12.5",
    "databricks-sdk",
    "pyarrow>=21",
    "rich>=14",
    "pyyaml>=6",
]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.12", "dbt-duckdb==1.11.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/jevdbx"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: runs dbt (offline render target)",
    "databricks: talks to the Databricks workspace (demo mode only); run with -m databricks",
]
addopts = "-m 'not databricks'"

[tool.ruff]
line-length = 100
src = ["src", "scripts"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

`src/jevdbx/__init__.py`: `"""Jev semantic dbt tests on Databricks (demo 05)."""`

- [ ] **Step 2: Copy the assets**

```bash
cd ~/Projects/jev-demo-5
mkdir -p scripts/pools jaffle_shop/seeds eval tests src/jevdbx
cp ~/Projects/jev-demo-4/scripts/make_seeds.py scripts/
cp ~/Projects/jev-demo-4/scripts/pools/*.toml scripts/pools/
cp ~/Projects/jev-demo-4/jaffle_shop/seeds/*.csv jaffle_shop/seeds/
cp ~/Projects/jev-demo-4/eval/golden_defects.csv eval/
cp ~/Projects/jev-demo-4/tests/test_make_seeds.py ~/Projects/jev-demo-4/tests/test_pools.py tests/
touch tests/__init__.py
uv sync
```

Check `tests/test_pools.py` and `tests/test_make_seeds.py` only reference paths that exist here
(`scripts/`, `jaffle_shop/seeds`, `eval/`); adjust nothing else.

- [ ] **Step 3: Write the identity test**

`tests/test_copied_assets.py`:

```python
"""The yardstick must be demo 04's, byte for byte: same seeds, same golden key, same pools."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DEMO4 = Path.home() / "Projects" / "jev-demo-4"

needs_demo4 = pytest.mark.skipif(not DEMO4.exists(), reason="demo 04 checkout not present")


def _make_seeds():
    spec = importlib.util.spec_from_file_location("make_seeds", ROOT / "scripts" / "make_seeds.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_regenerated_seeds_equal_committed(tmp_path):
    ms = _make_seeds()
    ms.write(ms.generate(42), tmp_path / "seeds", tmp_path / "golden.csv")
    for f in (ROOT / "jaffle_shop" / "seeds").glob("*.csv"):
        assert (tmp_path / "seeds" / f.name).read_bytes() == f.read_bytes(), f.name
    assert (tmp_path / "golden.csv").read_bytes() == (ROOT / "eval" / "golden_defects.csv").read_bytes()


@needs_demo4
@pytest.mark.parametrize(
    "rel",
    ["eval/golden_defects.csv", "scripts/make_seeds.py"]
    + [f"jaffle_shop/seeds/{p.name}" for p in (DEMO4 / "jaffle_shop/seeds").glob("*.csv")]
    + [f"scripts/pools/{p.name}" for p in (DEMO4 / "scripts/pools").glob("*.toml")],
)
def test_identical_to_demo04(rel):
    assert (ROOT / rel).read_bytes() == (DEMO4 / rel).read_bytes()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q` → Expected: all PASS. `uv run ruff check` → clean (if the copied
`make_seeds.py` trips a rule that demo 04's config also had, keep the file byte-identical and add
a per-file ignore in `pyproject.toml` instead of editing it).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "chore: scaffold jevdbx, copy demo 04 seeds, pools and golden key"
```

---

### Task 2: The UC function body (`noul_pack.py`)

**Files:**
- Create: `src/jevdbx/noul_pack.py`, `tests/test_noul_pack.py`

**Interfaces:**
- Produces:
  - `build_request(records: list[str], question: str, model: str) -> dict`
  - `backoff_seconds(attempt: int, retry_after: str | None, rand: float) -> float`
  - `urllib_post(url: str, body: bytes, headers: dict, timeout: float) -> tuple[int, bytes, dict]`
  - `handler(records, question, model, *, get_key, post, sleep, now, new_id) -> str` (JSON)
  - Result keys: `values` (list[float] | None), `input_tokens` (int), `model` (str | None),
    `error` (str | None), `attempts` (int), `retries` (list of `{"attempt", "status", "t"}`),
    `pack_uuid` (str), `started` (float epoch s), `finished` (float epoch s).

The module is embedded in `CREATE FUNCTION ... AS $$ <module source> <shim> $$` by Task 4.
No `from __future__`, no `$$`, no top-level side effects.

- [ ] **Step 1: Write the failing tests**

`tests/test_noul_pack.py`:

```python
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
        self.calls.append({"url": url, "body": json.loads(body), "headers": headers, "timeout": timeout})
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_noul_pack.py -q` → Expected: FAIL (`cannot import name 'noul_pack'`).

- [ ] **Step 3: Implement `src/jevdbx/noul_pack.py`**

```python
"""Body of the Unity Catalog function jev_demo.jev.noul_pack(records, question, model).

One call = one Jev request in the `nested` layout: an empty shared state and one Noul question
per record, each carrying its record next to the sentence ({"record": ..., "question": ...}).
See ~/Projects/jev-demo-4/docs/pack-layouts.md for why.

This source is embedded verbatim into CREATE FUNCTION ... AS $$ ... $$ by jevdbx.deploy, which
appends a shim binding the injected dependencies. So: no `from __future__` import, no `$$`, no
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
            out["values"], out["input_tokens"], out["model"], out["error"] = _parse(raw, len(records))
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
```

Note on `retries`: it holds only the attempts that were *followed by* a retry, so on give-up
after 6 attempts it has 5 entries and `attempts == 6`; `test_gives_up_after_six_attempts` asserts
5 sleeps. `test_retries_then_succeeds` asserts one retry entry. A success after a failed attempt
resets `error` to None via `_parse`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_noul_pack.py -q` → Expected: PASS. `uv run ruff check` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/jevdbx/noul_pack.py tests/test_noul_pack.py
git commit -m "feat(noul_pack): UC function body -- nested request, retries, key-safe errors"
```

---

### Task 3: SIMULATED function body and pricing

**Files:**
- Create: `src/jevdbx/demo_pack.py`, `src/jevdbx/pricing.py`, `tests/test_demo_pack.py`

**Interfaces:**
- Produces:
  - `demo_pack.hash_unit(*parts: str) -> float` in [0, 1]
  - `demo_pack.handler(records, question, model, *, now, new_id) -> str` (same keys as Task 2;
    `model` = `"demo:" + model`, `attempts` = 1, `retries` = [], `error` = None)
  - `pricing.PRICE_PER_MTOK_USD = 0.042`, `pricing.cost_usd(tokens: int) -> float`

- [ ] **Step 1: Write the failing tests**

`tests/test_demo_pack.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_demo_pack.py -q` → FAIL (import).

- [ ] **Step 3: Implement**

`src/jevdbx/demo_pack.py`:

```python
"""Body of jev_demo.jev.noul_pack_demo: SIMULATED values, no network, no secret.

Same contract as noul_pack.handler so the dbt hook cannot tell them apart; values are a hash of
(question, record), not a judgment (port of demo 04's DemoBackend). Embedded into CREATE FUNCTION
like noul_pack: no `from __future__`, no `$$`.
"""

import hashlib
import json


def hash_unit(*parts):
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def handler(records, question, model, *, now, new_id):
    started = now()
    return json.dumps({
        "values": [hash_unit(question, r) ** 6 for r in records],
        "input_tokens": sum(len(r) // 4 + 40 for r in records),
        "model": "demo:" + model,
        "error": None,
        "attempts": 1,
        "retries": [],
        "pack_uuid": new_id(),
        "started": started,
        "finished": now(),
    })
```

`src/jevdbx/pricing.py`:

```python
"""Jev pricing. https://docs.typesafe.ai/models -- charged per input token; output tokens are free."""

PRICE_PER_MTOK_USD = 0.042


def cost_usd(tokens: int) -> float:
    return tokens * PRICE_PER_MTOK_USD / 1_000_000
```

- [ ] **Step 4: Run tests** — `uv run pytest -q` → PASS; `uv run ruff check` → clean.

- [ ] **Step 5: Commit** — `git commit -m "feat(demo_pack): SIMULATED function body; pricing constant"`

---

### Task 4: Platform DDL, Databricks client, deploy CLI, env helper

**Files:**
- Create: `src/jevdbx/deploy.py`, `src/jevdbx/databricks.py`, `scripts/deploy.py`, `scripts/jev_env.py`
- Test: `tests/test_deploy.py`, `tests/test_databricks_client.py`

**Interfaces:**
- Consumes: `noul_pack.handler`, `noul_pack.urllib_post`, `demo_pack.handler` (Tasks 2–3).
- Produces:
  - `deploy.Target(catalog="jev_demo", schema="jev", secret="typesafe_api_key")` (frozen dataclass)
  - `deploy.live_function_sql(t: Target) -> str`, `deploy.demo_function_sql(t) -> str`
  - `deploy.judgments_table_sql(t)`, `deploy.hook_runs_table_sql(t)`, `deploy.requests_view_sql(t)`
  - `deploy.platform_statements(t) -> list[tuple[str, str]]` (label, sql), in dependency order
  - `deploy.production_statements(catalog="jev_demo") -> list[tuple[str, str]]`
  - `databricks.Sql(profile: str | None = None, warehouse: str | None = None)` with
    `.run(sql: str, timeout_s: float = 900) -> Result`; `Result(state, columns, rows, error,
    statement_id, wall_s)`; `databricks.resolve_warehouse_id(client, name_or_id) -> str`.
    Defaults: profile from `DATABRICKS_CONFIG_PROFILE` or `jev-demo-5`; warehouse from
    `JEV_WAREHOUSE` or `jev-demo-5` (a name; resolved to an id).

- [ ] **Step 1: Write the failing tests**

`tests/test_deploy.py`:

```python
import json
import sys
import textwrap
import types

import pytest

from jevdbx import deploy

T = deploy.Target()


def _exec_body(sql: str, fake_modules: dict):
    """Run a rendered function body the way UC does: as the body of a Python function."""
    body = sql.split("AS $$", 1)[1].rsplit("$$", 1)[0]
    src = "def __udf(records, question, model):\n" + textwrap.indent(body, "    ")
    saved = {k: sys.modules.get(k) for k in fake_modules}
    sys.modules.update(fake_modules)
    try:
        ns: dict = {}
        exec(compile(src, "<udf>", "exec"), ns)
        return ns["__udf"]
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def test_live_function_clauses():
    sql = deploy.live_function_sql(T)
    assert sql.startswith("CREATE OR REPLACE FUNCTION jev_demo.jev.noul_pack(")
    assert "records ARRAY<STRING>, question STRING, model STRING" in sql
    assert "RETURNS STRING" in sql and "LANGUAGE PYTHON" in sql and "NOT DETERMINISTIC" in sql
    assert "SECRETS (jev_demo.jev.typesafe_api_key)" in sql
    assert "ENVIRONMENT (environment_version = '6')" in sql
    assert sql.count("$$") == 2


def test_demo_function_has_no_secret_and_no_network():
    sql = deploy.demo_function_sql(T)
    assert "jev_demo.jev.noul_pack_demo(" in sql and "SECRETS" not in sql
    assert "urllib" not in sql and "typesafe.ai" not in sql


def test_live_body_runs_inside_a_function(monkeypatch):
    secrets = types.ModuleType("databricks.secrets")
    got = {}

    def fake_get(catalog, schema, key):
        got.update(catalog=catalog, schema=schema, key=key)
        return "K"

    secrets.get = fake_get
    pkg = types.ModuleType("databricks")
    pkg.secrets = secrets
    udf = _exec_body(deploy.live_function_sql(T), {"databricks": pkg, "databricks.secrets": secrets})

    import urllib.request

    class Resp:
        status = 200
        headers = {}

        def read(self):
            return json.dumps({"model": "jev-1.13.0", "answers": {"r000": {"noul": 0.8}},
                               "usage": {"input_tokens": 9}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: Resp())
    res = json.loads(udf(['{"a": 1}'], json.dumps({"instructions": "q"}), "jev-1.13.0"))
    assert res["values"] == [0.8] and res["input_tokens"] == 9
    assert got == {"catalog": "jev_demo", "schema": "jev", "key": "typesafe_api_key"}


def test_demo_body_runs_inside_a_function():
    udf = _exec_body(deploy.demo_function_sql(T), {})
    res = json.loads(udf(['{"a": 1}', '{"a": 2}'], json.dumps({"instructions": "q"}), "m"))
    assert len(res["values"]) == 2 and res["model"] == "demo:m"


def test_tables_and_view():
    j = deploy.judgments_table_sql(T)
    for col in ["key STRING", "test_name STRING", "p DOUBLE", "pack_uuid STRING",
                "pack_tokens BIGINT", "pack_est_tokens BIGINT", "retry_statuses ARRAY<INT>",
                "invocation_id STRING", "judged_at TIMESTAMP"]:
        assert col in j
    assert j.startswith("CREATE TABLE IF NOT EXISTS jev_demo.jev.judgments") and "CLUSTER BY (key)" in j
    h = deploy.hook_runs_table_sql(T)
    for col in ["invocation_id STRING", "tested BIGINT", "missing BIGINT", "oversized BIGINT", "inserted BIGINT"]:
        assert col in h
    v = deploy.requests_view_sql(T)
    assert v.startswith("CREATE OR REPLACE VIEW jev_demo.jev.requests") and "GROUP BY pack_uuid" in v


def test_platform_order():
    labels = [label for label, _ in deploy.platform_statements(T)]
    assert labels == ["schema", "judgments", "hook_runs", "requests", "noul_pack_demo", "noul_pack"]


def test_production_statements():
    labels = [label for label, _ in deploy.production_statements()]
    assert labels == ["production schema", "raw volume"]


def test_rejects_unsafe_identifiers():
    with pytest.raises(ValueError):
        deploy.Target(catalog="jev_demo; drop")
```

`tests/test_databricks_client.py`:

```python
from types import SimpleNamespace as NS

from jevdbx import databricks


class FakeStatements:
    def __init__(self, states, rows=None):
        self.states = list(states)
        self.rows = rows or [["1"]]
        self.executed = []

    def _resp(self, state):
        return NS(statement_id="s1", status=NS(state=NS(value=state), error=None),
                  manifest=NS(schema=NS(columns=[NS(name="n")]), total_chunk_count=1),
                  result=NS(data_array=self.rows, next_chunk_index=None))

    def execute_statement(self, **kw):
        self.executed.append(kw)
        return self._resp(self.states.pop(0))

    def get_statement(self, statement_id):
        return self._resp(self.states.pop(0))


def test_run_polls_until_done(monkeypatch):
    fake = FakeStatements(["RUNNING", "RUNNING", "SUCCEEDED"])
    client = NS(statement_execution=fake)
    monkeypatch.setattr(databricks.time, "sleep", lambda s: None)
    sql = databricks.Sql(client=client, warehouse_id="w1")
    res = sql.run("select 1")
    assert res.state == "SUCCEEDED" and res.columns == ["n"] and res.rows == [["1"]]
    assert fake.executed[0]["warehouse_id"] == "w1" and fake.executed[0]["statement"] == "select 1"


def test_resolve_warehouse_by_name():
    client = NS(warehouses=NS(list=lambda: [NS(id="abc", name="jev-demo-5"), NS(id="x", name="o")]))
    assert databricks.resolve_warehouse_id(client, "jev-demo-5") == "abc"
    assert databricks.resolve_warehouse_id(client, "abc") == "abc"
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_deploy.py tests/test_databricks_client.py -q` → FAIL.

- [ ] **Step 3: Implement `src/jevdbx/deploy.py`**

```python
"""Platform DDL for demo 05: schema, judgments ledger, hook_runs, requests view, both functions.

The functions' Python bodies are the real modules jevdbx.noul_pack and jevdbx.demo_pack, embedded
verbatim plus a short shim that binds their injected dependencies to the UC runtime.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from jevdbx import demo_pack, noul_pack

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Target:
    catalog: str = "jev_demo"
    schema: str = "jev"
    secret: str = "typesafe_api_key"

    def __post_init__(self):
        for value in (self.catalog, self.schema, self.secret):
            if not _IDENT.match(value):
                raise ValueError(f"not a safe identifier: {value!r}")

    def fq(self, name: str) -> str:
        return f"{self.catalog}.{self.schema}.{name}"


def _source(module) -> str:
    src = Path(module.__file__).read_text()
    if "from __future__" in src or "$$" in src:
        raise ValueError(f"{module.__name__} cannot be embedded in a UC function body")
    return src


_LIVE_SHIM = """
import time as _time
import uuid as _uuid
from databricks.secrets import get as _uc_secret_get

return handler(
    records, question, model,
    get_key=lambda: _uc_secret_get(catalog={catalog!r}, schema={schema!r}, key={secret!r}),
    post=urllib_post, sleep=_time.sleep, now=_time.time, new_id=lambda: str(_uuid.uuid4()),
)
"""

_DEMO_SHIM = """
import time as _time
import uuid as _uuid

return handler(records, question, model, now=_time.time, new_id=lambda: str(_uuid.uuid4()))
"""

_SIGNATURE = "(records ARRAY<STRING>, question STRING, model STRING)"


def live_function_sql(t: Target) -> str:
    body = _source(noul_pack) + _LIVE_SHIM.format(catalog=t.catalog, schema=t.schema, secret=t.secret)
    return (
        f"CREATE OR REPLACE FUNCTION {t.fq('noul_pack')}{_SIGNATURE}\n"
        "RETURNS STRING\nLANGUAGE PYTHON\nNOT DETERMINISTIC\n"
        "COMMENT 'Jev (TypeSafe) Noul probabilities for one nested pack of records. jev-demo-5.'\n"
        f"SECRETS ({t.fq(t.secret)})\n"
        "ENVIRONMENT (environment_version = '6')\n"
        f"AS $$\n{body}\n$$"
    )


def demo_function_sql(t: Target) -> str:
    body = _source(demo_pack) + _DEMO_SHIM
    return (
        f"CREATE OR REPLACE FUNCTION {t.fq('noul_pack_demo')}{_SIGNATURE}\n"
        "RETURNS STRING\nLANGUAGE PYTHON\nNOT DETERMINISTIC\n"
        "COMMENT 'SIMULATED stand-in for noul_pack: hash values, no network. jev-demo-5.'\n"
        f"AS $$\n{body}\n$$"
    )


def judgments_table_sql(t: Target) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {t.fq('judgments')} (
  key STRING, test_name STRING, model_name STRING, question STRING, state STRING,
  p DOUBLE, requested_model STRING, answered_model STRING, mode STRING, layout STRING,
  pack_uuid STRING, pack_rows INT, pack_tokens BIGINT, pack_est_tokens BIGINT,
  attempts INT, retry_statuses ARRAY<INT>, error STRING,
  started_at TIMESTAMP, finished_at TIMESTAMP, invocation_id STRING, judged_at TIMESTAMP
) CLUSTER BY (key)
COMMENT 'Jev judgments: cache (successful rows) and ledger. jev-demo-5.'"""


def hook_runs_table_sql(t: Target) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {t.fq('hook_runs')} (
  invocation_id STRING, test_name STRING, model_name STRING, mode STRING, requested_model STRING,
  tested BIGINT, missing BIGINT, oversized BIGINT, inserted BIGINT, recorded_at TIMESTAMP
)
COMMENT 'One row per (dbt invocation, jev_expect test) written by the jev_judge post-hook.'"""


def requests_view_sql(t: Target) -> str:
    return f"""CREATE OR REPLACE VIEW {t.fq('requests')} AS
SELECT pack_uuid,
       any_value(invocation_id) AS invocation_id, any_value(test_name) AS test_name,
       any_value(mode) AS mode, any_value(answered_model) AS answered_model,
       any_value(pack_rows) AS pack_rows, any_value(pack_tokens) AS pack_tokens,
       any_value(pack_est_tokens) AS pack_est_tokens, any_value(attempts) AS attempts,
       any_value(retry_statuses) AS retry_statuses, any_value(error) AS error,
       min(started_at) AS started_at, max(finished_at) AS finished_at, count(*) AS rows_written
FROM {t.fq('judgments')}
WHERE pack_uuid IS NOT NULL
GROUP BY pack_uuid"""


def platform_statements(t: Target = Target()) -> list[tuple[str, str]]:
    return [
        ("schema", f"CREATE SCHEMA IF NOT EXISTS {t.catalog}.{t.schema} "
                   "COMMENT 'Jev semantic tests: functions, judgments ledger. jev-demo-5.'"),
        ("judgments", judgments_table_sql(t)),
        ("hook_runs", hook_runs_table_sql(t)),
        ("requests", requests_view_sql(t)),
        ("noul_pack_demo", demo_function_sql(t)),
        ("noul_pack", live_function_sql(t)),
    ]


def production_statements(catalog: str = "jev_demo") -> list[tuple[str, str]]:
    if not _IDENT.match(catalog):
        raise ValueError(f"not a safe identifier: {catalog!r}")
    return [
        ("production schema", f"CREATE SCHEMA IF NOT EXISTS {catalog}.production "
                              "COMMENT 'Production run: real product reviews. jev-demo-5.'"),
        ("raw volume", f"CREATE VOLUME IF NOT EXISTS {catalog}.production.raw "
                       "COMMENT 'Parquet files written by scripts/fetch_reviews.py'"),
    ]
```

- [ ] **Step 4: Implement `src/jevdbx/databricks.py`**

```python
"""Minimal Statement Execution API client on databricks-sdk (auth: CLI profile, OAuth)."""

import os
import time
from dataclasses import dataclass, field

DEFAULT_PROFILE = "jev-demo-5"
DEFAULT_WAREHOUSE = "jev-demo-5"
_DONE = {"SUCCEEDED", "FAILED", "CANCELED", "CLOSED"}


@dataclass
class Result:
    state: str
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    error: str | None = None
    statement_id: str | None = None
    wall_s: float = 0.0

    def scalar(self):
        return self.rows[0][0] if self.rows else None


def _client(profile: str | None):
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(profile=profile or os.environ.get("DATABRICKS_CONFIG_PROFILE", DEFAULT_PROFILE))


def resolve_warehouse_id(client, name_or_id: str) -> str:
    for w in client.warehouses.list():
        if name_or_id in (w.name, w.id):
            return w.id
    raise LookupError(f"no SQL warehouse named or with id {name_or_id!r}")


class Sql:
    def __init__(self, profile: str | None = None, warehouse: str | None = None, *,
                 client=None, warehouse_id: str | None = None):
        self.client = client or _client(profile)
        self.warehouse_id = warehouse_id or resolve_warehouse_id(
            self.client, warehouse or os.environ.get("JEV_WAREHOUSE", DEFAULT_WAREHOUSE))

    def run(self, sql: str, timeout_s: float = 900) -> Result:
        se = self.client.statement_execution
        t0 = time.monotonic()
        resp = se.execute_statement(statement=sql, warehouse_id=self.warehouse_id,
                                    wait_timeout="50s", on_wait_timeout=_continue())
        while _state(resp) not in _DONE:
            if time.monotonic() - t0 > timeout_s:
                se.cancel_execution(resp.statement_id)
                return Result("CANCELED", error=f"timed out after {timeout_s:.0f} s",
                              statement_id=resp.statement_id, wall_s=time.monotonic() - t0)
            time.sleep(2)
            resp = se.get_statement(resp.statement_id)
        res = Result(_state(resp), statement_id=resp.statement_id, wall_s=time.monotonic() - t0)
        if res.state != "SUCCEEDED":
            err = getattr(resp.status, "error", None)
            res.error = getattr(err, "message", None) or str(err)
            return res
        manifest = resp.manifest
        res.columns = [c.name for c in manifest.schema.columns] if manifest and manifest.schema else []
        result = resp.result
        rows = list(result.data_array or []) if result else []
        nxt = getattr(result, "next_chunk_index", None) if result else None
        while nxt is not None:
            chunk = se.get_statement_result_chunk_n(resp.statement_id, nxt)
            rows.extend(chunk.data_array or [])
            nxt = chunk.next_chunk_index
        res.rows = rows
        return res


def _state(resp) -> str:
    state = resp.status.state
    return getattr(state, "value", state)


def _continue():
    try:
        from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout

        return ExecuteStatementRequestOnWaitTimeout.CONTINUE
    except ImportError:  # older/newer SDK naming
        return "CONTINUE"
```

Check the installed SDK's names once (`uv run python -c "import databricks.sdk.service.sql as s;
print([n for n in dir(s) if 'OnWaitTimeout' in n])"`) and adjust `_continue()` if needed.

- [ ] **Step 5: Implement the CLIs**

`scripts/deploy.py`:

```python
"""Print (default) or apply (--apply) the demo 05 platform DDL on the dev warehouse.

    uv run python scripts/deploy.py                 # print every statement
    uv run python scripts/deploy.py --apply         # run them (schema, tables, view, functions)
    uv run python scripts/deploy.py --apply --only noul_pack noul_pack_demo
    uv run python scripts/deploy.py --production --apply   # production schema + volume (ask first)
"""

import argparse
import sys

from jevdbx import deploy
from jevdbx.databricks import Sql


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--production", action="store_true")
    args = ap.parse_args(argv)
    stmts = deploy.production_statements() if args.production else deploy.platform_statements()
    if args.only:
        stmts = [(label, sql) for label, sql in stmts if label in args.only]
    if not args.apply:
        for label, sql in stmts:
            print(f"-- {label}\n{sql};\n")
        return 0
    sql = Sql()
    for label, stmt in stmts:
        res = sql.run(stmt)
        print(f"{label}: {res.state} ({res.wall_s:.1f} s)" + (f" -- {res.error}" if res.error else ""))
        if res.state != "SUCCEEDED":
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/jev_env.py`:

```python
"""Print shell exports for dbt: host and warehouse path from the CLI profile. Never tokens.

    eval "$(uv run python scripts/jev_env.py)"            # dev warehouse jev-demo-5
    eval "$(uv run python scripts/jev_env.py --warehouse jev-demo-5-prod)"
"""

import argparse
import os

from jevdbx.databricks import DEFAULT_PROFILE, DEFAULT_WAREHOUSE, _client, resolve_warehouse_id


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", DEFAULT_PROFILE))
    ap.add_argument("--warehouse", default=DEFAULT_WAREHOUSE)
    args = ap.parse_args(argv)
    client = _client(args.profile)
    host = client.config.host.removeprefix("https://").rstrip("/")
    wid = resolve_warehouse_id(client, args.warehouse)
    print(f"export DATABRICKS_CONFIG_PROFILE={args.profile}")
    print(f"export DATABRICKS_HOST={host}")
    print(f"export JEV_WAREHOUSE={args.warehouse}")
    print(f"export JEV_HTTP_PATH=/sql/1.0/warehouses/{wid}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests** — `uv run pytest -q` → PASS; `uv run ruff check` → clean.

- [ ] **Step 7: Commit** — `git commit -m "feat(deploy): platform DDL with embedded function bodies, SQL client, deploy + env CLIs"`

---

### Task 5: dbt project, shared macros and the `jev_expect` test

**Files:**
- Create: `jaffle_shop/dbt_project.yml`, `jaffle_shop/profiles.yml`,
  `jaffle_shop/models/staging/*.sql` (copied), `jaffle_shop/models/staging/schema.yml` (copied),
  `jaffle_shop/macros/jev_question.sql`, `jaffle_shop/macros/jev_expect.sql`,
  `jaffle_shop/macros/jev_render.sql`, `tests/dbt_helpers.py`, `tests/test_dbt_project.py`

**Interfaces:**
- Produces (Jinja macros, used by Task 6 and by the test):
  `jev_mode() -> 'live'|'demo'`, `jev_function() -> 'jev_demo.jev.noul_pack[_demo]'`,
  `jev_relation(name) -> 'jev_demo.jev.<name>'`, `jev_sql_string(s) -> SQL literal`,
  `jev_rewrite(text) -> text with `x` -> `record.x``, `jev_question(fails_if, criteria) -> JSON`,
  `jev_state_expr(column_name, context) -> SQL`, `jev_key_expr(state_expr, question_json) -> SQL`.
- `tests/dbt_helpers.py`: `dbt(*args, env=None) -> subprocess.CompletedProcess` (runs
  `uv run dbt ... --profiles-dir . --target render` in `jaffle_shop/`, `JEV_MODE` from env),
  `render(macro, args: dict) -> str` (runs `dbt run-operation jev_render_<...>` and returns the
  printed SQL between `-- BEGIN` / `-- END` markers).

- [ ] **Step 1: Copy the dbt sources from demo 04**

```bash
mkdir -p jaffle_shop/models/staging jaffle_shop/macros jaffle_shop/tests/baseline
cp ~/Projects/jev-demo-4/jaffle_shop/models/staging/*.sql jaffle_shop/models/staging/
cp ~/Projects/jev-demo-4/jaffle_shop/models/staging/schema.yml jaffle_shop/models/staging/
```

The staging SQL (`select id as ..., concat_ws(' ', ...), trim(...)`) is valid Spark SQL as is.

- [ ] **Step 2: Write `dbt_project.yml` and `profiles.yml`**

`jaffle_shop/dbt_project.yml`:

```yaml
name: jaffle_shop
version: "1.0.0"
profile: jaffle_shop
model-paths: ["models"]
seed-paths: ["seeds"]
macro-paths: ["macros"]
test-paths: ["tests"]

on-run-end:
  - "{{ jev_summary() }}"

vars:
  jev_catalog: jev_demo
  jev_schema: jev
  jev_mode: live            # override with env JEV_MODE=demo (SIMULATED)
  jev_model: jev-1.13.0     # pinned; part of the cache key
  jev_pack_token_budget: 48000
  jev_pack_max_rows: 256
  jev_row_token_limit: 30000
  jev_max_concurrency: 4
  jev_price_per_mtok_usd: 0.042   # https://docs.typesafe.ai/models
  production: false         # --vars '{production: true}' enables models/production

models:
  jaffle_shop:
    +materialized: table
    +post-hook: "{{ jev_judge() }}"
    production:
      +enabled: "{{ var('production', false) }}"
```

`jaffle_shop/profiles.yml`:

```yaml
# Host and warehouse come from the environment: eval "$(uv run python scripts/jev_env.py)".
# The `render` target is offline (DuckDB, in memory) and only used by pytest to render macros.
jaffle_shop:
  target: dev
  outputs:
    dev:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST') }}"
      http_path: "{{ env_var('JEV_HTTP_PATH') }}"
      catalog: jev_demo
      schema: jaffle_shop
      auth_type: oauth
      threads: 4
    notebook:
      type: databricks
      host: "{{ env_var('DATABRICKS_HOST', 'unset') }}"
      http_path: "{{ env_var('JEV_HTTP_PATH', 'unset') }}"
      token: "{{ env_var('DBT_DATABRICKS_TOKEN', 'unset') }}"
      catalog: jev_demo
      schema: jaffle_shop
      threads: 4
    render:
      type: duckdb
      path: ":memory:"
      threads: 1
```

- [ ] **Step 3: Write the shared macros**

`jaffle_shop/macros/jev_question.sql`:

```sql
{#-
  Building blocks shared by the jev_expect test and the jev_judge post-hook. The test finds the
  hook's judgments by key, so both MUST build the question, state and key through these macros.
-#}

{% macro jev_mode() %}
  {%- set mode = (env_var('JEV_MODE', var('jev_mode', 'live')) | string | lower) -%}
  {%- if mode not in ['live', 'demo'] -%}
    {{ exceptions.raise_compiler_error("jev: JEV_MODE must be 'live' or 'demo', got '" ~ mode ~ "'") }}
  {%- endif -%}
  {{ return(mode) }}
{% endmacro %}

{% macro jev_relation(name) %}
  {{ return(var('jev_catalog') ~ '.' ~ var('jev_schema') ~ '.' ~ name) }}
{% endmacro %}

{% macro jev_function() %}
  {{ return(jev_relation('noul_pack' if jev_mode() == 'live' else 'noul_pack_demo')) }}
{% endmacro %}

{% macro jev_sql_string(s) %}
  {{ return("'" ~ (s | string | replace("\\", "\\\\") | replace("'", "\\'")) ~ "'") }}
{% endmacro %}

{% macro jev_rewrite(text) %}
  {%- if text is none -%}{{ return(none) }}{%- endif -%}
  {{ return(modules.re.sub('`([A-Za-z_][A-Za-z0-9_]*)`', '`record.\\1`', text | string)) }}
{% endmacro %}

{% macro jev_question(fails_if, criteria=none) %}
  {%- if fails_if is not string or not (fails_if | trim) -%}
    {{ exceptions.raise_compiler_error("jev_expect: `fails_if` must be a non-empty sentence") }}
  {%- endif -%}
  {%- set question = {"instructions": jev_rewrite(fails_if)} -%}
  {%- if criteria is not none -%}
    {%- set normalized = {} -%}
    {%- for key, value in criteria.items() -%}
      {%- set k = (key | string | lower) -%}
      {%- if k not in ["true", "false"] -%}
        {{ exceptions.raise_compiler_error("jev_expect: `criteria` keys must be true/false, got " ~ key) }}
      {%- endif -%}
      {%- do normalized.update({k: jev_rewrite(value)}) -%}
    {%- endfor -%}
    {%- do question.update({"criteria": normalized}) -%}
  {%- endif -%}
  {{ return(tojson(question)) }}
{% endmacro %}

{% macro jev_state_expr(column_name, context=[]) %}
  {%- set parts = [] -%}
  {%- for f in [column_name] + (context or []) -%}
    {%- do parts.append("'" ~ f ~ "', " ~ adapter.quote(f)) -%}
  {%- endfor -%}
  {{ return("to_json(named_struct(" ~ (parts | join(", ")) ~ "))") }}
{% endmacro %}

{% macro jev_key_expr(state_expr, question_json) %}
  {{ return("sha2(concat_ws(chr(31), " ~ jev_sql_string(var('jev_model')) ~ ", "
            ~ jev_sql_string(jev_mode()) ~ ", 'nested', " ~ jev_sql_string(question_json)
            ~ ", " ~ state_expr ~ "), 256)") }}
{% endmacro %}
```

`jaffle_shop/macros/jev_expect.sql`:

```sql
{#-
  Semantic test: returns the rows whose judgment p >= threshold, plus rows that have no judgment
  yet (jev_p is NULL: run `dbt build` so the jev_judge post-hook can judge them). Judgments are
  made by the post-hook on the tested model and stored in jev_demo.jev.judgments; this test only
  reads them, so it stays an ordinary dbt test.
-#}
{% test jev_expect(model, column_name, fails_if, context=[], threshold=0.5, criteria=none) %}
  {%- if threshold is not number or threshold <= 0 or threshold > 1 -%}
    {{ exceptions.raise_compiler_error("jev_expect: `threshold` must be in (0, 1], got " ~ threshold) }}
  {%- endif -%}
  {%- set question = jev_question(fails_if, criteria) -%}
  {%- set key = jev_key_expr(jev_state_expr(column_name, context), question) -%}

with tested as (
  select *, {{ key }} as __jev_key
  from {{ model }}
  where {{ adapter.quote(column_name) }} is not null
),
judged as (
  select key, p from {{ jev_relation('judgments') }} where p is not null
)
select tested.* except (__jev_key), judged.p as jev_p
from tested
left join judged on judged.key = tested.__jev_key
where judged.p is null or judged.p >= {{ threshold }}
{% endtest %}
```

`jaffle_shop/macros/jev_render.sql` (test support; renders only, runs nothing):

```sql
{#- pytest helpers: print macro output between markers. Offline `render` target only. -#}
{% macro jev_render_question(fails_if, criteria=none) %}
  {{ print('-- BEGIN\n' ~ jev_question(fails_if, criteria) ~ '\n-- END') }}
{% endmacro %}

{% macro jev_render_key(column_name, context, fails_if, criteria=none) %}
  {%- set q = jev_question(fails_if, criteria) -%}
  {{ print('-- BEGIN\n' ~ jev_key_expr(jev_state_expr(column_name, context), q) ~ '\n-- END') }}
{% endmacro %}
```

- [ ] **Step 4: Write test helpers and tests**

`tests/dbt_helpers.py`:

```python
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
JAFFLE = ROOT / "jaffle_shop"


def dbt(*args, env=None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false", **(env or {})}
    if env is None or "JEV_MODE" not in env:
        full_env.pop("JEV_MODE", None)
    return subprocess.run(
        ["uv", "run", "dbt", *args, "--profiles-dir", ".", "--target", "render"],
        cwd=JAFFLE, capture_output=True, text=True, env=full_env, timeout=300,
    )


def render(macro: str, args: dict, env=None) -> str:
    out = dbt("run-operation", macro, "--args", json.dumps(args), env=env)
    m = re.search(r"-- BEGIN\n(.*?)\n-- END", out.stdout, re.S)
    assert m, f"no output from {macro}:\n{out.stdout}\n{out.stderr}"
    return m.group(1)
```

`tests/test_dbt_project.py`:

```python
import json
from pathlib import Path

import pytest
import yaml

from tests.dbt_helpers import JAFFLE, dbt, render

DEMO4_SCHEMA = Path.home() / "Projects/jev-demo-4/jaffle_shop/models/staging/schema.yml"
SENTENCE = "The customer's `comment` describes a different main reason"


def _jev_blocks(schema_path):
    out = {}
    for model in yaml.safe_load(Path(schema_path).read_text())["models"]:
        for col in model.get("columns", []):
            for t in col.get("data_tests", []):
                if isinstance(t, dict) and "jev_expect" in t:
                    out[t["jev_expect"]["name"]] = (model["name"], col["name"], t["jev_expect"])
    return out


@pytest.mark.skipif(not DEMO4_SCHEMA.exists(), reason="demo 04 checkout not present")
def test_jev_expect_blocks_identical_to_demo04():
    ours = _jev_blocks(JAFFLE / "models/staging/schema.yml")
    assert ours == _jev_blocks(DEMO4_SCHEMA) and len(ours) == 4


@pytest.mark.slow
def test_parse_succeeds():
    res = dbt("parse")
    assert res.returncode == 0, res.stdout + res.stderr


@pytest.mark.slow
def test_post_hook_and_vars_configured():
    dbt("parse")
    manifest = json.loads((JAFFLE / "target/manifest.json").read_text())
    node = manifest["nodes"]["model.jaffle_shop.stg_reviews"]
    assert any("jev_judge()" in h["sql"] for h in node["config"]["post-hook"])


@pytest.mark.slow
def test_question_rewrites_columns_and_normalizes_criteria():
    q = json.loads(render("jev_render_question", {
        "fails_if": "The `body` contradicts `stars`",
        "criteria": {True: "yes `body`", "false": "no"},
    }))
    assert q == {"instructions": "The `record.body` contradicts `record.stars`",
                 "criteria": {"true": "yes `record.body`", "false": "no"}}


@pytest.mark.slow
def test_key_escapes_quotes_and_includes_mode_and_model():
    key = render("jev_render_key", {"column_name": "comment", "context": ["reason_code"],
                                    "fails_if": SENTENCE + " than `reason_code`."})
    assert key.startswith("sha2(concat_ws(chr(31), 'jev-1.13.0', 'live', 'nested', ")
    assert "customer\\'s" in key  # single quote escaped for Spark SQL
    assert "to_json(named_struct('comment', " in key and "'reason_code', " in key
    demo = render("jev_render_key", {"column_name": "c", "context": [], "fails_if": "x"},
                  env={"JEV_MODE": "demo"})
    assert "'demo', 'nested'" in demo


@pytest.mark.slow
@pytest.mark.parametrize("args,msg", [
    ({"fails_if": ""}, "non-empty sentence"),
    ({"fails_if": "x", "criteria": {"maybe": "?"}}, "keys must be true/false"),
])
def test_question_validation(args, msg):
    res = dbt("run-operation", "jev_render_question", "--args", json.dumps(args))
    assert res.returncode != 0 and msg in res.stdout + res.stderr


@pytest.mark.slow
def test_bad_mode_is_rejected():
    key = dbt("run-operation", "jev_render_key", "--args",
              '{"column_name": "c", "context": [], "fails_if": "x"}', env={"JEV_MODE": "maybe"})
    assert key.returncode != 0 and "must be 'live' or 'demo'" in key.stdout + key.stderr


@pytest.mark.slow
def test_compiled_test_sql_reads_judgments():
    res = dbt("compile", "--select", "reviews_body_matches_stars")
    assert res.returncode == 0, res.stdout + res.stderr
    sql = next((JAFFLE / "target/compiled").rglob("reviews_body_matches_stars.sql")).read_text()
    assert "jev_demo.jev.judgments" in sql and "judged.p >= 0.8" in sql
    assert "except (__jev_key)" in sql and "where judged.p is null or" in sql
```

Note: `dbt compile` on the `render` target needs the seeds' models to resolve; if compile fails
because DuckDB cannot introspect absent relations, run `dbt("seed")` + `dbt("run", "--select",
"staging")`... that would execute hooks — instead pass `--no-introspect`? Prefer: compile only the
test node with `--select reviews_body_matches_stars` (dbt compiles ephemeral refs lazily). If it
still needs relations, mark this one test `xfail(strict=False)` with the reason and rely on the
integration test in Task 8; do not add workarounds that change macro behaviour.


- [ ] **Step 5: Run tests**

Run: `uv run pytest -q` (the `slow` tests run by default; they take ~1 min) → Expected: PASS.
`uv run ruff check` → clean.

- [ ] **Step 6: Commit** — `git commit -m "feat(dbt): project on dbt-databricks, shared jev macros, jev_expect as a plain test"`

---

### Task 6: The `jev_judge` post-hook and the run summary

**Files:**
- Create: `jaffle_shop/macros/jev_judge.sql`, `jaffle_shop/macros/jev_summary.sql`
- Modify: `jaffle_shop/macros/jev_render.sql` (add `jev_render_judge`)
- Test: `tests/test_jev_judge_sql.py`

**Interfaces:**
- Consumes: Task 5 macros.
- Produces: `jev_tests_for(node_id) -> list[test node]`,
  `jev_judge_sql(test_node, relation) -> {"count": sql, "insert": sql, "inserted": sql}`,
  `jev_judge()` (the post-hook; runs statements via `run_query`, renders to ''),
  `jev_summary()` (on-run-end; logs two lines).

- [ ] **Step 1: Write the failing render test**

`tests/test_jev_judge_sql.py`:

```python
import re

import pytest

from tests.dbt_helpers import render


@pytest.fixture(scope="module")
def sql():
    return render("jev_render_judge", {"model_name": "stg_reviews"})


def _sections(text):
    return dict(re.findall(r"-- (\w+)\n(.*?)(?=\n-- \w+\n|\Z)", text, re.S))


@pytest.mark.slow
def test_three_statements(sql):
    assert set(_sections(sql)) == {"count", "insert", "inserted"}


@pytest.mark.slow
def test_insert_packs_by_token_budget_and_row_cap(sql):
    ins = _sections(sql)["insert"]
    assert ins.lstrip().startswith("insert into jev_demo.jev.judgments (")
    assert "left anti join" in ins and "where p is not null" in ins          # cache
    assert "/ 3.0) + 20" in ins                                              # token estimate
    assert "/ 48000)" in ins and "/ 256)" in ins                              # budget, row cap
    assert "REPARTITION(4)" in ins                                            # concurrency
    assert "jev_demo.jev.noul_pack(transform(items, x -> x.state)" in ins     # one call per pack
    assert ins.count("noul_pack(") == 1
    assert "posexplode(items)" in ins and "r.values[pos]" in ins
    assert "est > 30000" in ins and "row exceeds token limit" in ins          # oversized rows


@pytest.mark.slow
def test_key_matches_the_test_macro(sql):
    ins = _sections(sql)["insert"]
    assert "sha2(concat_ws(chr(31), 'jev-1.13.0', 'live', 'nested', " in ins
    assert "to_json(named_struct('body', " in ins and "'stars', " in ins


@pytest.mark.slow
def test_demo_mode_uses_demo_function():
    demo = render("jev_render_judge", {"model_name": "stg_reviews"}, env={"JEV_MODE": "demo"})
    assert "jev_demo.jev.noul_pack_demo(" in demo and "'demo', 'nested'" in demo


@pytest.mark.slow
def test_model_without_semantic_tests_renders_nothing():
    assert render("jev_render_judge", {"model_name": "stg_orders"}).strip() == ""
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_jev_judge_sql.py -q` → FAIL
(`jev_render_judge` not found).

- [ ] **Step 3: Implement `jaffle_shop/macros/jev_judge.sql`**

```sql
{#-
  Post-hook on every model (dbt_project.yml): judges the states of this model's jev_expect tests
  that have no successful judgment yet, and appends them to jev_demo.jev.judgments.

  Per test: one count query, one INSERT ... SELECT that calls the UC function once per pack, one
  count of what was inserted, one hook_runs row. Raises if inserted != missing.
  Packs are cut by estimated tokens (budget) and a row cap; REPARTITION(n) caps how many packs run
  at once (the function is Arrow-batched: packs in one partition run one after another).
-#}

{% macro jev_tests_for(node_id) %}
  {%- set tests = [] -%}
  {%- for n in graph.nodes.values() -%}
    {%- if n.resource_type == 'test' and n.attached_node == node_id
          and n.test_metadata and n.test_metadata.name == 'jev_expect'
          and n.config.enabled -%}
      {%- do tests.append(n) -%}
    {%- endif -%}
  {%- endfor -%}
  {{ return(tests | sort(attribute='name')) }}
{% endmacro %}

{% macro jev_judge_sql(t, relation) %}
  {%- set kw = t.test_metadata.kwargs -%}
  {%- set column = kw['column_name'] -%}
  {%- set context = kw.get('context') or [] -%}
  {%- set question = jev_question(kw['fails_if'], kw.get('criteria')) -%}
  {%- set state = jev_state_expr(column, context) -%}
  {%- set key = jev_key_expr(state, question) -%}
  {%- set judgments = jev_relation('judgments') -%}
  {%- set limit = var('jev_row_token_limit') -%}
  {%- set model_lit = jev_sql_string(var('jev_model')) -%}
  {%- set result_schema = "values ARRAY<DOUBLE>, input_tokens BIGINT, model STRING, error STRING, attempts INT, retries ARRAY<STRUCT<attempt: INT, status: INT, t: DOUBLE>>, pack_uuid STRING, started DOUBLE, finished DOUBLE" -%}
  {%- set common -%}
with tested as (
  select distinct {{ key }} as key, {{ state }} as state
  from {{ relation }}
  where {{ adapter.quote(column) }} is not null
),
missing as (
  select tested.key, tested.state,
         cast(ceil((length(tested.state) + {{ question | length }}) / 3.0) + 20 as bigint) as est
  from tested
  left anti join (select key from {{ judgments }} where p is not null) done
    on done.key = tested.key
)
  {%- endset -%}
  {%- set count_sql -%}
{{ common }}
select (select count(*) from tested) as tested,
       count(*) as missing,
       count_if(est > {{ limit }}) as oversized
from missing
  {%- endset -%}
  {%- set insert_sql -%}
insert into {{ judgments }} (
  key, test_name, model_name, question, state, p, requested_model, answered_model, mode, layout,
  pack_uuid, pack_rows, pack_tokens, pack_est_tokens, attempts, retry_statuses, error,
  started_at, finished_at, invocation_id, judged_at
)
{{ common }},
fit as (select * from missing where est <= {{ limit }}),
bucketed as (
  select key, state, est,
         floor((sum(est) over (order by key rows between unbounded preceding and current row) - est)
               / {{ var('jev_pack_token_budget') }}) as bucket
  from fit
),
numbered as (
  select key, state, est, bucket,
         floor((row_number() over (partition by bucket order by key) - 1)
               / {{ var('jev_pack_max_rows') }}) as sub
  from bucketed
),
packs as (
  select /*+ REPARTITION({{ var('jev_max_concurrency') }}) */ bucket, sub,
         array_sort(collect_list(named_struct('key', key, 'state', state, 'est', est))) as items
  from numbered
  group by bucket, sub
),
called as (
  select items,
         from_json({{ jev_function() }}(transform(items, x -> x.state), {{ jev_sql_string(question) }}, {{ model_lit }}),
                   '{{ result_schema }}') as r
  from packs
),
exploded as (
  select r, size(items) as pack_rows,
         aggregate(items, cast(0 as bigint), (acc, x) -> acc + x.est) as pack_est, pos, item
  from called
  lateral view posexplode(items) e as pos, item
)
select item.key, {{ jev_sql_string(t.name) }}, {{ jev_sql_string(t.attached_node.split('.')[-1]) }},
       {{ jev_sql_string(question) }}, item.state, r.values[pos], {{ model_lit }}, r.model,
       {{ jev_sql_string(jev_mode()) }}, 'nested', r.pack_uuid, pack_rows, r.input_tokens, pack_est,
       r.attempts, transform(r.retries, x -> x.status), r.error,
       timestamp_seconds(r.started), timestamp_seconds(r.finished),
       {{ jev_sql_string(invocation_id) }}, current_timestamp()
from exploded
union all
select key, {{ jev_sql_string(t.name) }}, {{ jev_sql_string(t.attached_node.split('.')[-1]) }},
       {{ jev_sql_string(question) }}, state, cast(null as double), {{ model_lit }},
       cast(null as string), {{ jev_sql_string(jev_mode()) }}, 'nested', cast(null as string),
       cast(null as int), cast(null as bigint), est, cast(0 as int), cast(null as array<int>),
       concat('row exceeds token limit (est ', est, ' tokens > {{ limit }})'),
       cast(null as timestamp), cast(null as timestamp),
       {{ jev_sql_string(invocation_id) }}, current_timestamp()
from missing
where est > {{ limit }}
  {%- endset -%}
  {%- set inserted_sql -%}
select count(*) from {{ judgments }}
where invocation_id = {{ jev_sql_string(invocation_id) }} and test_name = {{ jev_sql_string(t.name) }}
  {%- endset -%}
  {{ return({"count": count_sql, "insert": insert_sql, "inserted": inserted_sql}) }}
{% endmacro %}

{% macro jev_judge() %}
  {%- if not execute or flags.WHICH not in ['run', 'build'] -%}{{ return('') }}{%- endif -%}
  {%- for t in jev_tests_for(model.unique_id) -%}
    {%- set s = jev_judge_sql(t, this) -%}
    {%- set c = run_query(s['count']) -%}
    {%- set tested = c.columns[0].values()[0] | int -%}
    {%- set missing = c.columns[1].values()[0] | int -%}
    {%- set oversized = c.columns[2].values()[0] | int -%}
    {%- if missing > 0 -%}{%- do run_query(s['insert']) -%}{%- endif -%}
    {%- set inserted = run_query(s['inserted']).columns[0].values()[0] | int -%}
    {%- do run_query("insert into " ~ jev_relation('hook_runs') ~ " values ("
          ~ jev_sql_string(invocation_id) ~ ", " ~ jev_sql_string(t.name) ~ ", "
          ~ jev_sql_string(model.name) ~ ", " ~ jev_sql_string(jev_mode()) ~ ", "
          ~ jev_sql_string(var('jev_model')) ~ ", " ~ tested ~ ", " ~ missing ~ ", "
          ~ oversized ~ ", " ~ inserted ~ ", current_timestamp())") -%}
    {%- do log("Jev · " ~ t.name ~ " · " ~ tested ~ " tested · " ~ missing ~ " judged now · "
              ~ oversized ~ " too long", info=True) -%}
    {%- if inserted != missing -%}
      {{ exceptions.raise_compiler_error("jev_judge: " ~ t.name ~ ": inserted " ~ inserted
          ~ " rows for " ~ missing ~ " missing states (one evaluation per row violated)") }}
    {%- endif -%}
  {%- endfor -%}
  {{ return('') }}
{% endmacro %}
```

- [ ] **Step 4: Add the render helper** (append to `jev_render.sql`):

```sql
{% macro jev_render_judge(model_name) %}
  {%- set node = graph.nodes['model.jaffle_shop.' ~ model_name] -%}
  {%- set parts = [] -%}
  {%- for t in jev_tests_for(node.unique_id) -%}
    {%- set s = jev_judge_sql(t, node.relation_name) -%}
    {%- do parts.append('-- count\n' ~ s['count'] ~ '\n-- insert\n' ~ s['insert'] ~ '\n-- inserted\n' ~ s['inserted']) -%}
  {%- endfor -%}
  {{ print('-- BEGIN\n' ~ (parts | join('\n')) ~ '\n-- END') }}
{% endmacro %}
```

- [ ] **Step 5: Implement `jaffle_shop/macros/jev_summary.sql`**

```sql
{#- on-run-end: one summary line + the once-per-row counters for this invocation. -#}
{% macro jev_summary() %}
  {%- if not execute or flags.WHICH not in ['run', 'build'] -%}{{ return('') }}{%- endif -%}
  {%- set inv = jev_sql_string(invocation_id) -%}
  {%- set h = run_query("select count(*), coalesce(sum(tested), 0), coalesce(sum(missing), 0),
        coalesce(sum(inserted), 0), coalesce(sum(oversized), 0), max(mode), max(requested_model)
      from " ~ jev_relation('hook_runs') ~ " where invocation_id = " ~ inv) -%}
  {%- set hooks = h.columns[0].values()[0] | int -%}
  {%- if hooks == 0 -%}{{ return('') }}{%- endif -%}
  {%- set tested = h.columns[1].values()[0] | int -%}
  {%- set missing = h.columns[2].values()[0] | int -%}
  {%- set inserted = h.columns[3].values()[0] | int -%}
  {%- set oversized = h.columns[4].values()[0] | int -%}
  {%- set mode = h.columns[5].values()[0] -%}
  {%- set r = run_query("select count(*), coalesce(sum(pack_tokens), 0), coalesce(sum(pack_rows), 0),
        coalesce(sum(attempts - 1), 0), coalesce(sum(size(filter(retry_statuses, s -> s = 429))), 0),
        count_if(error is not null),
        coalesce((unix_micros(max(finished_at)) - unix_micros(min(started_at))) / 1e6, 0),
        max(answered_model)
      from " ~ jev_relation('requests') ~ " where invocation_id = " ~ inv) -%}
  {%- set packs = r.columns[0].values()[0] | int -%}
  {%- set tokens = r.columns[1].values()[0] | int -%}
  {%- set pack_rows = r.columns[2].values()[0] | int -%}
  {%- set retries = r.columns[3].values()[0] | int -%}
  {%- set throttled = r.columns[4].values()[0] | int -%}
  {%- set errors = r.columns[5].values()[0] | int -%}
  {%- set span = r.columns[6].values()[0] | float -%}
  {%- set answered = r.columns[7].values()[0] or var('jev_model') -%}
  {%- set dups = run_query("select count(*) from (select key from " ~ jev_relation('judgments')
        ~ " where p is not null group by key having count(*) > 1)").columns[0].values()[0] | int -%}
  {%- set cached = ((tested - missing) * 100 / tested) if tested else 0 -%}
  {%- set cost = tokens * var('jev_price_per_mtok_usd') / 1000000 -%}
  {%- set label = 'SIMULATED' if mode == 'demo' else 'LIVE' -%}
  {%- set line1 = "Jev · {:,} judgments · {:.0f}% cached · {:,} requests · {:,} retries ({:,}× 429) · {:.1f} s Jev · ${:.3f} · {} {} budget={}k".format(
        tested, cached, packs, retries, throttled, span, cost, label, answered,
        (var('jev_pack_token_budget') / 1000) | int) -%}
  {%- if errors -%}{%- set line1 = line1 ~ " · " ~ errors ~ " errors" -%}{%- endif -%}
  {%- set ok = (inserted == missing) and (pack_rows == inserted - oversized) and (dups == 0) -%}
  {%- set line2 = "Jev · once-per-row {}: {:,} inserted = {:,} missing · packs sum {:,} (+{:,} too long) · {:,} duplicate keys".format(
        'OK' if ok else 'VIOLATED', inserted, missing, pack_rows, oversized, dups) -%}
  {%- do log(line1, info=True) -%}
  {%- do log(line2, info=True) -%}
  {{ return('') }}
{% endmacro %}
```

- [ ] **Step 6: Run tests** — `uv run pytest -q` → PASS; `uv run ruff check` → clean.

- [ ] **Step 7: Commit** — `git commit -m "feat(dbt): jev_judge post-hook (token-budgeted packs, one call per pack) and run summary"`

---

### Task 7: Port the regex baselines to Spark SQL

**Files:**
- Create: `jaffle_shop/tests/baseline/baseline_*.sql` (4 files), `tests/test_baselines.py`

**Interfaces:** none new. Test names stay `baseline_<semantic test name>`.

Porting rules (DuckDB → Databricks SQL), change nothing else:
- `regexp_matches(x, 'p')` → `regexp(x, 'p')` (Databricks `regexp` = RLIKE, Java regex).
- `len(regexp_extract_all(s, 'p'))` → `size(regexp_extract_all(s, 'p', 0))`.
- **Backslashes:** Databricks SQL string literals treat `\` as an escape. Every `\` in a DuckDB
  pattern becomes `\\` (so `\b` → `\\b`, `\d` → `\\d`, `\s` → `\\s`, `\.` → `\\.`).
- `(?i)` works unchanged in Java regex. `''` inside literals stays `''`.

- [ ] **Step 1: Write the equivalence test**

`tests/test_baselines.py`:

```python
"""The Spark port must use exactly demo 04's patterns: same regexes, same conditions."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DEMO4 = Path.home() / "Projects/jev-demo-4/jaffle_shop/tests/baseline"
NAMES = ["customers_full_name_is_a_person", "returns_comment_matches_reason_code",
         "reviews_body_matches_stars", "tickets_body_has_no_pii"]

_LIT = re.compile(r"'((?:[^']|'')*)'")


def _patterns(sql: str, spark: bool) -> list[str]:
    pats = [m.group(1) for m in _LIT.finditer(sql)]
    return [p.replace("\\\\", "\\") if spark else p for p in pats]


def _normalize(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = sql.replace("regexp_matches(", "regexp(").replace("len(regexp_extract_all(", "size(regexp_extract_all(")
    return re.sub(r"\s+", " ", sql)


@pytest.mark.skipif(not DEMO4.exists(), reason="demo 04 checkout not present")
@pytest.mark.parametrize("name", NAMES)
def test_same_patterns_as_demo04(name):
    ours = (ROOT / f"jaffle_shop/tests/baseline/baseline_{name}.sql").read_text()
    theirs = (DEMO4 / f"baseline_{name}.sql").read_text()
    assert _patterns(ours, spark=True) == _patterns(theirs, spark=False)


@pytest.mark.parametrize("name", NAMES)
def test_no_duckdb_only_functions_left(name):
    sql = (ROOT / f"jaffle_shop/tests/baseline/baseline_{name}.sql").read_text()
    assert "regexp_matches(" not in sql and "len(" not in sql
    assert re.search(r"(?<!\\)\\[bdsw.]", sql.replace("\\\\", "")) is None  # every \ doubled
```

- [ ] **Step 2: Run to verify failure** — FAIL (files missing).

- [ ] **Step 3: Port the four files** following the rules. Example, the reviews baseline:

```sql
{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
with lexicon as (
  select *,
    size(regexp_extract_all(lower(body), '\\b(great|love|loved|amazing|delicious|best|perfect|excellent|fantastic|tasty|recommend|good|lovely|fresh|yum)\\b', 0))
    - size(regexp_extract_all(lower(body), '\\b(never|worst|awful|terrible|disgusting|cold|raw|bad|horrible|inedible|refund|disappointed|soggy|gross)\\b', 0))
      as sentiment
  from {{ ref('stg_reviews') }}
)
select * from lexicon
where (stars >= 4 and sentiment < 0) or (stars <= 2 and sentiment > 0)
```

Note: `regexp_extract_all(s, p, 0)` extracts group 0 (whole match); DuckDB's default is also the
whole match, so the counts agree. The third argument `0` is a number, not a pattern: the
`_patterns` helper only reads quoted literals.

- [ ] **Step 4: Run tests** — PASS. The row-level equivalence on real data is checked in Task 8.

- [ ] **Step 5: Commit** — `git commit -m "feat(baseline): demo 04 regex baselines ported to Spark SQL, same patterns"`

---

### Task 8: Deploy to the dev warehouse and prove it end to end in demo mode

Standing OK: this runs only on the 2X-Small `jev-demo-5` warehouse, demo mode. No live Jev call.

**Files:**
- Create: `tests/integration/__init__.py`, `tests/integration/test_databricks_demo.py`,
  `scripts/demo04_reference.py` (exports demo 04 per-row baseline flags for comparison)
- Modify: none of the macros unless a test proves them wrong (then fix + add an offline test)

**Interfaces:**
- Consumes: everything above. Needs `eval "$(uv run python scripts/jev_env.py)"` and dbt auth.

- [ ] **Step 1: Deploy the platform objects**

```bash
cd ~/Projects/jev-demo-5
uv run python scripts/deploy.py            # read the statements
uv run python scripts/deploy.py --apply --only schema judgments hook_runs requests noul_pack_demo
```

The live `noul_pack` needs the secret `jev_demo.jev.typesafe_api_key`, which the user creates;
deploy it only once `databricks secrets-uc get-secret jev_demo.jev.typesafe_api_key` succeeds.

- [ ] **Step 2: Establish dbt auth**

Run `eval "$(uv run python scripts/jev_env.py)" && cd jaffle_shop && uv run dbt debug --profiles-dir .`.
`auth_type: oauth` (U2M) may open a browser once. If it cannot complete non-interactively, check
the installed adapter's accepted auth types (`uv run python -c "import dbt.adapters.databricks.credentials as c, inspect; print(inspect.getsource(c))" | grep -n auth_type`)
for a CLI-profile/SDK-default option and use it in `profiles.yml`. Never write a token into any
file, and never print one. If only a browser flow works, stop and ask the user to run
`dbt debug` once.

- [ ] **Step 3: Write the integration tests**

`tests/integration/test_databricks_demo.py` (demo mode only; runs dbt with `--target dev`):

```python
"""Demo-mode end-to-end on the dev warehouse. Run: uv run pytest -m databricks -q
(after: eval "$(uv run python scripts/jev_env.py)"). Never runs a live Jev call."""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from jevdbx.databricks import Sql

pytestmark = pytest.mark.databricks
ROOT = Path(__file__).parents[2]
JAFFLE = ROOT / "jaffle_shop"
DEMO4_DB = Path.home() / "Projects/jev-demo-4/jaffle_shop/jaffle_shop.duckdb"
BASELINES = ["customers_full_name_is_a_person", "returns_comment_matches_reason_code",
             "reviews_body_matches_stars", "tickets_body_has_no_pii"]
ID_COL = {"customers_full_name_is_a_person": "customer_id",
          "returns_comment_matches_reason_code": "return_id",
          "reviews_body_matches_stars": "review_id", "tickets_body_has_no_pii": "ticket_id"}


def dbt(*args):
    env = {**os.environ, "JEV_MODE": "demo", "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    return subprocess.run(["uv", "run", "dbt", *args, "--profiles-dir", ".", "--target", "dev"],
                          cwd=JAFFLE, capture_output=True, text=True, env=env, timeout=1800)


def clear_demo_rows(sql):
    assert sql.run("delete from jev_demo.jev.judgments where mode = 'demo'").state == "SUCCEEDED"


@pytest.fixture(scope="module")
def sql():
    return Sql()


@pytest.fixture(scope="module")
def cold_build(sql):
    clear_demo_rows(sql)
    seed = dbt("seed")
    assert seed.returncode == 0, seed.stdout[-3000:]
    return dbt("build", "--select", "+tag:semantic", "tag:baseline")


def test_cold_build_judges_every_state_once(cold_build):
    out = cold_build.stdout
    assert cold_build.returncode == 0, out[-4000:]
    assert "SIMULATED" in out and "once-per-row OK" in out and "0% cached" in out
    # 1,057 = demo 04's distinct (test, state) count at pack=1. If this differs, find out why
    # (e.g. a to_json difference) before touching the number.
    assert "1,057 judgments" in out


def test_rerun_is_fully_cached(cold_build):
    res = dbt("build", "--select", "+tag:semantic")
    assert res.returncode == 0, res.stdout[-3000:]
    assert "100% cached" in res.stdout and " 0 requests" in res.stdout


def test_single_python_eval_in_insert_plan(sql, cold_build):
    res = subprocess.run(
        ["uv", "run", "dbt", "run-operation", "jev_render_judge", "--args",
         json.dumps({"model_name": "stg_reviews"}), "--profiles-dir", ".", "--target", "dev"],
        cwd=JAFFLE, capture_output=True, text=True, env={**os.environ, "JEV_MODE": "demo"})
    insert = res.stdout.split("-- insert\n", 1)[1].split("\n-- inserted\n", 1)[0]
    plan = "\n".join(str(r[0]) for r in sql.run("explain formatted " + insert).rows)
    nodes = set(re.findall(r"^\(\d+\) \w*EvalPython\w*", plan, re.M))
    assert len(nodes) == 1, plan[:3000]


def test_stored_failures_have_jev_p(sql, cold_build):
    total, with_p = sql.run(
        "select count(*), count(jev_p) from "
        "jev_demo.jaffle_shop_dbt_test__audit.reviews_body_matches_stars").rows[0]
    assert int(total) == int(with_p) > 0


def test_staging_matches_demo04_and_has_no_nulls(sql, cold_build):
    counts = {m: int(sql.run(f"select count(*) from jev_demo.jaffle_shop.{m}").scalar())
              for m in ["stg_customers", "stg_orders", "stg_returns", "stg_reviews", "stg_tickets"]}
    assert counts == {"stg_customers": 500, "stg_orders": 1500, "stg_returns": 200,
                      "stg_reviews": 400, "stg_tickets": 200}
    nulls = sql.run(
        "select (select count(*) from jev_demo.jaffle_shop.stg_customers where full_name is null or email is null)"
        " + (select count(*) from jev_demo.jaffle_shop.stg_returns where comment is null or reason_code is null)"
        " + (select count(*) from jev_demo.jaffle_shop.stg_reviews where body is null or stars is null)"
        " + (select count(*) from jev_demo.jaffle_shop.stg_tickets where body is null)").scalar()
    assert int(nulls) == 0  # so Spark's to_json NULL-field omission cannot change any state


@pytest.mark.skipif(not DEMO4_DB.exists(), reason="demo 04 DuckDB file not present")
@pytest.mark.parametrize("name", BASELINES)
def test_baselines_flag_same_rows_as_demo04(sql, cold_build, name):
    ref = subprocess.run(["uv", "run", "python", "scripts/demo04_reference.py", name],
                         cwd=ROOT, capture_output=True, text=True)
    if ref.returncode == 2:
        pytest.skip(ref.stdout.strip())
    theirs = set(json.loads(ref.stdout))
    ours = {int(r[0]) for r in sql.run(
        f"select {ID_COL[name]} from jev_demo.jaffle_shop_dbt_test__audit.baseline_{name}").rows}
    assert ours == theirs


def test_oversized_rows_are_reported_not_sent(sql, cold_build):
    clear_demo_rows(sql)
    res = dbt("build", "--select", "+stg_reviews", "--vars", "{jev_row_token_limit: 40}")
    assert res.returncode == 0, res.stdout[-3000:]
    assert " 0 requests" in res.stdout and "+400 too long" in res.stdout
    errs = sql.run("select count(*) from jev_demo.jev.judgments where mode = 'demo' "
                   "and test_name = 'reviews_body_matches_stars' "
                   "and error like 'row exceeds token limit%'").scalar()
    assert int(errs) == 400
    clear_demo_rows(sql)
```

`scripts/demo04_reference.py` (reads demo 04's DuckDB read-only; exit 2 = nothing to compare):

```python
"""Print demo 04's stored baseline failures for one test as a JSON id list (read-only)."""

import json
import sys
from pathlib import Path

import duckdb

DB = Path.home() / "Projects/jev-demo-4/jaffle_shop/jaffle_shop.duckdb"
ID = {"customers_full_name_is_a_person": "customer_id",
      "returns_comment_matches_reason_code": "return_id",
      "reviews_body_matches_stars": "review_id", "tickets_body_has_no_pii": "ticket_id"}


def main(name: str) -> int:
    con = duckdb.connect(str(DB), read_only=True)
    table = f"main_dbt_test__audit.baseline_{name}"
    try:
        ids = sorted(int(r[0]) for r in con.execute(f"select {ID[name]} from {table}").fetchall())
    except duckdb.CatalogException:
        print(f"demo 04 has no {table}")
        return 2
    print(json.dumps(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
```

`duckdb` is needed only for this script: add `"duckdb>=1.5"` to the `dev` dependency group.

- [ ] **Step 4: Run** — `uv run pytest -m databricks -q` → PASS. Fix macros for real failures,
adding an offline test for each fix. Record wall times in the task report.

- [ ] **Step 5: Commit** — `git commit -m "test(integration): demo-mode end-to-end on Databricks -- once per row, cache, plan, baselines"`

---

### Task 9: Production dataset pipeline and production models

**Files:**
- Create: `scripts/fetch_reviews.py`, `scripts/audit_sample.py`, `tests/test_fetch_reviews.py`,
  `tests/fixtures/finefoods_sample.txt`, `jaffle_shop/models/production/stg_product_reviews.sql`,
  `jaffle_shop/models/production/schema.yml`,
  `jaffle_shop/tests/production_baseline/baseline_product_reviews_body_matches_stars.sql`

**Interfaces:**
- Produces (pure functions in `scripts/fetch_reviews.py`, importable by tests):
  - `parse_snap(lines: Iterable[str]) -> Iterator[dict]` → `{"id": int, "score": int, "summary": str, "text": str}`
  - `sample(rows: list[dict], n: int, seed: int) -> list[dict]` (sorted by id)
  - `plant_flips(rows, rate: float, seed: int) -> tuple[list[dict], list[dict]]` →
    (rows with `stars`, flips `{"id", "original_stars", "planted_stars"}`)
  - `split(rows, first: int) -> tuple[list, list]`
  - CLI: `--source PATH` (local `finefoods.txt.gz` or Kaggle `Reviews.csv`), `--download` (prints
    URL, filename and size first and requires the user's go-ahead in chat before it is ever run),
    `--out data/`, `--upload` (to `/Volumes/jev_demo/production/raw/`).

- [ ] **Step 1: Fixture + failing tests**

`tests/fixtures/finefoods_sample.txt` — 12 records in SNAP format, e.g.:

```
product/productId: B001E4KFG0
review/userId: A3SGXH7AUHU8GW
review/profileName: delmartian
review/helpfulness: 1/1
review/score: 5.0
review/time: 1303862400
review/summary: Good Quality Dog Food
review/text: I have bought several of the Vitality canned dog food products and have found them all to be of good quality.

```

Write 12 such records (invented text; scores covering 1,2,3,4,5; one with non-ASCII).

`tests/test_fetch_reviews.py`:

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("fetch_reviews", ROOT / "scripts/fetch_reviews.py")
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
FIX = ROOT / "tests/fixtures/finefoods_sample.txt"


def rows():
    return list(fr.parse_snap(FIX.read_text(encoding="utf-8").splitlines(keepends=True)))


def test_parse_keeps_only_safe_fields_with_1_based_ids():
    rs = rows()
    assert len(rs) == 12 and [r["id"] for r in rs] == list(range(1, 13))
    assert set(rs[0]) == {"id", "score", "summary", "text"}
    assert rs[0]["score"] == 5 and rs[0]["summary"] == "Good Quality Dog Food"


def test_sample_is_deterministic_and_sorted():
    many = [{"id": i, "score": 5, "summary": "", "text": ""} for i in range(1, 1001)]
    a, b = fr.sample(many, 100, 42), fr.sample(many, 100, 42)
    assert a == b and len(a) == 100 and [r["id"] for r in a] == sorted(r["id"] for r in a)


def test_flips_cross_the_pole_and_never_touch_three_stars():
    many = [{"id": i, "score": (i % 5) + 1, "summary": "", "text": ""} for i in range(1, 10001)]
    out, flips = fr.plant_flips(many, 0.03, 42)
    by_id = {r["id"]: r for r in out}
    assert 250 <= len(flips) <= 350
    for f in flips:
        assert (f["original_stars"], f["planted_stars"]) in {(1, 5), (5, 1), (2, 4), (4, 2)}
        assert by_id[f["id"]]["stars"] == f["planted_stars"]
    flipped = {f["id"] for f in flips}
    assert all(r["stars"] == r["score"] for r in out if r["id"] not in flipped)
    assert all(r["score"] != 3 for r in out if r["id"] in flipped)
    assert fr.plant_flips(many, 0.03, 42) == (out, flips)


def test_split():
    a, b = fr.split(list(range(10)), 7)
    assert a == list(range(7)) and b == [7, 8, 9]
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `scripts/fetch_reviews.py`**

```python
"""Production dataset: Amazon Fine Food Reviews (SNAP, McAuley & Leskovec, WWW 2013).

Keeps only id, score, summary and text (drops user ids and profile names), samples 100,000 with
seed 42, plants star flips across the pole (1<->5, 2<->4) on 3% of the non-3-star rows, writes two
Parquet files (95,000 + 5,000, for the incremental proof) and eval/production_flips.csv.

    uv run python scripts/fetch_reviews.py --source data/finefoods.txt.gz --out data/
    uv run python scripts/fetch_reviews.py --source data/finefoods.txt.gz --out data/ --upload

Downloading is a separate, explicit step (`--download`), done only after the user said yes.
"""

import argparse
import csv
import gzip
import random
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://snap.stanford.edu/data/finefoods.txt.gz"
FLIPS = {1: 5, 5: 1, 2: 4, 4: 2}
VOLUME = "/Volumes/jev_demo/production/raw"


def parse_snap(lines: Iterable[str]) -> Iterator[dict]:
    rec: dict = {}
    n = 0
    for line in lines:
        line = line.rstrip("\n")
        if not line.strip():
            if rec:
                n += 1
                yield {"id": n, "score": int(float(rec["review/score"])),
                       "summary": rec.get("review/summary", ""), "text": rec.get("review/text", "")}
                rec = {}
            continue
        key, _, value = line.partition(": ")
        rec[key] = value
    if rec:
        n += 1
        yield {"id": n, "score": int(float(rec["review/score"])),
               "summary": rec.get("review/summary", ""), "text": rec.get("review/text", "")}


def parse_kaggle_csv(path: Path) -> Iterator[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            yield {"id": int(r["Id"]), "score": int(r["Score"]), "summary": r["Summary"], "text": r["Text"]}


def sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    picked = random.Random(seed).sample(rows, n)
    return sorted(picked, key=lambda r: r["id"])


def plant_flips(rows: list[dict], rate: float, seed: int) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    eligible = [r["id"] for r in rows if r["score"] in FLIPS]
    chosen = set(rng.sample(eligible, round(len(eligible) * rate)))
    out, flips = [], []
    for r in rows:
        stars = r["score"]
        if r["id"] in chosen:
            stars = FLIPS[r["score"]]
            flips.append({"id": r["id"], "original_stars": r["score"], "planted_stars": stars})
        out.append({**r, "stars": stars})
    return out, flips


def split(rows: list, first: int) -> tuple[list, list]:
    return rows[:first], rows[first:]


def _read_source(path: Path) -> list[dict]:
    if path.suffix == ".csv":
        return list(parse_kaggle_csv(path))
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="latin-1") as f:
        return list(parse_snap(f))


def _write_parquet(rows: list[dict], path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({
        "id": [r["id"] for r in rows],
        "stars": [r["stars"] for r in rows],
        "summary": [r["summary"] for r in rows],
        "text": [r["text"] for r in rows],
    })
    pq.write_table(table, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "data")
    ap.add_argument("--n", type=int, default=100_000)
    ap.add_argument("--first", type=int, default=95_000)
    ap.add_argument("--rate", type=float, default=0.03)
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.download:
        import urllib.request

        dest = args.out / "finefoods.txt.gz"
        print(f"downloading {URL} -> {dest}")
        urllib.request.urlretrieve(URL, dest)
        args.source = dest
    if not args.source:
        ap.error("--source or --download required")
    rows = _read_source(args.source)
    planted, flips = plant_flips(sample(rows, args.n, 42), args.rate, 42)
    a, b = split(planted, args.first)
    _write_parquet(a, args.out / "reviews_part1.parquet")
    _write_parquet(b, args.out / "reviews_part2.parquet")
    with open(ROOT / "eval/production_flips.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["id", "original_stars", "planted_stars"], lineterminator="\n")
        w.writeheader()
        w.writerows(flips)
    print(f"{len(rows):,} source rows -> {len(planted):,} sampled ({len(a):,} + {len(b):,}), "
          f"{len(flips):,} planted flips")
    if args.upload:
        from jevdbx.databricks import _client

        files = _client(None).files
        for name in ("reviews_part1.parquet",):  # part2 is uploaded later: the incremental proof
            with open(args.out / name, "rb") as fh:
                files.upload(f"{VOLUME}/{name}", fh, overwrite=True)
            print(f"uploaded {VOLUME}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Add `--upload-part2` that uploads `reviews_part2.parquet` the same way (the incremental step).

- [ ] **Step 4: Production models**

`jaffle_shop/models/production/stg_product_reviews.sql`:

```sql
{{ config(tags=['production']) }}
select cast(id as bigint) as review_id,
       cast(stars as int) as stars,
       concat_ws('\n', summary, text) as body
from read_files('/Volumes/jev_demo/production/raw/', format => 'parquet')
```

`jaffle_shop/models/production/schema.yml` — the demo 04 reviews test, verbatim sentence,
context, threshold and criteria, new name and tag:

```yaml
version: 2

models:
  - name: stg_product_reviews
    columns:
      - name: review_id
        data_tests: [unique, not_null]
      - name: stars
        data_tests:
          - not_null
          - accepted_values: {arguments: {values: [1, 2, 3, 4, 5], quote: false}}
      - name: body
        data_tests:
          - not_null
          - jev_expect:
              name: product_reviews_body_matches_stars
              arguments:
                fails_if: "The overall sentiment of the review `body` clearly contradicts its `stars` rating (1 = very bad, 5 = excellent)."
                context: [stars]
                threshold: 0.8
                criteria:
                  "true": "A glowing text with 1-2 stars, or an angry/negative text with 4-5 stars"
                  "false": "Sentiment roughly matches the stars, including sarcasm that matches a low rating and mixed 3-star reviews"
              config: {severity: warn, store_failures: true, tags: [production]}
```

Add a test in `tests/test_dbt_project.py`: the production block's `arguments` equal demo 04's
`reviews_body_matches_stars` arguments exactly.

`jaffle_shop/tests/production_baseline/baseline_product_reviews_body_matches_stars.sql`: the
Task 7 reviews baseline with `ref('stg_product_reviews')`, config
`tags=['production_baseline'], enabled=var('production', false)`. Add `tests/production_baseline`
to `test-paths` in `dbt_project.yml`.

- [ ] **Step 5: `scripts/audit_sample.py`** — reads flagged ids from
`jev_demo.jaffle_shop_dbt_test__audit.product_reviews_body_matches_stars`, removes the ids in
`eval/production_flips.csv`, samples 100 with seed 42, writes `data/production_audit.csv` with
columns `id, stars, body, label` (label empty, **no `jev_p`**) and prints how to label
(`real` = the text and stars genuinely disagree, `ok` = they don't). `score.py` (Task 10) reads
the labelled file and commits only `eval/production_audit_labels.csv` (`id,label`). Test the
pure sampling function (`pick_audit(flagged: set[int], planted: set[int], n, seed) -> list[int]`).

- [ ] **Step 6: Run tests** — `uv run pytest -q` → PASS; ruff clean.

- [ ] **Step 7: Commit** — `git commit -m "feat(production): review fetch/sample/plant pipeline, production model + tests, audit sampler"`

---

### Task 10: Scorecards and recording views

**Files:**
- Create: `scripts/score.py`, `scripts/show.py`, `eval/demo04_reference.json`,
  `tests/test_score.py`, `tests/test_show.py`

**Interfaces:**
- Consumes: `jevdbx.databricks.Sql`, `jevdbx.pricing`, golden key, flips, audit labels.
- Produces (pure, tested): `load_golden(path) -> dict[str, dict[int, str]]`,
  `metrics(flagged: set[int], golden: dict[int, str]) -> Metrics(flagged, tp, fp, fn,
  hard_neg_flagged, precision, recall, f1)`, `wilson(k, n, z=1.96) -> tuple[float, float]`,
  `audited_precision(planted_tp: int, unplanted_flagged: int, audit: dict[int, str]) ->
  tuple[float, float, float]` (point, lo, hi), `gate(results, run) -> tuple[bool, list[str]]`,
  `refuse_append_if_simulated(run) -> None` (raises `SystemExit` for mode demo).

Port demo 04's `scripts/score.py` (read it first). Keep: `Metrics`, `load_golden`, `metrics`,
gate rules and messages, the printed table layout, `append_report`. Change:
- Stored failures come from `jev_demo.jaffle_shop_dbt_test__audit.<test>` via `Sql().run`.
- Run provenance comes from `jev_demo.jev.hook_runs` + `requests` for the latest invocation
  (`order by recorded_at desc limit 1` → its `invocation_id`): mode, answered model, requests,
  tokens, retries, 429s, errors, Jev span. SIMULATED → banner + `--append` refused.
- `--run` executes `uv run dbt build --select +tag:semantic tag:baseline --target dev` (with
  `--vars '{production: true}' --select +tag:production tag:production_baseline` for
  `--production`); `--fresh` deletes this mode's judgments for the selected tests first
  (`delete from jev_demo.jev.judgments where mode = ... and test_name in (...)`).
- `eval/demo04_reference.json`: demo 04's logged gated runs, copied by hand from
  `~/Projects/jev-demo-4/docs/eval-results.md` (pack=1, pack=32/nested, pack=64/nested: requests,
  wall, cost, per-test P/R/F1 for Jev and baseline). The scorecard prints demo 04 pack=64/nested
  next to this run.
- Production mode: recall on planted flips, raw precision vs flips, audited precision with Wilson
  95% interval, baseline F1 on the same data, and the operational checks (0 errors, once-per-row
  OK from the summary, rerun 0 requests if `--rerun` given).
- `--append` writes the markdown block to `docs/eval-results.md` including warehouse, budget,
  requests, retries, 429s, tokens, Jev cost, and the est/actual token ratio from `requests`.

`tests/test_score.py` must cover: metrics on a hand-built golden dict (tp/fp/fn, hard negatives),
`wilson(8, 10)` ≈ (0.49, 0.94), `audited_precision(90, 50, {…40 real, 10 ok…})` = ((90+40)/(90+50) ≈ 0.929 …),
gate pass/fail messages matching demo 04's wording, SIMULATED refusal.

`scripts/show.py`: port demo 04's `show.py` views (`tests`, `rows`, `score`) to read from
Databricks; keep the phone-readable layout. `tests/test_show.py`: port demo 04's pure-function
tests (`load_jev_tests`, `format_headline`, `select_example_row`).

- [ ] Steps: failing tests → implement → PASS → ruff → commit
  `git commit -m "feat(score): yardstick and production scorecards on Databricks; show views"`

---

### Task 11: dbt inside Databricks — serverless notebook and bundle

**Files:**
- Create: `notebooks/jev_semantic_tests.py`, `databricks.yml`, `tests/test_bundle.py`

**Interfaces:**
- Consumes: the dbt project, `jevdbx.pricing`.

- [ ] **Step 1: Test the bundle and notebook shape**

`tests/test_bundle.py`:

```python
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_bundle_defines_serverless_notebook_job():
    b = yaml.safe_load((ROOT / "databricks.yml").read_text())
    job = b["resources"]["jobs"]["jev_semantic_tests"]
    task = job["tasks"][0]
    assert task["notebook_task"]["notebook_path"].endswith("notebooks/jev_semantic_tests.py")
    assert "new_cluster" not in task and "existing_cluster_id" not in task  # serverless
    params = {p["name"]: p["default"] for p in job["parameters"]}
    assert params["mode"] == "demo" and params["selection"] == "yardstick"


def test_notebook_never_prints_the_token():
    src = (ROOT / "notebooks/jev_semantic_tests.py").read_text()
    assert src.startswith("# Databricks notebook source")
    assert "apiToken()" in src and "DBT_DATABRICKS_TOKEN" in src
    assert "print(token" not in src and "display(token" not in src
```

- [ ] **Step 2: Write `databricks.yml`**

```yaml
bundle:
  name: jev-demo-5

include: []

sync:
  include: ["jaffle_shop/**", "notebooks/**", "src/**", "pyproject.toml"]
  exclude: ["jaffle_shop/target/**", "jaffle_shop/logs/**", "data/**", ".venv/**"]

targets:
  dev:
    mode: development
    default: true
    workspace:
      profile: jev-demo-5

resources:
  jobs:
    jev_semantic_tests:
      name: jev-semantic-tests
      parameters:
        - {name: mode, default: demo}
        - {name: selection, default: yardstick}
        - {name: warehouse, default: jev-demo-5}
      tasks:
        - task_key: dbt_build
          notebook_task:
            notebook_path: ./notebooks/jev_semantic_tests.py
```

- [ ] **Step 3: Write the notebook** (`notebooks/jev_semantic_tests.py`, Databricks source format):

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # Jev semantic dbt tests, run inside Databricks
# MAGIC `dbt build` on a serverless notebook; queries run on the SQL warehouse; Jev is the UC
# MAGIC function `jev_demo.jev.noul_pack`, whose key never leaves Unity Catalog.

# COMMAND ----------

# MAGIC %pip install -q "dbt-databricks==1.12.5"

# COMMAND ----------

dbutils.widgets.dropdown("mode", "demo", ["demo", "live"])
dbutils.widgets.dropdown("selection", "yardstick", ["yardstick", "production"])
dbutils.widgets.text("warehouse", "jev-demo-5")

# COMMAND ----------

import os
import subprocess
from pathlib import Path

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
warehouse = next(x for x in w.warehouses.list() if x.name == dbutils.widgets.get("warehouse"))
project = Path(os.getcwd()).parent / "jaffle_shop"
env = {
    **os.environ,
    "DATABRICKS_HOST": w.config.host.removeprefix("https://").rstrip("/"),
    "JEV_HTTP_PATH": f"/sql/1.0/warehouses/{warehouse.id}",
    "DBT_DATABRICKS_TOKEN": ctx.apiToken().get(),  # short-lived run token; never displayed
    "JEV_MODE": dbutils.widgets.get("mode"),
    "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
}
if dbutils.widgets.get("selection") == "production":
    args = ["build", "--vars", "{production: true}", "--select",
            "+tag:production", "tag:production_baseline"]
else:
    args = ["build", "--select", "+tag:semantic", "tag:baseline"]

# COMMAND ----------

res = subprocess.run(["dbt", *args, "--profiles-dir", ".", "--target", "notebook"],
                     cwd=project, env=env, capture_output=True, text=True)
print(res.stdout[-8000:])
summary = [line for line in res.stdout.splitlines() if "Jev ·" in line]
assert res.returncode == 0 or "WARN" in res.stdout, res.stderr[-3000:]

# COMMAND ----------

# MAGIC %md ## Summary

# COMMAND ----------

displayHTML("<pre>" + "\n".join(summary) + "</pre>")

# COMMAND ----------

# MAGIC %md ## Failing rows, with Jev's probability

# COMMAND ----------

tests = (["product_reviews_body_matches_stars"] if dbutils.widgets.get("selection") == "production"
         else ["customers_full_name_is_a_person", "returns_comment_matches_reason_code",
               "reviews_body_matches_stars", "tickets_body_has_no_pii"])
for t in tests:
    display(spark.sql(f"select * from jev_demo.jaffle_shop_dbt_test__audit.{t} "
                      "order by jev_p desc nulls last limit 20"))
```

The dbt `notebook` target in `profiles.yml` (Task 5) reads `DBT_DATABRICKS_TOKEN`. The token
string only exists in the subprocess environment.

- [ ] **Step 4: Deploy and run in demo mode** (standing OK: the notebook's queries go to the
2X-Small warehouse; serverless notebook compute is covered by the user's go-ahead for this
feature):

```bash
databricks bundle validate -p jev-demo-5
databricks bundle deploy -p jev-demo-5
databricks bundle run jev_semantic_tests -p jev-demo-5 --params mode=demo,selection=yardstick
```

Expected: run succeeds; the job output shows the `SIMULATED` summary and `once-per-row OK`. If
the dbt subprocess cannot authenticate with the run token, report it; do not switch to a PAT.

- [ ] **Step 5: Commit** — `git commit -m "feat(notebook): run dbt inside Databricks via a serverless notebook job (bundle)"`

---

### Task 12: Recording script and docs

**Files:**
- Create: `scripts/record.sh`, `README.md`, `CLAUDE.md`, `docs/eval-results.md`

- [ ] **Step 1: `docs/eval-results.md`** — header explaining the file (every scored live run,
newest last, same columns as demo 04 plus warehouse/budget/429s/est-ratio/DBUs), and a
"Reference: demo 04" block with the numbers from `eval/demo04_reference.json`. No runs yet.

- [ ] **Step 2: `CLAUDE.md`** — demo 04's rules adapted: commands (uv sync, pytest, ruff,
`eval "$(uv run python scripts/jev_env.py)"`, deploy, dbt build yardstick/production, score,
bundle), and rules: never read/print/log `.env`, secrets, tokens or the key; the key only in the
UC secret created by the user; SIMULATED never reported; golden key/pools/baselines never edited
to make Jev win; changing `fails_if`/`criteria`/`threshold` requires a fresh live scored run;
live runs, new warehouses, downloads, `system.billing`, dropping schemas are confirm-first;
2X-Small queries have a standing OK; the function body modules must stay embeddable (no
`from __future__`, no `$$`); `jev_question.sql` is the single place for question/state/key.

- [ ] **Step 3: `README.md`** — what it is (demo 04 → Databricks), architecture diagram (spec §6),
prerequisites (Premium workspace with UC; the serverless-networking preview; the secret
one-liner; `deploy.py --apply`), running (local dbt, notebook/bundle), the production run and
dataset citation (McAuley & Leskovec, WWW 2013; CC0 on Kaggle), results placeholder that points
to `docs/eval-results.md` (no numbers until live runs are logged), production notes (function
owner should be a service principal; no global pacer: 429 + backoff; residual task-retry gap).

- [ ] **Step 4: `scripts/record.sh`** — port demo 04's `record.sh` (typewriter, captions,
keypress between beats) with the beats from spec §14; a `--notebook` flag prints the bundle run
URL instead of running dbt locally. Smoke test in demo mode only:
`yes '' | JEV_MODE=demo TYPE_DELAY=0 scripts/record.sh` (needs the dev warehouse; standing OK).

- [ ] **Step 5: Commit** — `git commit -m "docs: README, CLAUDE.md, eval-results skeleton, recording script"`

---

## After the plan (needs the user)

1. User creates `jev_demo.jev.typesafe_api_key`; deploy `noul_pack` (`deploy.py --apply --only noul_pack`).
2. **Live yardstick run** (confirm-first): `uv run python scripts/score.py --run --fresh --append`.
3. **Production run** (confirm-first each): download → `deploy.py --production --apply` →
   `fetch_reviews.py --upload` → create `jev-demo-5-prod` → live build (95k) → audit labelling by
   the user → `--upload-part2` + rebuild (5k) → rerun (0 requests) → score + append.
4. Recording.
