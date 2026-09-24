# Jev Semantic dbt Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An extended jaffle_shop dbt project where four `jev_expect` generic tests, written as English sentences, catch structurally-valid-but-semantically-wrong rows via a TypeSafe Jev UDF, scored against a hidden answer key and a regex baseline, plus a scripted terminal recording.

**Architecture:** A dbt-duckdb plugin (`jevdbt.plugin`) registers two DuckDB Python UDFs on connection: `jev_noul(state, question)` (Arrow, batched) and `jev_stats()`. A generic test macro compiles to SQL that calls `jev_noul` over a JSON struct of the judged column + context columns. A Scorer (ported from `~/Projects/jev-demo-2/src/semsql/engine.py`) dedupes, caches in sqlite, packs rows, and paces requests. Seeds are generated deterministically from authored text pools; `score.py` compares stored failures to `eval/golden_defects.csv`.

**Tech Stack:** Python 3.13, uv, dbt-core 1.12.5, dbt-duckdb 1.11.0, duckdb 1.5.5, typesafe-sdk 0.7.1, pyarrow, numpy, python-dotenv, rich, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-24-jev-dbt-semantic-tests-design.md`

## Global Constraints

- Pins exactly: `dbt-core==1.12.5`, `dbt-duckdb==1.11.0`, `duckdb==1.5.5`, `typesafe-sdk==0.7.1`. Python `>=3.13`. Use the project venv (`uv run dbt ...`), never the global `dbt` (it is dbt Fusion and cannot load plugins).
- Never read, print, or log `.env` or `TYPESAFE_API_KEY`.
- dbt 1.12 generic-test syntax: custom args under `arguments:`, readable test names via `name:`.
- The CTE in `jev_expect` is `as materialized` (DuckDB otherwise evaluates the UDF twice per row).
- Simulated mode must always say `SIMULATED` in the summary line. Never report simulated numbers as real.
- Price constant: `$0.042` per million **input** tokens (output free) — source https://docs.typesafe.ai/models. Rate limit: 1,200 requests/min.
- Never edit seed data, pools, or the golden key to make Jev win. Baseline rules are written before live results and are not weakened afterwards.
- All dbt commands run from `jaffle_shop/` with `--profiles-dir .`.
- Commit after each task; messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `uv run pytest -q` and `uv run ruff check` green at the end of every task.

## File map

```
pyproject.toml                         T1
src/jevdbt/__init__.py                 T1
src/jevdbt/questions.py                T1  Question (Noul instructions + criteria), packing rewrite
src/jevdbt/stats.py                    T1  counters, snapshot, format_summary
src/jevdbt/cache.py                    T2  sqlite (model, question, state) -> float
src/jevdbt/backend.py                  T2  JevBackend, DemoBackend, make_backend
src/jevdbt/scorer.py                   T3  dedupe/cache/pack/concurrency/rpm
src/jevdbt/runtime.py                  T4  Settings from config+env, Runtime singleton
src/jevdbt/udf.py                      T4  register(con, runtime)
src/jevdbt/plugin.py                   T4  dbt-duckdb Plugin
scripts/pools/{customers,returns,reviews,tickets}.toml   T5
scripts/make_seeds.py                  T6
jaffle_shop/seeds/*.csv, eval/golden_defects.csv          T6 (generated, committed)
jaffle_shop/{dbt_project.yml,profiles.yml}                T7
jaffle_shop/macros/{jev_expect.sql,jev_summary.sql}       T7
jaffle_shop/models/staging/{stg_*.sql,schema.yml}         T7
jaffle_shop/tests/baseline/*.sql       T8
scripts/score.py, scripts/show_failures.py, docs/eval-results.md   T9
(live gate — controller only)          T10
scripts/record.sh, README.md, CLAUDE.md                    T11
tests/test_*.py                        each task
```

---

### Task 1: Scaffold, Question, Stats

**Files:**
- Create: `pyproject.toml`, `src/jevdbt/__init__.py`, `src/jevdbt/questions.py`, `src/jevdbt/stats.py`
- Test: `tests/test_questions.py`, `tests/test_stats.py`

**Interfaces:**
- Produces: `Question(instructions: str, criteria_true: str|None=None, criteria_false: str|None=None)` frozen dataclass; `Question.from_json(raw: str) -> Question`; `Question.key() -> str`; `Question.for_packed_row(row_id: str) -> Question`.
- Produces: `Stats()` with `add(*, judgments=0, sent=0, requests=0, input_tokens=0, errors=0, udf_seconds=0.0)`, `snapshot() -> StatsSnapshot`; `StatsSnapshot` fields `judgments, sent, requests, input_tokens, errors, udf_seconds` + properties `cached_fraction`, `cost_usd`; `format_summary(snap, *, simulated: bool, model: str, pack: int) -> str`; `PRICE_PER_MTOK_USD = 0.042`.

- [ ] **Step 1: Create `pyproject.toml` and sync**

```toml
[project]
name = "jevdbt"
version = "0.1.0"
description = "Semantic dbt tests backed by TypeSafe Jev (demo)"
requires-python = ">=3.13"
dependencies = [
    "dbt-core==1.12.5",
    "dbt-duckdb==1.11.0",
    "duckdb==1.5.5",
    "typesafe-sdk==0.7.1",
    "pyarrow>=21",
    "numpy>=2",
    "python-dotenv>=1.0",
    "rich>=14",
]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.12"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/jevdbt"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: runs dbt end to end"]

[tool.ruff]
line-length = 100
src = ["src", "scripts"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

`src/jevdbt/__init__.py`: `"""Semantic dbt tests backed by TypeSafe Jev."""`

Run: `uv python pin 3.13 && uv sync`
Expected: resolves and installs; `uv run python -c "import dbt.adapters.duckdb, typesafe_sdk"` exits 0. If `pyarrow>=21`/`numpy>=2` floors fail to resolve, loosen to the newest version that resolves and note it in the commit message.

- [ ] **Step 2: Write failing tests** — `tests/test_questions.py`

```python
import json

import pytest

from jevdbt.questions import Question


def test_from_json_instructions_only():
    q = Question.from_json(json.dumps({"instructions": "Contains PII"}))
    assert q == Question("Contains PII")


def test_from_json_with_criteria():
    raw = json.dumps({"instructions": "x", "criteria": {"true": "yes-case", "false": "no-case"}})
    q = Question.from_json(raw)
    assert (q.criteria_true, q.criteria_false) == ("yes-case", "no-case")


@pytest.mark.parametrize(
    "raw",
    ["[]", '{"criteria": {}}', '{"instructions": "  "}', '{"instructions": "x", "criteria": {"maybe": "y"}}'],
)
def test_from_json_rejects_bad_input(raw):
    with pytest.raises(ValueError):
        Question.from_json(raw)


def test_key_is_stable_and_distinguishes_criteria():
    assert Question("a").key() == Question("a").key()
    assert Question("a").key() != Question("a", "t").key()


def test_for_packed_row_prefixes_and_rewrites_column_refs():
    q = Question("The comment contradicts `reason_code`", criteria_true="unlike `reason_code`")
    packed = q.for_packed_row("r003")
    assert packed.instructions.startswith("Judge ONLY the record in `rows.r003`, ignoring all other rows. ")
    assert "`rows.r003.reason_code`" in packed.instructions
    assert packed.criteria_true == "unlike `rows.r003.reason_code`"
    assert packed.criteria_false is None
```

`tests/test_stats.py`

```python
from jevdbt.stats import Stats, StatsSnapshot, format_summary


def test_add_and_snapshot():
    s = Stats()
    s.add(judgments=10, sent=4, requests=1, input_tokens=1_000_000, udf_seconds=0.5)
    s.add(judgments=2, errors=1)
    snap = s.snapshot()
    assert (snap.judgments, snap.sent, snap.requests, snap.errors) == (12, 4, 1, 1)
    assert snap.cached_fraction == 1 - 4 / 12
    assert round(snap.cost_usd, 6) == 0.042


def _snap(**kw):
    base = dict(judgments=1312, sent=813, requests=164, input_tokens=95_000, errors=0, udf_seconds=7.94)
    base.update(kw)
    return StatsSnapshot(**base)


def test_format_summary_live():
    line = format_summary(_snap(), simulated=False, model="jev-latest", pack=8)
    assert line == (
        "Jev · 1,312 judgments · 38% cached · 164 requests · 7.9 s · $0.004 · LIVE jev-latest pack=8"
    )


def test_format_summary_simulated_with_errors_and_tiny_cost():
    line = format_summary(_snap(input_tokens=10, errors=3), simulated=True, model="demo", pack=1)
    assert "SIMULATED demo pack=1" in line
    assert "<$0.001" in line
    assert line.endswith(" · 3 errors")


def test_cached_fraction_zero_judgments():
    assert _snap(judgments=0, sent=0).cached_fraction == 0.0
```

- [ ] **Step 3: Run tests, expect FAIL** — `uv run pytest -q` → ImportError / ModuleNotFoundError.

- [ ] **Step 4: Implement** — `src/jevdbt/questions.py`

```python
"""A Noul judgment request, parsed from the JSON string the jev_expect macro emits."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_COLUMN_REF = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


def _rewrite(text: str | None, row_id: str) -> str | None:
    if text is None:
        return None
    return _COLUMN_REF.sub(lambda m: f"`rows.{row_id}.{m.group(1)}`", text)


@dataclass(frozen=True)
class Question:
    """A yes/no question: `instructions` plus optional descriptions of the yes and no outcomes."""

    instructions: str
    criteria_true: str | None = None
    criteria_false: str | None = None

    def __post_init__(self) -> None:
        if not self.instructions or not self.instructions.strip():
            raise ValueError("instructions must be non-empty")

    @classmethod
    def from_json(cls, raw: str) -> Question:
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("instructions"), str):
            raise ValueError(f"question must be a JSON object with string 'instructions': {raw!r}")
        criteria = data.get("criteria") or {}
        if not isinstance(criteria, dict) or set(criteria) - {"true", "false"}:
            raise ValueError(f"criteria must only have 'true'/'false' keys: {raw!r}")
        return cls(data["instructions"], criteria.get("true"), criteria.get("false"))

    def key(self) -> str:
        """Stable identity for caching."""
        return json.dumps([self.instructions, self.criteria_true, self.criteria_false])

    def for_packed_row(self, row_id: str) -> Question:
        """Scope this question to one record inside a packed `{"rows": {...}}` state."""
        prefix = f"Judge ONLY the record in `rows.{row_id}`, ignoring all other rows. "
        return Question(
            prefix + _rewrite(self.instructions, row_id),
            _rewrite(self.criteria_true, row_id),
            _rewrite(self.criteria_false, row_id),
        )
```

`src/jevdbt/stats.py`

```python
"""Thread-safe counters for one dbt invocation, and the one-line run summary."""

from __future__ import annotations

import threading
from dataclasses import dataclass

# https://docs.typesafe.ai/models — charged per input token; output tokens are free.
PRICE_PER_MTOK_USD = 0.042


@dataclass(frozen=True)
class StatsSnapshot:
    judgments: int  # non-null states resolved by jev_noul (incl. duplicates and cache hits)
    sent: int  # states actually sent to the backend
    requests: int
    input_tokens: int
    errors: int
    udf_seconds: float  # wall time spent inside jev_noul

    @property
    def cached_fraction(self) -> float:
        return 1 - self.sent / self.judgments if self.judgments else 0.0

    @property
    def cost_usd(self) -> float:
        return self.input_tokens * PRICE_PER_MTOK_USD / 1_000_000


class Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._c = dict(judgments=0, sent=0, requests=0, input_tokens=0, errors=0, udf_seconds=0.0)

    def add(self, **deltas: float) -> None:
        with self._lock:
            for name, delta in deltas.items():
                if name not in self._c:
                    raise KeyError(name)
                self._c[name] += delta

    def snapshot(self) -> StatsSnapshot:
        with self._lock:
            return StatsSnapshot(**self._c)


def _cost(usd: float) -> str:
    return "<$0.001" if usd < 0.001 else f"${usd:.3f}"


def format_summary(snap: StatsSnapshot, *, simulated: bool, model: str, pack: int) -> str:
    mode = "SIMULATED" if simulated else "LIVE"
    line = (
        f"Jev · {snap.judgments:,} judgments · {snap.cached_fraction:.0%} cached · "
        f"{snap.requests:,} requests · {snap.udf_seconds:.1f} s · {_cost(snap.cost_usd)} · "
        f"{mode} {model} pack={pack}"
    )
    if snap.errors:
        line += f" · {snap.errors} errors"
    return line
```

- [ ] **Step 5: Run** `uv run pytest -q && uv run ruff check` → all pass.
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: scaffold jevdbt with Question and Stats"` (+ Co-Authored-By trailer). Commit `uv.lock` and `.python-version`.

---

### Task 2: Cache and backends

**Files:**
- Create: `src/jevdbt/cache.py`, `src/jevdbt/backend.py`
- Test: `tests/test_cache.py`, `tests/test_backend.py`

**Interfaces:**
- Consumes: `Question` (T1).
- Produces: `Cache(path)`, `.get_many(model: str, question: Question, states: list[str]) -> dict[str, float]`, `.put_many(model, question, items: dict[str, float])`, `.close()`.
- Produces: `BatchResult(values: list[float|None], input_tokens: int)`; `Backend` protocol (`name: str`, `simulated: bool`, `last_error: str|None`, `async judge(states: list[str], question: Question) -> BatchResult`, `async aclose()`); `JevBackend(model="jev-latest", client=None)`; `DemoBackend(latency=0.0)`; `make_backend(mode: str, model: str) -> Backend` where mode ∈ {"live","demo"} (resolution of "auto" happens in T4).

States are JSON object strings (DuckDB `to_json(struct_pack(...))`). Backends `json.loads` them.

- [ ] **Step 1: Failing tests** — `tests/test_cache.py`

```python
from jevdbt.cache import Cache
from jevdbt.questions import Question


def test_roundtrip_and_isolation(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    q1, q2 = Question("a"), Question("b")
    c.put_many("m", q1, {'{"x":1}': 0.9, '{"x":2}': 0.1})
    assert c.get_many("m", q1, ['{"x":1}', '{"x":2}', '{"x":3}']) == {'{"x":1}': 0.9, '{"x":2}': 0.1}
    assert c.get_many("m", q2, ['{"x":1}']) == {}
    assert c.get_many("other", q1, ['{"x":1}']) == {}


def test_many_keys_over_sqlite_variable_limit(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    q = Question("a")
    items = {f'{{"i":{i}}}': i / 3000 for i in range(2500)}
    c.put_many("m", q, items)
    assert c.get_many("m", q, list(items)) == items
```

`tests/test_backend.py`

```python
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
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/test_cache.py tests/test_backend.py -q`.

- [ ] **Step 3: Implement** — `src/jevdbt/cache.py`

```python
"""Sqlite cache of (model, question, state) -> noul probability."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

from jevdbt.questions import Question

_CHUNK = 900  # stay under sqlite's bound-variable limit


def _digest(model: str, question: Question, state: str) -> str:
    return hashlib.sha256(f"{model}\x1f{question.key()}\x1f{state}".encode()).hexdigest()


class Cache:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._con.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value REAL NOT NULL)")
        self._con.commit()

    def get_many(self, model: str, question: Question, states: list[str]) -> dict[str, float]:
        keys = {_digest(model, question, s): s for s in states}
        out: dict[str, float] = {}
        key_list = list(keys)
        with self._lock:
            for i in range(0, len(key_list), _CHUNK):
                chunk = key_list[i : i + _CHUNK]
                marks = ",".join("?" * len(chunk))
                rows = self._con.execute(
                    f"SELECT key, value FROM cache WHERE key IN ({marks})", chunk
                ).fetchall()
                for key, value in rows:
                    out[keys[key]] = float(value)
        return out

    def put_many(self, model: str, question: Question, items: dict[str, float]) -> None:
        if not items:
            return
        rows = [(_digest(model, question, s), v) for s, v in items.items()]
        with self._lock:
            self._con.executemany(
                "INSERT INTO cache (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                rows,
            )
            self._con.commit()

    def close(self) -> None:
        with self._lock:
            self._con.close()
```

`src/jevdbt/backend.py`

```python
"""Judgment backends: TypeSafe Jev (live) and a deterministic offline stand-in (simulated)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from typesafe_sdk import AsyncTypeSafeClient, Noul, TypeSafeError

from jevdbt.questions import Question


@dataclass
class BatchResult:
    values: list[float | None]  # None marks a failed judgment
    input_tokens: int


class Backend(Protocol):
    name: str
    simulated: bool
    last_error: str | None

    async def judge(self, states: list[str], question: Question) -> BatchResult: ...

    async def aclose(self) -> None: ...


def _to_noul(q: Question) -> Noul:
    criteria = None
    if q.criteria_true is not None or q.criteria_false is not None:
        criteria = {"true": q.criteria_true, "false": q.criteria_false}
    return Noul(instructions=q.instructions, criteria=criteria)


class JevBackend:
    def __init__(self, model: str = "jev-latest", client: Any = None) -> None:
        self.name = model
        self.simulated = False
        self.last_error: str | None = None
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = AsyncTypeSafeClient(model=self.name)
        return self._client

    async def judge(self, states: list[str], question: Question) -> BatchResult:
        client = self._ensure_client()
        try:
            if len(states) == 1:
                resp = await client.system_one(json.loads(states[0]), {"q": _to_noul(question)})
                values: list[float | None] = [resp.answers["q"].noul]
            else:
                ids = [f"r{i:03d}" for i in range(len(states))]
                state = {"rows": {rid: json.loads(s) for rid, s in zip(ids, states, strict=True)}}
                questions = {rid: _to_noul(question.for_packed_row(rid)) for rid in ids}
                resp = await client.system_one(state, questions)
                values = [resp.answers[rid].noul for rid in ids]
            return BatchResult(values, resp.usage.input_tokens)
        except (TypeSafeError, KeyError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return BatchResult([None] * len(states), 0)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


def _hash_unit(*parts: str) -> float:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class DemoBackend:
    """Offline stand-in. Values are a hash, not a judgment: most rows low, a few percent high."""

    def __init__(self, latency: float = 0.0) -> None:
        self.name = "demo"
        self.simulated = True
        self.last_error: str | None = None
        self._latency = latency

    async def judge(self, states: list[str], question: Question) -> BatchResult:
        if self._latency:
            await asyncio.sleep(self._latency)
        values: list[float | None] = [_hash_unit(question.key(), s) ** 6 for s in states]
        tokens = sum(len(s) // 4 + 40 for s in states)
        return BatchResult(values, tokens)

    async def aclose(self) -> None:
        return None


def make_backend(mode: str, model: str) -> Backend:
    if mode == "demo":
        return DemoBackend()
    if mode == "live":
        return JevBackend(model=model)
    raise ValueError(f"mode must be 'live' or 'demo', got {mode!r}")
```

- [ ] **Step 4: Run** `uv run pytest -q && uv run ruff check` → pass. If `test_demo_is_deterministic...` fails only on the `0 < … < 50` bound, check the exponent math (P(u^6 ≥ 0.8) ≈ 3.7%, ~18 of 500) before changing anything.
- [ ] **Step 5: Commit** `feat: sqlite cache and Jev/demo backends`.

---

### Task 3: Scorer

**Files:**
- Create: `src/jevdbt/scorer.py`
- Test: `tests/test_scorer.py`

**Interfaces:**
- Consumes: `Backend`, `BatchResult` (T2), `Cache` (T2), `Question`, `Stats` (T1).
- Produces: `Scorer(backend, stats, cache=None, *, pack=1, concurrency=32, rpm=1200)`; `score_many(states: list[str|None], question: Question) -> list[float|None]` (sync, thread-safe, order-preserving); `close()`.
- Stats contract: every call adds `judgments = count of non-null states`, `sent = distinct states sent to backend`, `requests`, `input_tokens`, `errors` (one per chunk with any None).

- [ ] **Step 1: Failing tests** — `tests/test_scorer.py`

```python
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
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** — `src/jevdbt/scorer.py` (port of `~/Projects/jev-demo-2/src/semsql/engine.py`, renamed texts→states, new stats contract)

```python
"""Scorer: states + Question -> probabilities via cache and backend, on a background loop."""

from __future__ import annotations

import asyncio
import threading
import time

from jevdbt.backend import Backend, BatchResult
from jevdbt.cache import Cache
from jevdbt.questions import Question
from jevdbt.stats import Stats


class _RpmPacer:
    """Spaces request starts to at most `rpm` per minute. `rpm <= 0` disables pacing."""

    def __init__(self, rpm: int) -> None:
        self._interval = 60.0 / rpm if rpm > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        if not self._interval:
            return
        async with self._lock:
            now = time.monotonic()
            if now < self._next:
                await asyncio.sleep(self._next - now)
                now = time.monotonic()
            self._next = max(now, self._next) + self._interval


class Scorer:
    """Owns an asyncio loop thread; `score_many` is a synchronous, thread-safe facade."""

    def __init__(
        self,
        backend: Backend,
        stats: Stats,
        cache: Cache | None = None,
        *,
        pack: int = 1,
        concurrency: int = 32,
        rpm: int = 1200,
    ) -> None:
        self.backend = backend
        self.stats = stats
        self.cache = cache
        self.pack = max(1, pack)
        self._concurrency = concurrency
        self._rpm = rpm
        self._closed = False
        self._close_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait()

    def _run_loop(self, ready: threading.Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._pacer = _RpmPacer(self._rpm)
        ready.set()
        loop.run_forever()

    def score_many(self, states: list[str | None], question: Question) -> list[float | None]:
        out: list[float | None] = [None] * len(states)
        positions: dict[str, list[int]] = {}
        for i, s in enumerate(states):
            if s is not None:
                positions.setdefault(s, []).append(i)
        if not positions:
            return out
        judgments = sum(len(v) for v in positions.values())

        resolved: dict[str, float | None] = {}
        if self.cache is not None:
            resolved.update(self.cache.get_many(self.backend.name, question, list(positions)))
        missing = [s for s in positions if s not in resolved]
        if missing:
            chunks = [missing[i : i + self.pack] for i in range(0, len(missing), self.pack)]
            assert self._loop is not None
            future = asyncio.run_coroutine_threadsafe(self._run(chunks, question), self._loop)
            to_cache: dict[str, float] = {}
            for chunk, result in zip(chunks, future.result(), strict=True):
                for s, v in zip(chunk, result.values, strict=True):
                    resolved[s] = v
                    if v is not None:
                        to_cache[s] = v
            if self.cache is not None:
                self.cache.put_many(self.backend.name, question, to_cache)
        self.stats.add(judgments=judgments, sent=len(missing))

        for s, idxs in positions.items():
            for i in idxs:
                out[i] = resolved.get(s)
        return out

    async def _run(self, chunks: list[list[str]], question: Question) -> list[BatchResult]:
        return await asyncio.gather(*(self._one(c, question) for c in chunks))

    async def _one(self, chunk: list[str], question: Question) -> BatchResult:
        async with self._semaphore:
            await self._pacer.wait()
            result = await self.backend.judge(chunk, question)
        self.stats.add(requests=1, input_tokens=result.input_tokens)
        if any(v is None for v in result.values):
            self.stats.add(errors=1)
        return result

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(self.backend.aclose(), self._loop)
        try:
            future.result(timeout=10)
        except Exception:  # noqa: BLE001 -- best-effort shutdown
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)
```

- [ ] **Step 4: Run** `uv run pytest -q && uv run ruff check` → pass.
- [ ] **Step 5: Commit** `feat: scorer with dedupe, cache, packing and rpm pacing`.

---

### Task 4: Runtime, UDFs, dbt-duckdb plugin

**Files:**
- Create: `src/jevdbt/runtime.py`, `src/jevdbt/udf.py`, `src/jevdbt/plugin.py`
- Test: `tests/test_runtime.py`, `tests/test_udf.py`

**Interfaces:**
- Consumes: everything from T1–T3.
- Produces: `Settings` frozen dataclass (`mode: "live"|"demo"`, `model: str`, `pack: int`, `concurrency: int`, `rpm: int`, `cache_path: str|None`); `resolve_settings(config: Mapping, env: Mapping) -> Settings`; `Runtime(scorer, stats, settings)` with `.simulated: bool`, `.summary() -> str`, `.stats_json() -> str`; `build_runtime(settings) -> Runtime`; `get_runtime(config: Mapping) -> Runtime` (process singleton, loads `.env` unless `DOTENV_DISABLE=1`); `register(con, runtime)` registering `jev_noul(VARCHAR, VARCHAR) -> DOUBLE` and `jev_stats() -> VARCHAR`; `jevdbt.plugin.Plugin`.
- `jev_stats()` JSON keys: `judgments, sent, requests, input_tokens, errors, udf_seconds, simulated, model, pack, summary`.

Settings precedence: env `JEV_MODE`, `JEV_PACK`, `JEV_CACHE` (path), `JEV_NO_CACHE=1` override profile `config` keys `mode`, `pack`, `concurrency`, `rpm`, `model`, `cache_path`. Defaults: mode `auto`, pack 1, concurrency 32, rpm 1200, model `jev-latest`, cache `.jev_cache.sqlite`. `auto` → `live` if `TYPESAFE_API_KEY` is set and non-empty, else `demo`. `live` without the key → `RuntimeError("JEV_MODE=live but TYPESAFE_API_KEY is not set")`. Invalid mode → `ValueError`.

- [ ] **Step 1: Failing tests** — `tests/test_runtime.py`

```python
import json

import pytest

from jevdbt.runtime import Settings, build_runtime, resolve_settings


def test_defaults_auto_without_key_is_demo():
    s = resolve_settings({}, {})
    assert s == Settings(mode="demo", model="jev-latest", pack=1, concurrency=32, rpm=1200,
                         cache_path=".jev_cache.sqlite")


def test_auto_with_key_is_live():
    assert resolve_settings({}, {"TYPESAFE_API_KEY": "k"}).mode == "live"


def test_env_overrides_config():
    s = resolve_settings(
        {"mode": "live", "pack": 4, "cache_path": "a.sqlite"},
        {"JEV_MODE": "demo", "JEV_PACK": "8", "JEV_NO_CACHE": "1"},
    )
    assert (s.mode, s.pack, s.cache_path) == ("demo", 8, None)


def test_live_without_key_raises():
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        resolve_settings({"mode": "live"}, {})


def test_bad_mode_raises():
    with pytest.raises(ValueError):
        resolve_settings({"mode": "maybe"}, {})


def test_runtime_stats_json(tmp_path):
    rt = build_runtime(Settings("demo", "jev-latest", 1, 4, 0, str(tmp_path / "c.sqlite")))
    data = json.loads(rt.stats_json())
    assert data["judgments"] == 0 and data["simulated"] is True
    assert data["summary"].startswith("Jev · 0 judgments") and "SIMULATED demo pack=1" in data["summary"]
    rt.scorer.close()
```

(`model` shows as `demo` in simulated summaries: `Runtime.summary()` passes `backend.name`.)

`tests/test_udf.py`

```python
import json

import duckdb

from jevdbt.runtime import Settings, build_runtime
from jevdbt.udf import register


def make_con(tmp_path):
    rt = build_runtime(Settings("demo", "jev-latest", 1, 4, 0, None))
    con = duckdb.connect()
    register(con, rt)
    return con, rt


def test_jev_noul_over_json_struct_groups_questions(tmp_path):
    con, rt = make_con(tmp_path)
    con.execute("create table t as select * from (values (1,'a','x'),(2,'b','y'),(3,null,'z')) v(id,c,d)")
    q1 = json.dumps({"instructions": "Q1 about `d`"})
    q2 = json.dumps({"instructions": "Q2", "criteria": {"true": "it's yes", "false": "no"}})
    rows = con.execute(
        f"""select id,
                   jev_noul(case when c is null then null else to_json(struct_pack(c := c, d := d)) end, '{q1}'),
                   jev_noul(to_json(struct_pack(c := c, d := d)), '{q2.replace("'", "''")}')
            from t order by id"""
    ).fetchall()
    assert rows[2][1] is None
    assert all(0.0 <= r[1] <= 1.0 for r in rows[:2])
    assert all(0.0 <= r[2] <= 1.0 for r in rows)
    assert rt.stats.snapshot().judgments == 5
    rt.scorer.close()


def test_materialized_cte_evaluates_once(tmp_path):
    con, rt = make_con(tmp_path)
    con.execute("create table t as select range as id, 'txt' || range as c from range(300)")
    q = json.dumps({"instructions": "Q"})
    con.execute(
        f"""with judged as materialized (
              select *, jev_noul(to_json(struct_pack(c := c)), '{q}') as jev_p from t)
            select * from judged where jev_p >= 0.5"""
    ).fetchall()
    assert rt.stats.snapshot().judgments == 300
    rt.scorer.close()


def test_jev_stats_returns_json(tmp_path):
    con, rt = make_con(tmp_path)
    data = json.loads(con.execute("select jev_stats()").fetchone()[0])
    assert data["simulated"] is True and "summary" in data
    rt.scorer.close()


def test_bad_question_raises_clear_error(tmp_path):
    con, rt = make_con(tmp_path)
    try:
        con.execute("select jev_noul('{}', 'not json')").fetchall()
        raise AssertionError("expected an error")
    except duckdb.Error as exc:
        assert "jev_noul" in str(exc)
    rt.scorer.close()
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** — `src/jevdbt/runtime.py`

```python
"""Settings resolution and the per-process Runtime (scorer + stats) shared by all connections."""

from __future__ import annotations

import atexit
import json
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jevdbt.backend import make_backend
from jevdbt.cache import Cache
from jevdbt.scorer import Scorer
from jevdbt.stats import Stats, format_summary

_MODES = {"auto", "live", "demo"}


@dataclass(frozen=True)
class Settings:
    mode: str  # resolved: "live" | "demo"
    model: str
    pack: int
    concurrency: int
    rpm: int
    cache_path: str | None


def resolve_settings(config: Mapping[str, Any], env: Mapping[str, str]) -> Settings:
    mode = (env.get("JEV_MODE") or str(config.get("mode", "auto"))).lower()
    if mode not in _MODES:
        raise ValueError(f"jevdbt mode must be one of {sorted(_MODES)}, got {mode!r}")
    has_key = bool(env.get("TYPESAFE_API_KEY"))
    if mode == "auto":
        mode = "live" if has_key else "demo"
    if mode == "live" and not has_key:
        raise RuntimeError("JEV_MODE=live but TYPESAFE_API_KEY is not set")
    cache_path: str | None = env.get("JEV_CACHE") or str(config.get("cache_path", ".jev_cache.sqlite"))
    if env.get("JEV_NO_CACHE") == "1":
        cache_path = None
    return Settings(
        mode=mode,
        model=str(config.get("model", "jev-latest")),
        pack=int(env.get("JEV_PACK") or config.get("pack", 1)),
        concurrency=int(config.get("concurrency", 32)),
        rpm=int(config.get("rpm", 1200)),
        cache_path=cache_path,
    )


class Runtime:
    def __init__(self, scorer: Scorer, stats: Stats, settings: Settings) -> None:
        self.scorer = scorer
        self.stats = stats
        self.settings = settings

    @property
    def simulated(self) -> bool:
        return self.scorer.backend.simulated

    def summary(self) -> str:
        return format_summary(
            self.stats.snapshot(),
            simulated=self.simulated,
            model=self.scorer.backend.name,
            pack=self.settings.pack,
        )

    def stats_json(self) -> str:
        snap = self.stats.snapshot()
        return json.dumps(
            {
                **snap.__dict__,
                "simulated": self.simulated,
                "model": self.scorer.backend.name,
                "pack": self.settings.pack,
                "summary": self.summary(),
            }
        )


def build_runtime(settings: Settings) -> Runtime:
    stats = Stats()
    cache = Cache(settings.cache_path) if settings.cache_path else None
    backend = make_backend(settings.mode, settings.model)
    scorer = Scorer(
        backend, stats, cache, pack=settings.pack, concurrency=settings.concurrency, rpm=settings.rpm
    )
    return Runtime(scorer, stats, settings)


_runtime: Runtime | None = None
_runtime_lock = threading.Lock()


def get_runtime(config: Mapping[str, Any]) -> Runtime:
    """One Runtime per process: dbt opens a connection per thread; they share stats and cache."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            if os.environ.get("DOTENV_DISABLE") != "1":
                from dotenv import find_dotenv, load_dotenv

                load_dotenv(find_dotenv(usecwd=True))
            _runtime = build_runtime(resolve_settings(config, os.environ))
            atexit.register(_runtime.scorer.close)
        return _runtime
```

`src/jevdbt/udf.py`

```python
"""DuckDB UDFs: jev_noul(state, question) -> probability, jev_stats() -> JSON."""

from __future__ import annotations

import time

import duckdb
import pyarrow as pa
from duckdb.func import PythonUDFType

from jevdbt.questions import Question
from jevdbt.runtime import Runtime


def register(con: duckdb.DuckDBPyConnection, runtime: Runtime) -> None:
    def jev_noul(state_col: pa.Array, question_col: pa.Array) -> pa.Array:
        started = time.perf_counter()
        states = state_col.to_pylist()
        raw_questions = question_col.to_pylist()
        out: list[float | None] = [None] * len(states)
        groups: dict[str, list[int]] = {}
        for i, (s, q) in enumerate(zip(states, raw_questions, strict=True)):
            if s is not None and q is not None:
                groups.setdefault(q, []).append(i)
        for raw, idxs in groups.items():
            try:
                question = Question.from_json(raw)
            except ValueError as exc:
                raise duckdb.InvalidInputException(f"jev_noul: bad question: {exc}") from exc
            values = runtime.scorer.score_many([states[i] for i in idxs], question)
            for i, v in zip(idxs, values, strict=True):
                out[i] = v
        runtime.stats.add(udf_seconds=time.perf_counter() - started)
        return pa.array(out, type=pa.float64())

    con.create_function(
        "jev_noul", jev_noul, ["VARCHAR", "VARCHAR"], "DOUBLE", type=PythonUDFType.ARROW
    )
    con.create_function("jev_stats", runtime.stats_json, [], "VARCHAR", side_effects=True)
```

Note: `json.JSONDecodeError` is a `ValueError` subclass, so `'not json'` is covered. If DuckDB's `create_function` rejects a bound method for `jev_stats`, wrap it: `lambda: runtime.stats_json()`.

`src/jevdbt/plugin.py`

```python
"""dbt-duckdb plugin: `plugins: [{module: jevdbt.plugin, config: {...}}]` in profiles.yml."""

from __future__ import annotations

from typing import Any

from dbt.adapters.duckdb.plugins import BasePlugin

from jevdbt.runtime import get_runtime
from jevdbt.udf import register


class Plugin(BasePlugin):
    def initialize(self, plugin_config: dict[str, Any]) -> None:
        self._config = dict(plugin_config)

    def configure_connection(self, conn: Any) -> None:
        register(conn, get_runtime(self._config))
```

- [ ] **Step 4: Run** `uv run pytest -q && uv run ruff check` → pass.
- [ ] **Step 5: Commit** `feat: runtime settings, DuckDB UDFs and dbt-duckdb plugin`.

---

### Task 5: Text pools (content authoring)

**Files:**
- Create: `scripts/pools/customers.toml`, `scripts/pools/returns.toml`, `scripts/pools/reviews.toml`, `scripts/pools/tickets.toml`
- Test: `tests/test_pools.py`

**Interfaces:**
- Produces the TOML schemas below, consumed by T6. Every `defect` and `hard_negative` entry has a `note` explaining the label in ≤ 15 words.

This task is writing, not code. Independent of T1–T4; can run in parallel with them.

Slots available to texts (filled by T6; use them freely, `{product}` especially): `{product}`, `{minutes}` (35–150), `{day}` (weekday), `{first_name}`, `{order_no}` (e.g. `#10482`), `{store_address}` (the shop's own address), and for PII only: `{street}`, `{house_no}`, `{postcode}`, `{city}`, `{phone}`, `{iban}`, `{personal_email}`.

Schemas and **exact** counts (T6 uses every defect/hard_negative exactly once, so counts here = counts in the data):

```toml
# customers.toml
first_names = ["Sanne", "Daan", ...]     # >= 120, international mix (NL, TR, MA, CN, IN, PL, ES, NG, US...)
last_names  = ["de Vries", "Yilmaz", ...] # >= 120, same mix, incl. tussenvoegsels
[[junk]]            # exactly 25: placeholders, keyboard mash, company names, emails pasted as names,
first_name = "test" # phone numbers as names, "N/A", "Mickey Mouse"-style fakes, "asdf asdf"
last_name = "test"
note = "placeholder test record"
[[hard_negative]]   # exactly 25: real people a regex would flag: surname Test / Bar / Foo(t), single
first_name = "Anna" # letters or very short (Bo Li), mononyms with empty last_name, O'Neill-Ødegaard,
last_name = "Test"  # "Xi Xi", names containing "Co"/"Inc"-like tokens (Inca, Coco), no-vowel (Nguyễn? no — "Mbw")
note = "Test is a real Dutch/English surname"
```

```toml
# returns.toml
[[clean]]           # >= 110, spread over damaged/wrong_item/late/changed_mind/other (other >= 10)
code = "late"
text = "Took {minutes} minutes, the {product} was stone cold by then."
[[defect]]          # exactly 12: comment clearly describes a DIFFERENT code than `code`
code = "changed_mind"
text = "The {product} arrived burnt black on one side."
note = "really damaged, coded changed_mind"
[[hard_negative]]   # exactly 20: consistent with `code` but contains keywords of another code
code = "late"
text = "Honestly I'd changed my mind by the time it showed up {minutes} min late."
note = "mentions changed mind, but lateness is the reason"
```

```toml
# reviews.toml
[[clean]]           # >= 180, stars 1..5 all represented, sentiment matches stars
stars = 5
text = "Best {product} in town, still warm on arrival."
[[defect]]          # exactly 24: sentiment clearly contradicts stars (half 4-5★ negative, half 1-2★ glowing)
stars = 5
text = "Never ordering again, the {product} was raw inside."
note = "furious text, 5 stars"
[[hard_negative]]   # exactly 30: sarcasm/irony matching a LOW rating, mixed 3★, negations ("not bad at all" 4★)
stars = 1
text = "Great, cold again. Love that for me."
note = "sarcastic praise, correctly 1 star"
```

```toml
# tickets.toml
[[clean]]           # >= 110: order issues, allergens, opening hours, refunds — no personal data
subject = "Missing drink"
text = "Order {order_no} came without the iced coffee."
[[defect]]          # exactly 14: personal data in prose — home address, phone, IBAN, personal email,
subject = "Refund"  # date of birth + full name; vary formats (spaced IBAN, "zero six", "at gmail dot com")
text = "Please refund to {iban}, I'm {first_name} and live at {street} {house_no}, {city}."
note = "IBAN and home address"
[[hard_negative]]   # exactly 25: order numbers, the store's own address, first name only, a
subject = "Pickup"  # public phone of the shop, a postcode used for delivery-area questions only
text = "Can I pick up {order_no} at {store_address} instead?"
note = "store address, not personal"
```

Quality bar (the writer self-audits every entry before finishing):
- Every `defect` is unambiguous to a careful human reader. Every `hard_negative` is clearly clean to a careful human reader AND would trip a naive keyword/regex rule. Every `clean` is clean.
- Varied voice: terse, rambling, typos, lowercase, emoji (sparingly), non-native English. Lengths 4–60 words.
- No real brands, no real people, no real IBANs (T6 generates fake PII values).
- English only.

- [ ] **Step 1: Write `tests/test_pools.py`** (fails until pools exist)

```python
import re
import tomllib
from pathlib import Path

import pytest

POOLS = Path(__file__).parents[1] / "scripts" / "pools"
SLOTS = {"product", "minutes", "day", "first_name", "order_no", "store_address",
         "street", "house_no", "postcode", "city", "phone", "iban", "personal_email"}
PII_SLOTS = {"street", "house_no", "postcode", "city", "phone", "iban", "personal_email"}
CODES = {"damaged", "wrong_item", "late", "changed_mind", "other"}


def load(name):
    return tomllib.loads((POOLS / f"{name}.toml").read_text())


def slots(text):
    return set(re.findall(r"\{(\w+)\}", text))


def test_customers():
    p = load("customers")
    assert len(p["first_names"]) >= 120 and len(p["last_names"]) >= 120
    assert len(p["junk"]) == 25 and len(p["hard_negative"]) == 25
    assert all(e["note"] for e in p["junk"] + p["hard_negative"])


@pytest.mark.parametrize("name,defects,hard,clean_min", [
    ("returns", 12, 20, 110), ("reviews", 24, 30, 180), ("tickets", 14, 25, 110)])
def test_counts_and_slots(name, defects, hard, clean_min):
    p = load(name)
    assert len(p["defect"]) == defects and len(p["hard_negative"]) == hard
    assert len(p["clean"]) >= clean_min
    for group in ("clean", "defect", "hard_negative"):
        for e in p[group]:
            assert slots(e["text"]) <= SLOTS, e
            if group != "clean":
                assert e["note"], e
            if name != "tickets" or group != "defect":
                assert not (slots(e["text"]) & PII_SLOTS), e
    texts = [e["text"] for g in ("clean", "defect", "hard_negative") for e in p[g]]
    assert len(texts) == len(set(texts)), "duplicate texts"


def test_returns_codes():
    p = load("returns")
    assert {e["code"] for e in p["clean"]} == CODES
    assert all(e["code"] in CODES for g in ("defect", "hard_negative") for e in p[g])


def test_reviews_stars():
    p = load("reviews")
    assert {e["stars"] for e in p["clean"]} == {1, 2, 3, 4, 5}


def test_tickets_defects_all_carry_pii_slots_or_literal_pii():
    for e in load("tickets")["defect"]:
        assert slots(e["text"]) & PII_SLOTS or "@" in e["text"] or any(c.isdigit() for c in e["text"]), e
```

- [ ] **Step 2: Write the four pools** to the schemas and counts above. Do the self-audit pass as a separate read-through of each file.
- [ ] **Step 3: Run** `uv run pytest tests/test_pools.py -q` → pass (requires T1's `pyproject.toml`; if run before T1, use `python3 -m pytest tests/test_pools.py -q`).
- [ ] **Step 4: Commit** `feat: authored text pools with defects and hard negatives`.

---

### Task 6: Seed + golden key generator

**Files:**
- Create: `scripts/make_seeds.py`; generated `jaffle_shop/seeds/raw_{customers,orders,returns,reviews,tickets}.csv`, `eval/golden_defects.csv`
- Test: `tests/test_make_seeds.py`

**Interfaces:**
- Consumes: pools (T5).
- Produces: `generate(seed: int = 42, pools_dir: Path = POOLS) -> dict[str, list[dict]]` returning keys `raw_customers, raw_orders, raw_returns, raw_reviews, raw_tickets, golden`; `write(tables, seeds_dir, golden_path)`; CLI `uv run python scripts/make_seeds.py` writes files.
- Columns (these are contracts for T7/T9):
  - `raw_customers`: `id, first_name, last_name, email` — 500 rows
  - `raw_orders`: `id, user_id, order_date, status` — 1,500 rows; status ∈ `placed, shipped, completed, return_pending, returned`; exactly 200 `returned`
  - `raw_returns`: `id, order_id, reason_code, comment` — 200 rows, one per returned order
  - `raw_reviews`: `id, order_id, stars, body` — 400 rows, distinct `completed` or `returned` orders
  - `raw_tickets`: `id, customer_id, subject, body` — 200 rows
  - `golden`: `test_name, id, label, note` with test names `customers_full_name_is_a_person`, `returns_comment_matches_reason_code`, `reviews_body_matches_stars`, `tickets_body_has_no_pii`; label ∈ `defect, hard_negative`.

Rules:
- `rng = random.Random(seed)`. All choices go through `rng`. Output CSVs byte-identical across runs.
- Each table: take every `defect` and `hard_negative` entry once, fill the remainder with `rng.choice(clean)`, `rng.shuffle` the list, then assign ids `1..N` in shuffled order; golden rows record the resulting ids.
- Customers: clean rows = `rng.choice(first_names)` + `rng.choice(last_names)`; email = ascii-folded `first.last` (spaces→`.`, drop non `[a-z0-9.]`) + `{id}@example.com`; for junk/hard-negative rows use the same email rule from their own names (fall back to `customer{id}@example.com` if empty). Empty `last_name` stays empty (CSV empty → NULL).
- Slots: `{product}` from `["cheese & tomato jaffle", "ham & cheese jaffle", "banana nutella jaffle", "vegan chili jaffle", "apple cinnamon jaffle", "iced coffee", "flat white", "lemonade"]`; `{minutes}` 35–150; `{day}` weekday name; `{first_name}` from pool; `{order_no}` `#` + 5 digits; `{store_address}` `"Jaffle Shop, Oudegracht 118, Utrecht"`; `{street}` from `["Kerkstraat", "Dorpsweg", "Lindenlaan", "Prinsengracht", "Molenweg", "Stationsplein"]`; `{house_no}` 1–220 (+ optional letter); `{postcode}` 4 digits + space + 2 uppercase letters; `{city}` from 6 Dutch cities; `{phone}` `06-` + 8 digits in one of 3 formats (`06-12345678`, `06 1234 5678`, `+31 6 12345678`); `{iban}` `NL` + 2 digits + one of `ABNA, INGB, RABO, TRIO` + 10 digits, grouped by 4 with spaces half the time; `{personal_email}` first name + surname-ish + `@gmail.com|@outlook.com|@hotmail.nl`.
- Orders: `user_id` uniform over customers; `order_date` uniform 2026-01-01..2026-08-31; choose 200 order ids for `returned`, remainder weighted `placed 5%, shipped 10%, completed 80%, return_pending 5%`.
- Returns: `order_id` = the 200 returned orders in shuffled order. Reviews: 400 distinct orders sampled from completed ∪ returned. Tickets: `customer_id` uniform.

- [ ] **Step 1: Failing tests** — `tests/test_make_seeds.py`

```python
import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("make_seeds", ROOT / "scripts" / "make_seeds.py")
make_seeds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_seeds)


def test_deterministic_and_written_files_match(tmp_path):
    a, b = make_seeds.generate(42), make_seeds.generate(42)
    assert a == b
    make_seeds.write(a, tmp_path / "seeds", tmp_path / "golden.csv")
    make_seeds.write(b, tmp_path / "seeds2", tmp_path / "golden2.csv")
    for f in (tmp_path / "seeds").iterdir():
        assert f.read_bytes() == (tmp_path / "seeds2" / f.name).read_bytes()


def test_shapes_and_structural_validity():
    t = make_seeds.generate(42)
    assert [len(t[k]) for k in ("raw_customers", "raw_orders", "raw_returns", "raw_reviews", "raw_tickets")] == [500, 1500, 200, 400, 200]
    cust = {r["id"] for r in t["raw_customers"]}
    orders = {r["id"]: r for r in t["raw_orders"]}
    assert all(r["user_id"] in cust for r in t["raw_orders"])
    assert sum(r["status"] == "returned" for r in orders.values()) == 200
    assert all(orders[r["order_id"]]["status"] == "returned" for r in t["raw_returns"])
    assert len({r["order_id"] for r in t["raw_returns"]}) == 200
    assert len({r["order_id"] for r in t["raw_reviews"]}) == 400
    assert all(orders[r["order_id"]]["status"] in {"completed", "returned"} for r in t["raw_reviews"])
    assert all(r["customer_id"] in cust for r in t["raw_tickets"])
    assert {r["reason_code"] for r in t["raw_returns"]} <= {"damaged", "wrong_item", "late", "changed_mind", "other"}
    assert {r["stars"] for r in t["raw_reviews"]} <= {1, 2, 3, 4, 5}
    for name in ("raw_returns", "raw_reviews", "raw_tickets"):
        for r in t[name]:
            text = r.get("comment") or r.get("body")
            assert text and "{" not in text, r


def test_golden_counts_and_ids_exist():
    t = make_seeds.generate(42)
    ids = {
        "customers_full_name_is_a_person": {r["id"] for r in t["raw_customers"]},
        "returns_comment_matches_reason_code": {r["id"] for r in t["raw_returns"]},
        "reviews_body_matches_stars": {r["id"] for r in t["raw_reviews"]},
        "tickets_body_has_no_pii": {r["id"] for r in t["raw_tickets"]},
    }
    counts = {}
    for g in t["golden"]:
        assert g["id"] in ids[g["test_name"]]
        counts[(g["test_name"], g["label"])] = counts.get((g["test_name"], g["label"]), 0) + 1
    assert counts == {
        ("customers_full_name_is_a_person", "defect"): 25, ("customers_full_name_is_a_person", "hard_negative"): 25,
        ("returns_comment_matches_reason_code", "defect"): 12, ("returns_comment_matches_reason_code", "hard_negative"): 20,
        ("reviews_body_matches_stars", "defect"): 24, ("reviews_body_matches_stars", "hard_negative"): 30,
        ("tickets_body_has_no_pii", "defect"): 14, ("tickets_body_has_no_pii", "hard_negative"): 25,
    }


def test_committed_files_are_current():
    seeds = ROOT / "jaffle_shop" / "seeds"
    with (seeds / "raw_returns.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 200
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `scripts/make_seeds.py`** per the rules above. Structure: `load_pools(dir)`, `Filler(rng)` with one method per slot and `fill(text) -> str` using `re.sub(r"\{(\w+)\}", ...)`, `_labelled(pool, n, rng)` returning `[(entry, label)]` of length n (label `clean|defect|hard_negative`) shuffled, `generate(seed, pools_dir)`, `write(tables, seeds_dir, golden_path)` using `csv.DictWriter` with `lineterminator="\n"`, and `main()` writing to `jaffle_shop/seeds/` and `eval/golden_defects.csv`. Keep ints as ints in the returned dicts.
- [ ] **Step 4: Generate** `uv run python scripts/make_seeds.py`, then `uv run pytest -q && uv run ruff check` → pass.
- [ ] **Step 5: Commit** `feat: deterministic seed and golden-key generator` (include generated CSVs).

---

### Task 7: dbt project, `jev_expect`, summary hook, semantic tests

**Files:**
- Create: `jaffle_shop/dbt_project.yml`, `jaffle_shop/profiles.yml`, `jaffle_shop/macros/jev_expect.sql`, `jaffle_shop/macros/jev_summary.sql`, `jaffle_shop/models/staging/stg_customers.sql`, `stg_orders.sql`, `stg_returns.sql`, `stg_reviews.sql`, `stg_tickets.sql`, `jaffle_shop/models/staging/schema.yml`
- Test: `tests/test_dbt_project.py` (marked `slow`)

**Interfaces:**
- Consumes: plugin (T4), seeds (T6).
- Produces: models `stg_customers(customer_id, first_name, last_name, full_name, email)`, `stg_orders(order_id, customer_id, order_date, status)`, `stg_returns(return_id, order_id, reason_code, comment)`, `stg_reviews(review_id, order_id, stars, body)`, `stg_tickets(ticket_id, customer_id, subject, body)`; four semantic tests with store_failures tables in schema `main_dbt_test__audit` named exactly `customers_full_name_is_a_person`, `returns_comment_matches_reason_code`, `reviews_body_matches_stars`, `tickets_body_has_no_pii`, each carrying the model's columns + `jev_p`; tag `semantic`.

- [ ] **Step 1: Project config**

`jaffle_shop/dbt_project.yml`

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
models:
  jaffle_shop:
    +materialized: table
```

`jaffle_shop/profiles.yml`

```yaml
jaffle_shop:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: jaffle_shop.duckdb
      threads: 4
      plugins:
        - module: jevdbt.plugin
          config:
            mode: auto        # live when TYPESAFE_API_KEY is set, else SIMULATED
            pack: 1           # override with JEV_PACK; only record at a pack size that passed the gate
            concurrency: 32
            rpm: 1200
            model: jev-latest
```

- [ ] **Step 2: Macros**

`jaffle_shop/macros/jev_expect.sql`

```sql
{#-
  Semantic test: fails on rows where Jev judges `fails_if` to be true with p >= threshold.
  State sent to Jev is a JSON object of the tested column plus `context` columns.
-#}
{% test jev_expect(model, column_name, fails_if, context=[], threshold=0.5, criteria=none) %}
  {%- if fails_if is not string or not (fails_if | trim) -%}
    {{ exceptions.raise_compiler_error("jev_expect: `fails_if` must be a non-empty sentence") }}
  {%- endif -%}
  {%- if threshold is not number or threshold <= 0 or threshold > 1 -%}
    {{ exceptions.raise_compiler_error("jev_expect: `threshold` must be in (0, 1], got " ~ threshold) }}
  {%- endif -%}
  {%- set question = {"instructions": fails_if} -%}
  {%- if criteria is not none -%}
    {%- set normalized = {} -%}
    {%- for key, value in criteria.items() -%}
      {%- set k = (key | string | lower) -%}
      {%- if k not in ["true", "false"] -%}
        {{ exceptions.raise_compiler_error("jev_expect: `criteria` keys must be true/false, got " ~ key) }}
      {%- endif -%}
      {%- do normalized.update({k: value}) -%}
    {%- endfor -%}
    {%- do question.update({"criteria": normalized}) -%}
  {%- endif -%}
  {%- set fields = [column_name] + context -%}

with judged as materialized (
  select
    *,
    jev_noul(
      case when {{ column_name }} is null then null
           else to_json(struct_pack({% for f in fields %}{{ f }} := {{ f }}{{ ", " if not loop.last else "" }}{% endfor %}))
      end,
      '{{ tojson(question) | replace("'", "''") }}'
    ) as jev_p
  from {{ model }}
)
select * from judged where jev_p >= {{ threshold }}
{% endtest %}
```

`jaffle_shop/macros/jev_summary.sql`

```sql
{% macro jev_summary() %}
  {%- if execute -%}
    {%- set result = run_query("select jev_stats()") -%}
    {%- set stats = fromjson(result.columns[0].values()[0]) -%}
    {%- if stats["judgments"] > 0 -%}
      {%- do log(stats["summary"], info=True) -%}
    {%- endif -%}
  {%- endif -%}
{% endmacro %}
```

- [ ] **Step 3: Models** (one select each; rename ids)

```sql
-- stg_customers.sql
select id as customer_id, first_name, last_name,
       trim(concat_ws(' ', first_name, last_name)) as full_name, email
from {{ ref('raw_customers') }}
-- stg_orders.sql
select id as order_id, user_id as customer_id, order_date, status from {{ ref('raw_orders') }}
-- stg_returns.sql
select id as return_id, order_id, reason_code, comment from {{ ref('raw_returns') }}
-- stg_reviews.sql
select id as review_id, order_id, stars, body from {{ ref('raw_reviews') }}
-- stg_tickets.sql
select id as ticket_id, customer_id, subject, body from {{ ref('raw_tickets') }}
```

- [ ] **Step 4: `schema.yml`** — standard tests plus the four semantic tests. Wording below is the starting point; T10 may tune it (logged).

```yaml
version: 2

models:
  - name: stg_customers
    columns:
      - name: customer_id
        data_tests: [unique, not_null]
      - name: email
        data_tests: [unique, not_null]
      - name: full_name
        data_tests:
          - not_null
          - jev_expect:
              name: customers_full_name_is_a_person
              arguments:
                fails_if: "`full_name` is not a real individual person's name: it is a placeholder, test value, keyboard mash, company or organisation name, email address, or otherwise not a person."
                context: [email]
                threshold: 0.7
                criteria:
                  "true": "Clearly not a real person's name"
                  "false": "Plausibly a real person's name, including unusual, very short, single-word, or non-Western names"
              config: {severity: error, store_failures: true, tags: [semantic]}

  - name: stg_orders
    columns:
      - name: order_id
        data_tests: [unique, not_null]
      - name: customer_id
        data_tests:
          - not_null
          - relationships: {arguments: {to: ref('stg_customers'), field: customer_id}}
      - name: status
        data_tests:
          - accepted_values: {arguments: {values: [placed, shipped, completed, return_pending, returned]}}

  - name: stg_returns
    columns:
      - name: return_id
        data_tests: [unique, not_null]
      - name: order_id
        data_tests:
          - unique
          - relationships: {arguments: {to: ref('stg_orders'), field: order_id}}
      - name: reason_code
        data_tests:
          - not_null
          - accepted_values: {arguments: {values: [damaged, wrong_item, late, changed_mind, other]}}
      - name: comment
        data_tests:
          - not_null
          - jev_expect:
              name: returns_comment_matches_reason_code
              arguments:
                fails_if: "The customer's `comment` describes a different main reason for the return than `reason_code` (damaged, wrong_item, late, changed_mind, other)."
                context: [reason_code]
                threshold: 0.8
                criteria:
                  "true": "The stated main reason plainly belongs to another code"
                  "false": "Consistent with the code, or too vague to tell; code 'other' fits anything unusual"
              config: {severity: error, store_failures: true, tags: [semantic]}

  - name: stg_reviews
    columns:
      - name: review_id
        data_tests: [unique, not_null]
      - name: order_id
        data_tests:
          - unique
          - relationships: {arguments: {to: ref('stg_orders'), field: order_id}}
      - name: stars
        data_tests:
          - not_null
          - accepted_values: {arguments: {values: [1, 2, 3, 4, 5], quote: false}}
      - name: body
        data_tests:
          - not_null
          - jev_expect:
              name: reviews_body_matches_stars
              arguments:
                fails_if: "The overall sentiment of the review `body` clearly contradicts its `stars` rating (1 = very bad, 5 = excellent)."
                context: [stars]
                threshold: 0.8
                criteria:
                  "true": "A glowing text with 1-2 stars, or an angry/negative text with 4-5 stars"
                  "false": "Sentiment roughly matches the stars, including sarcasm that matches a low rating and mixed 3-star reviews"
              config: {severity: error, store_failures: true, tags: [semantic]}

  - name: stg_tickets
    columns:
      - name: ticket_id
        data_tests: [unique, not_null]
      - name: customer_id
        data_tests:
          - relationships: {arguments: {to: ref('stg_customers'), field: customer_id}}
      - name: subject
        data_tests: [not_null]
      - name: body
        data_tests:
          - not_null
          - jev_expect:
              name: tickets_body_has_no_pii
              arguments:
                fails_if: "The ticket `body` contains personal data that could identify or contact a specific private person, such as a home address, personal phone number, personal email address, bank account number (IBAN), or date of birth."
                threshold: 0.5
                criteria:
                  "true": "Contains at least one such personal detail about a private person"
                  "false": "No such detail; order numbers, the shop's own address or phone, and a first name alone are not personal data"
              config: {severity: error, store_failures: true, tags: [semantic]}
```

If `email` is not unique in the generated data, fix the generator's email rule in T6's file (adding `{id}` already guarantees uniqueness) — never drop the test.

- [ ] **Step 5: Manual run (demo mode)**

```bash
cd jaffle_shop
JEV_MODE=demo JEV_NO_CACHE=1 DOTENV_DISABLE=1 uv run dbt build --profiles-dir . --exclude tag:semantic
JEV_MODE=demo JEV_NO_CACHE=1 DOTENV_DISABLE=1 uv run dbt test --profiles-dir . --select tag:semantic
```

Expected: first command `Done. PASS=… ERROR=0`; second shows 4 tests, some `FAIL n`, and a line `Jev · 1,300 judgments · 0% cached · … SIMULATED demo pack=1`. Exactly 1,300 proves one evaluation per row. No deprecation warning about missing `arguments`.

- [ ] **Step 6: Integration test** — `tests/test_dbt_project.py`

```python
import os
import shutil
import subprocess
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).parents[1]
SEMANTIC = ["customers_full_name_is_a_person", "returns_comment_matches_reason_code",
            "reviews_body_matches_stars", "tickets_body_has_no_pii"]
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    dst = tmp_path_factory.mktemp("dbt") / "jaffle_shop"
    shutil.copytree(ROOT / "jaffle_shop", dst, ignore=shutil.ignore_patterns("target", "logs", "*.duckdb*", ".jev_cache.sqlite"))
    return dst


def dbt(project, *args, **env):
    full_env = {**os.environ, "JEV_MODE": "demo", "JEV_NO_CACHE": "1", "DOTENV_DISABLE": "1", **env}
    full_env.pop("TYPESAFE_API_KEY", None)
    return subprocess.run(["uv", "run", "--project", str(ROOT), "dbt", *args, "--profiles-dir", "."],
                          cwd=project, env=full_env, capture_output=True, text=True, timeout=600)


def test_standard_tests_green(project):
    r = dbt(project, "build", "--exclude", "tag:semantic", "tag:baseline")
    assert r.returncode == 0, r.stdout[-3000:]
    assert "ERROR=0" in r.stdout
    assert "MissingArgumentsPropertyInGenericTestDeprecation" not in r.stdout


def test_semantic_tests_store_failures_and_summary(project):
    r = dbt(project, "test", "--select", "tag:semantic")
    assert "Jev · 1,300 judgments" in r.stdout, r.stdout[-3000:]
    assert "SIMULATED" in r.stdout
    con = duckdb.connect(str(project / "jaffle_shop.duckdb"), read_only=True)
    for name in SEMANTIC:
        cols = [c[0] for c in con.execute(f"select * from main_dbt_test__audit.{name} limit 0").description]
        assert "jev_p" in cols, name


def test_bad_threshold_is_a_compile_error(project, tmp_path):
    schema = project / "models" / "staging" / "schema.yml"
    original = schema.read_text()
    schema.write_text(original.replace("threshold: 0.8", "threshold: 1.5", 1))
    try:
        r = dbt(project, "compile", "--select", "tag:semantic")
        assert r.returncode != 0 and "threshold" in (r.stdout + r.stderr)
    finally:
        schema.write_text(original)
```

Run: `uv run pytest -q` (all, including slow) → pass; `uv run ruff check` → clean.

- [ ] **Step 7: Commit** `feat: jaffle_shop dbt project with jev_expect semantic tests`.

---

### Task 8: Regex/keyword baseline tests

**Files:**
- Create: `jaffle_shop/tests/baseline/baseline_customers_full_name_is_a_person.sql`, `baseline_returns_comment_matches_reason_code.sql`, `baseline_reviews_body_matches_stars.sql`, `baseline_tickets_body_has_no_pii.sql`
- Modify: `tests/test_dbt_project.py` (add one test)

**Interfaces:**
- Produces: store_failures tables `main_dbt_test__audit.baseline_<semantic test name>` carrying the model's id column; tag `baseline`.

The baseline is an honest "30 minutes of regex" effort, written now, before any live Jev result. It is not tuned after seeing Jev's numbers. It may be tuned against the *pool files* before T10 only if a rule is obviously broken (e.g. a regex syntax slip), logged in the commit message.

- [ ] **Step 1: Write the four singular tests** (DuckDB regex = RE2; `(?i)` for case-insensitive)

`baseline_tickets_body_has_no_pii.sql`

```sql
{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
select * from {{ ref('stg_tickets') }}
where regexp_matches(body, '\b[A-Z]{2}\d{2}\s?[A-Z]{4}(\s?\d{4}){2}\s?\d{2}\b')              -- NL IBAN, spaced or not
   or regexp_matches(body, '(\+31|0031|\b0)[\s-]?6[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{2}\b')  -- NL mobile
   or regexp_matches(body, '(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}')                          -- email
   or regexp_matches(body, '\b\d{4}\s?[A-Z]{2}\b')                                                -- NL postcode
   or regexp_matches(body, '(?i)\b[a-z]+(straat|laan|weg|plein|gracht|kade|singel)\s+\d+')        -- street + number
   or regexp_matches(body, '(?i)\b(born|date of birth|dob)\b')
```

`baseline_returns_comment_matches_reason_code.sql`

```sql
{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
with keyworded as (
  select *,
    case
      when regexp_matches(comment, '(?i)(broken|burnt|burned|crushed|squashed|leak|spilled|damaged|soggy|mould|mold|raw)') then 'damaged'
      when regexp_matches(comment, '(?i)(wrong|instead of|not what i ordered|someone else|different order|missing)') then 'wrong_item'
      when regexp_matches(comment, '(?i)(late|hours?|waited|took forever|delay|still waiting|\d+\s?min)') then 'late'
      when regexp_matches(comment, '(?i)(changed my mind|don''t need|no longer|by mistake|accident|cancel)') then 'changed_mind'
    end as keyword_code
  from {{ ref('stg_returns') }}
)
select * from keyworded
where keyword_code is not null and reason_code <> 'other' and keyword_code <> reason_code
```

`baseline_reviews_body_matches_stars.sql`

```sql
{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
with lexicon as (
  select *,
    len(regexp_extract_all(lower(body), '\b(great|love|loved|amazing|delicious|best|perfect|excellent|fantastic|tasty|recommend|good|lovely|fresh|yum)\b'))
    - len(regexp_extract_all(lower(body), '\b(never|worst|awful|terrible|disgusting|cold|raw|bad|horrible|inedible|refund|disappointed|soggy|gross)\b'))
      as sentiment
  from {{ ref('stg_reviews') }}
)
select * from lexicon
where (stars >= 4 and sentiment < 0) or (stars <= 2 and sentiment > 0)
```

`baseline_customers_full_name_is_a_person.sql`

```sql
{{ config(tags=['baseline'], store_failures=true, severity='warn') }}
select * from {{ ref('stg_customers') }}
where regexp_matches(full_name, '(?i)\b(test|dummy|asdf|qwerty|xxx|n/?a|unknown|sample|foo|bar|none|null)\b')
   or full_name like '%@%'
   or regexp_matches(full_name, '(?i)\b(bv|b\.v\.|ltd|llc|inc|gmbh|nv|co|company|holding|group)\b')
   or regexp_matches(full_name, '\d')
   or lower(first_name) = lower(last_name)
   or not regexp_matches(lower(full_name), '[aeiouy]')
```

Baseline tests use `severity='warn'` so `dbt build` excluding only `tag:semantic` stays green-with-warnings; the recording's beat 1 excludes both tags.

- [ ] **Step 2: Add integration test** to `tests/test_dbt_project.py`

```python
def test_baseline_tables_exist(project):
    r = dbt(project, "test", "--select", "tag:baseline")
    assert r.returncode == 0, r.stdout[-3000:]  # severity warn
    con = duckdb.connect(str(project / "jaffle_shop.duckdb"), read_only=True)
    for name in SEMANTIC:
        con.execute(f"select count(*) from main_dbt_test__audit.baseline_{name}").fetchone()
```

- [ ] **Step 3: Run** `uv run pytest -q && uv run ruff check` → pass. Also run `cd jaffle_shop && uv run dbt test --profiles-dir . --select tag:baseline` and eyeball warn counts (each should be > 0).
- [ ] **Step 4: Commit** `feat: regex/keyword baseline tests`.

---

### Task 9: Scorecard and failure viewer

**Files:**
- Create: `scripts/score.py`, `scripts/show_failures.py`, `docs/eval-results.md`
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: store_failures tables (T7, T8), `eval/golden_defects.csv` (T6).
- Produces: `score.py` functions `load_golden(path) -> dict[str, dict[int, str]]` (test → {id: label}), `metrics(flagged: set[int], golden: dict[int, str]) -> Metrics` (dataclass: `flagged, tp, fp, fn, hard_neg_flagged, precision, recall, f1`), `gate(results: dict[str, tuple[Metrics, Metrics]], summary: str|None) -> tuple[bool, list[str]]`, `parse_summary(stdout: str) -> str|None`; CLI flags `--run`, `--pack N`, `--fresh`, `--mode live|demo`, `--append`, `--db PATH`.

`TESTS = {"customers_full_name_is_a_person": "customer_id", "returns_comment_matches_reason_code": "return_id", "reviews_body_matches_stars": "review_id", "tickets_body_has_no_pii": "ticket_id"}`.

Metric definitions: `precision = tp/flagged` (0.0 when nothing flagged), `recall = tp/defects`, `f1` harmonic mean (0.0 if both 0). Gate passes iff summary is not None, contains `LIVE`, does not contain ` errors`, and for every test Jev precision ≥ 0.85, recall ≥ 0.85, and Jev f1 > baseline f1. Returns the list of reasons for any failure.

- [ ] **Step 1: Failing tests** — `tests/test_score.py`

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("score", ROOT / "scripts" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

GOLD = {1: "defect", 2: "defect", 3: "hard_negative", 4: "defect"}


def test_metrics():
    m = score.metrics({1, 2, 3, 9}, GOLD)
    assert (m.flagged, m.tp, m.fp, m.fn, m.hard_neg_flagged) == (4, 2, 2, 1, 1)
    assert m.precision == 0.5 and round(m.recall, 3) == 0.667


def test_metrics_nothing_flagged():
    m = score.metrics(set(), GOLD)
    assert (m.precision, m.recall, m.f1) == (0.0, 0.0, 0.0)


def test_parse_summary_strips_ansi():
    out = "\x1b[0m19:26:50  Jev · 1,300 judgments · 0% cached · 1,300 requests · 64.2 s · $0.004 · LIVE jev-latest pack=1\n"
    assert score.parse_summary(out).startswith("Jev · 1,300 judgments")
    assert score.parse_summary("nothing") is None


def test_gate():
    good = score.metrics({1, 2, 4}, GOLD)
    weak = score.metrics({1}, GOLD)
    live = "Jev · 10 judgments · LIVE jev-latest pack=1"
    ok, reasons = score.gate({"t": (good, weak)}, live)
    assert ok and reasons == []
    ok, reasons = score.gate({"t": (good, weak)}, live.replace("LIVE", "SIMULATED"))
    assert not ok
    ok, reasons = score.gate({"t": (weak, good)}, live)
    assert not ok and any("recall" in r for r in reasons)
    ok, _ = score.gate({"t": (good, weak)}, live + " · 2 errors")
    assert not ok
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `scripts/score.py`**

Behaviour:
1. If `--run`: run `uv run dbt test --profiles-dir . --select tag:semantic tag:baseline` in `jaffle_shop/` with env overrides (`JEV_PACK`, `JEV_MODE`, `JEV_NO_CACHE=1` when `--fresh`), stream nothing, capture stdout, `summary = parse_summary(stdout)`. dbt's non-zero exit (test failures) is expected; fail loudly only if no `Done.` line appears.
2. Open `jaffle_shop/jaffle_shop.duckdb` read-only (`--db` overrides). For each test: Jev flagged ids = `select <id> from main_dbt_test__audit.<test>`; baseline = `... baseline_<test>`. Missing table → exit 2 with a message naming the table and the dbt command to run.
3. Print a `rich` table: columns `test`, `defects`, `Jev P`, `Jev R`, `Jev hard-neg`, `regex P`, `regex R`, `regex hard-neg`; P/R formatted `0.92`; Jev cells bold. Under it the summary line (or `summary: not captured (use --run)`), then `GATE PASS` in green or `GATE FAIL` + reasons in red (only when summary captured).
4. `--append`: append to `docs/eval-results.md` a section `## <ISO timestamp> · <mode/pack from summary>` with the summary line, a markdown table of the same numbers, the gate result, and for each test the ids of hard negatives Jev flagged and defects Jev missed (for wording work in T10).

`parse_summary`: strip ANSI `\x1b\[[0-9;]*m`, return the substring starting at `Jev · ` on the last line containing it, stripped; else None.

`scripts/show_failures.py` (recording beat 4): for each semantic test, print a `rich` panel titled with the test name listing the top `--limit` (default 2) stored-failure rows by `jev_p` desc: id, the judged text (+ context column value) truncated to 90 chars, `jev_p` formatted `0.97`. Text columns per test: customers `full_name`, returns `reason_code` + `comment`, reviews `stars` + `body`, tickets `body`. Read-only DB connection.

`docs/eval-results.md` starts with:

```markdown
# Eval results

Every scored run, newest last. Written by `scripts/score.py --append`. Gate: live, no errors,
Jev precision ≥ 0.85 and recall ≥ 0.85 on every test, and Jev F1 > regex-baseline F1 on every test.
Wording/threshold changes are logged here with before/after numbers.
```

- [ ] **Step 4: Run** `uv run pytest -q && uv run ruff check` → pass. Smoke: `JEV_MODE=demo uv run python scripts/score.py --run --fresh --mode demo` prints the table and no GATE PASS (simulated).
- [ ] **Step 5: Commit** `feat: scorecard vs golden key and failure viewer`.

---

### Task 10: Live gate run (controller only — not delegated)

**Files:** Modify `docs/eval-results.md`; possibly `jaffle_shop/models/staging/schema.yml` (wording/thresholds only).

- [ ] **Step 1: Key.** `ln -s ../jev-demo-3/.env .env` (the user populated that file with a live key; do not read or print it). Verify only via a live run.
- [ ] **Step 2: Build.** `cd jaffle_shop && uv run dbt build --profiles-dir . --exclude tag:semantic` → green (baseline warns).
- [ ] **Step 3: pack=1 fresh.** `uv run python scripts/score.py --run --fresh --pack 1 --mode live --append`. Expect ~1 min. Record result.
- [ ] **Step 4: pack=8 fresh.** Same with `--pack 8 --append`.
- [ ] **Step 5: If a test fails the gate at pack=1**: inspect the missed/false-flagged ids from eval-results, adjust only `fails_if` / `criteria` / `threshold` for that test, rerun Step 3 for it, log before/after. At most 3 iterations per test. A golden-key label is changed only if the pool entry is demonstrably mislabeled to a careful human — fix the pool entry's group, regenerate seeds, log it. If still failing: reframe or drop the test from the recording and note it in eval-results and the final report.
- [ ] **Step 6: Choose recording pack**: largest of {8, 1} that passed.
- [ ] **Step 7: Commit** `docs: live eval results` (+ any wording changes).

---

### Task 11: Recording script and docs

**Files:**
- Create: `scripts/record.sh`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: `scripts/record.sh`**

```bash
#!/usr/bin/env bash
# Typewriter runner for the screen recording. Keypress advances each beat.
# Usage: scripts/record.sh [--cold] [--pack N]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/jaffle_shop"
source "$ROOT/.venv/bin/activate"
COLD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cold) COLD=1; shift ;;
    --pack) export JEV_PACK="$2"; shift 2 ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done
TYPE_DELAY="${TYPE_DELAY:-0.03}"

# Preflight (not recorded): fresh models + baseline tables for the scorecard.
dbt build --profiles-dir . --exclude tag:semantic --quiet >/dev/null 2>&1 || true
[[ $COLD == 1 ]] && rm -f .jev_cache.sqlite

type_cmd() {
  printf '\033[1;32m❯\033[0m '
  local s="$1"
  for ((i = 0; i < ${#s}; i++)); do printf '%s' "${s:i:1}"; sleep "$TYPE_DELAY"; done
  printf '\n'
}
beat() {
  read -rsn1
  type_cmd "$1"
  eval "$1" || true
  echo
}

clear
beat "dbt build --profiles-dir . --exclude tag:semantic tag:baseline"
beat "grep --color=always -A10 'jev_expect:' models/staging/schema.yml"
beat "dbt test --profiles-dir . --select tag:semantic"
beat "python ../scripts/show_failures.py"
beat "python ../scripts/score.py"
beat "dbt test --profiles-dir . --select tag:semantic"
read -rsn1
```

`chmod +x scripts/record.sh`. Smoke in demo mode: `JEV_MODE=demo DOTENV_DISABLE=1 TYPE_DELAY=0 yes '' | scripts/record.sh` completes without error. (`read -rsn1` consumes a newline from `yes ''`.)

- [ ] **Step 2: `README.md`** — what it is (3 sentences), the `schema.yml` example, how it works (plugin → UDF → scorer → Jev, as a 5-step list), run commands (`uv sync`, `uv run python scripts/make_seeds.py`, dbt build/test, score), live vs SIMULATED, the latest gated numbers copied from `docs/eval-results.md` with date and pack, recording instructions, and "why dbt-core not Fusion" (one paragraph).
- [ ] **Step 3: `CLAUDE.md`** — modelled on `~/Projects/jev-demo-3/CLAUDE.md`: one-line description + spec path; Commands (sync, seeds, dbt demo/live, pytest incl. `-m "not slow"`, ruff, score, record); Rules (never read `.env`; always project venv dbt, never global Fusion `dbt`; `as materialized` must stay; SIMULATED always labelled; never edit data/golden/baseline to make Jev win; changing `fails_if`/`criteria`/`threshold` → rerun `score.py --run --fresh --append`).
- [ ] **Step 4: Run** full `uv run pytest -q && uv run ruff check`.
- [ ] **Step 5: Commit** `docs: README, CLAUDE.md and recording script`.
