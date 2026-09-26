# Jev VISUALIZE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A localhost web demo where a SQL query ending in `VISUALIZE '<intent>'` is charted by letting TypeSafe's Jev model rank code-generated chart candidates.

**Architecture:** Python/FastAPI backend does everything: split off the `VISUALIZE` clause, run SQL in read-only DuckDB, profile the result, enumerate valid Vega-Lite candidates by rule, ask Jev one batched request of Score/Noul questions, rank, and stream an NDJSON response. A thin Vite/React frontend renders a flat json-render spec whose `Chart` component wraps vega-embed.

**Tech Stack:** Python 3.13, uv, DuckDB, FastAPI, uvicorn, typesafe-sdk, pytest, ruff · Vite, React 19, TypeScript, `@json-render/core`, `@json-render/react`, zod, vega-embed, CodeMirror 6, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-21-jev-visualize-design.md` — read it before any task.

## Global Constraints

- Python `>=3.13`, managed with `uv`. Package name `jevviz`, source in `src/jevviz/`.
- Jev is never asked to count, compare numbers, or produce text. All numeric guards live in `profile.py` / `rules/`.
- Jev model string: `"jev-latest"`. Env var: `TYPESAFE_API_KEY` (read server-side only; never logged, never printed, never sent to the client; never read `.env` contents in a tool call).
- Price constant: `0.042` USD per 1M input tokens; output free.
- Candidate cap 24 (`table` and `kpi` exempt); max 4 candidates per rule; max 6 intents per query; row cap 5,000.
- Rank key is `P(level >= 2)`; never use the interpolated `score`.
- Only five renderable component types: `Grid`, `Panel`, `Chart`, `Kpi`, `Table`.
- Every Vega-Lite spec uses `"data": {"name": "rows"}`; rows are sent once.
- A viz failure never hides the data: the table from the `result` event stays on screen.
- DuckDB demo DB opens `read_only=True` with `enable_external_access=false`; server binds `127.0.0.1` only.
- Demo mode (no key) must show a visible `SIMULATED` badge; all tests except `eval` and the probe run offline.
- Do not use json-render's `experimental_*` APIs.
- Commit after every task. End commit messages with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## File Structure

```
pyproject.toml
src/jevviz/
  __init__.py
  types.py          Question, Answer, JudgeResult, Column, Profile, Candidate (all shared dataclasses)
  backend.py        Backend protocol, JevBackend, DemoBackend, make_backend()
  cache.py          sqlite cache: (model, state_hash, question) -> Answer
  parse.py          extract_viz()
  data.py           seeded synthetic retailer -> DuckDB file
  db.py             open_db(), run_query()
  profile.py        profile()
  rules/
    __init__.py     registry, @rule, enumerate_candidates()
    titles.py       humanise(), describe helpers
    basic.py        table, kpi, bar, pie, line, multi_line
    advanced.py     grouped_bar, stacked_bar, scatter, histogram, heatmap
  viz_questions.py  build_questions(), state_for()
  rank.py           rank_key(), match_band(), rank_panels()
  spec.py           assemble_spec()
  pipeline.py       visualize(): profile -> candidates -> judge -> rank -> spec
  api.py            FastAPI app, POST /run NDJSON stream
  eval.py           golden-set eval, Jev vs rules-only
  golden.toml       golden set
scripts/probe_questions.py   throwaway probe (Task 1)
tests/              one test file per module
web/                Vite + React frontend (Tasks 12-14)
```

Shared dataclasses live in `types.py` so no module imports another module's internals.

---

### Task 0: Project scaffold, shared types, backend, cache

**Files:**
- Create: `pyproject.toml`, `src/jevviz/__init__.py`, `src/jevviz/types.py`, `src/jevviz/backend.py`, `src/jevviz/cache.py`
- Test: `tests/test_types.py`, `tests/test_backend.py`, `tests/test_cache.py`

**Interfaces:**
- Produces (`types.py`):
  - `Question(kind: Literal["noul","score"], instructions: str, levels: tuple[str,...] = ())` with `.key() -> str`
  - `Answer(kind: str, noul: float | None = None, probabilities: dict[int,float] | None = None, confidence: float | None = None)`
  - `JudgeResult(answers: dict[str, Answer], input_tokens: int, error: str | None = None)`
  - `Column(name, kind: tuple[str,...], distinct: int, null_share: float, min, max, samples: tuple, evenly_spaced: bool, position: int)`
  - `Profile(columns: tuple[Column,...], row_count: int)` with `.hash() -> str`, `.by_kind(kind) -> list[Column]`
  - `Candidate(id, kind, columns: tuple[str,...], measures: tuple[str,...], title, description, vega: dict)`
- Produces (`backend.py`): `Backend` protocol with `name: str`, `simulated: bool`, `async judge(state: dict, questions: dict[str, Question]) -> JudgeResult`, `async aclose()`; `make_backend(demo: bool | None = None, model: str = "jev-latest") -> Backend`
- Produces (`cache.py`): `Cache(path)` with `get_many(model, state_hash, questions: dict[str, Question]) -> dict[str, Answer]`, `put_many(model, state_hash, questions, answers: dict[str, Answer]) -> None`, `close()`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "jevviz"
version = "0.1.0"
description = "SQL VISUALIZE clause ranked by TypeSafe Jev"
requires-python = ">=3.13"
dependencies = [
    "duckdb>=1.5.5",
    "fastapi>=0.115",
    "uvicorn>=0.32",
    "python-dotenv>=1.0",
    "typesafe-sdk>=0.7.0",
]

[build-system]
requires = ["uv_build>=0.12.9,<0.13.0"]
build-backend = "uv_build"

[dependency-groups]
dev = ["pytest>=9.1.1", "pytest-asyncio>=1.4.0", "httpx>=0.27", "jsonschema>=4.23", "ruff>=0.16.8"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["live: needs TYPESAFE_API_KEY and network"]
addopts = "-m 'not live'"
```

Create `src/jevviz/__init__.py` containing only `"""Jev VISUALIZE demo."""`. Run `uv sync`. Expected: resolves and creates `.venv`.

- [ ] **Step 2: Write failing tests for types**

`tests/test_types.py`:

```python
import pytest
from jevviz.types import Column, Profile, Question


def col(name, kind, distinct=5, position=0):
    return Column(name=name, kind=kind, distinct=distinct, null_share=0.0,
                  min=None, max=None, samples=("a",), evenly_spaced=False, position=position)


def test_question_key_is_stable_and_distinguishes_levels():
    a = Question("score", "how well", ("bad", "good"))
    b = Question("score", "how well", ("bad", "great"))
    assert a.key() == Question("score", "how well", ("bad", "good")).key()
    assert a.key() != b.key()


def test_score_needs_two_levels():
    with pytest.raises(ValueError):
        Question("score", "x", ("only",))


def test_profile_hash_deterministic_and_order_sensitive():
    p1 = Profile((col("a", ("nominal",)), col("b", ("quantitative",), position=1)), 10)
    p2 = Profile((col("a", ("nominal",)), col("b", ("quantitative",), position=1)), 10)
    p3 = Profile((col("a", ("nominal",)),), 10)
    assert p1.hash() == p2.hash()
    assert p1.hash() != p3.hash()


def test_by_kind_includes_dual_tagged_columns():
    rating = col("rating", ("nominal", "quantitative"))
    p = Profile((rating,), 5)
    assert p.by_kind("nominal") == [rating]
    assert p.by_kind("quantitative") == [rating]
```

Run: `uv run pytest tests/test_types.py -q` — Expected: FAIL, `ModuleNotFoundError: jevviz.types`.

- [ ] **Step 3: Implement `src/jevviz/types.py`**

```python
"""Shared plain-data types. No module-specific logic lives here."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Question:
    kind: Literal["noul", "score"]
    instructions: str
    levels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.instructions.strip():
            raise ValueError("instructions must be non-empty")
        if self.kind == "score" and len(self.levels) < 2:
            raise ValueError("score questions need at least 2 levels")

    def key(self) -> str:
        return "|".join([self.kind, self.instructions, "\x1e".join(self.levels)])


@dataclass(frozen=True)
class Answer:
    kind: str
    noul: float | None = None
    probabilities: dict[int, float] | None = None
    confidence: float | None = None


@dataclass
class JudgeResult:
    answers: dict[str, Answer]
    input_tokens: int
    error: str | None = None


@dataclass(frozen=True)
class Column:
    name: str
    kind: tuple[str, ...]          # subset of ("temporal", "quantitative", "nominal")
    distinct: int
    null_share: float
    min: Any
    max: Any
    samples: tuple
    evenly_spaced: bool
    position: int


@dataclass(frozen=True)
class Profile:
    columns: tuple[Column, ...]
    row_count: int

    def by_kind(self, kind: str) -> list[Column]:
        return [c for c in self.columns if kind in c.kind]

    def get(self, name: str) -> Column:
        return next(c for c in self.columns if c.name == name)

    def hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class Candidate:
    id: str
    kind: str
    columns: tuple[str, ...]
    measures: tuple[str, ...]
    title: str
    description: str
    vega: dict
```

Run: `uv run pytest tests/test_types.py -q` — Expected: 4 passed.

- [ ] **Step 4: Write failing tests for backend**

`tests/test_backend.py`:

```python
from jevviz.backend import DemoBackend, make_backend
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
```

Run: `uv run pytest tests/test_backend.py -q` — Expected: FAIL, module not found.

- [ ] **Step 5: Implement `src/jevviz/backend.py`**

```python
"""Judgment backends: the real TypeSafe Jev API and a deterministic offline stand-in."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Protocol

from jevviz.types import Answer, JudgeResult, Question

_ID_HINTS = ("_id", "id", "zip", "code", "postcode", "sku", "number")
_WORD = re.compile(r"[a-z]+")
_STOP = frozenset("a an the is are of in on for with and or to how what which by this that".split())
_SYNONYMS = {
    "trend": {"time", "change", "changes", "over"}, "trending": {"time", "change", "changes", "over"},
    "share": {"proportion", "part", "whole"}, "compare": {"compared", "comparison", "across"},
    "relationship": {"correlation", "against", "versus"}, "distribution": {"spread", "histogram"},
}


class Backend(Protocol):
    name: str
    simulated: bool

    async def judge(self, state: dict, questions: dict[str, Question]) -> JudgeResult: ...
    async def aclose(self) -> None: ...


class JevBackend:
    def __init__(self, model: str = "jev-latest") -> None:
        self.name = model
        self.simulated = False
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from typesafe_sdk import AsyncTypeSafeClient
            self._client = AsyncTypeSafeClient(model=self.name)
        return self._client

    async def judge(self, state: dict, questions: dict[str, Question]) -> JudgeResult:
        from typesafe_sdk import Noul, Score, TypeSafeError
        sdk_qs = {
            qid: Noul(instructions=q.instructions) if q.kind == "noul"
            else Score(instructions=q.instructions, criteria=list(q.levels))
            for qid, q in questions.items()
        }
        try:
            resp = await self._ensure_client().system_one(state, sdk_qs)
        except TypeSafeError as exc:
            return JudgeResult(answers={}, input_tokens=0, error=f"{type(exc).__name__}: {exc}")
        answers: dict[str, Answer] = {}
        for qid, q in questions.items():
            raw = resp.answers.get(qid)
            if raw is None:
                continue
            if q.kind == "noul":
                answers[qid] = Answer("noul", noul=float(raw.noul))
            else:
                answers[qid] = Answer("score", probabilities={int(k): float(v) for k, v in raw.probabilities.items()},
                                      confidence=float(raw.confidence))
        return JudgeResult(answers=answers, input_tokens=resp.usage.input_tokens)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


def _tokens(text: str) -> set[str]:
    words = {w for w in _WORD.findall(text.lower()) if w not in _STOP}
    for w in list(words):
        words |= _SYNONYMS.get(w, set())
    return words


class DemoBackend:
    """Deterministic, offline. Scores by token overlap between intent and panel description."""

    name = "demo"
    simulated = True

    async def judge(self, state: dict, questions: dict[str, Question]) -> JudgeResult:
        await asyncio.sleep(0.15)
        answers = {qid: self._answer(q) for qid, q in questions.items()}
        return JudgeResult(answers=answers, input_tokens=sum(len(q.instructions) // 4 for q in questions.values()))

    def _answer(self, q: Question) -> Answer:
        if q.kind == "noul":
            m = re.search(r"`([^`]+)`", q.instructions)
            name = (m.group(1) if m else "").lower()
            hit = any(name == h or name.endswith(h) for h in _ID_HINTS)
            return Answer("noul", noul=0.9 if hit else 0.1)
        quoted = re.findall(r'"([^"]*)"', q.instructions)
        intent, desc = (quoted + ["", ""])[:2]
        it, dt = _tokens(intent), _tokens(desc)
        overlap = len(it & dt) / max(len(it), 1)
        hi = min(0.95, 0.1 + overlap)
        n = len(q.levels)
        probs = {i: 0.0 for i in range(n)}
        probs[n - 1] = hi * 0.6
        probs[n - 2] = hi * 0.4
        rest = (1.0 - hi) / (n - 2) if n > 2 else 0.0
        for i in range(n - 2):
            probs[i] = rest
        if n == 2:
            probs[0] = 1.0 - hi
            probs[1] = hi
        return Answer("score", probabilities=probs, confidence=max(probs.values()))

    async def aclose(self) -> None:
        return None


def make_backend(demo: bool | None = None, model: str = "jev-latest") -> Backend:
    if demo is None:
        demo = not os.environ.get("TYPESAFE_API_KEY")
    return DemoBackend() if demo else JevBackend(model=model)
```

Run: `uv run pytest tests/test_backend.py -q` — Expected: 3 passed.

- [ ] **Step 6: Write failing tests for cache**

`tests/test_cache.py`:

```python
from jevviz.cache import Cache
from jevviz.types import Answer, Question

Q = {"a": Question("noul", "is a?"), "b": Question("score", "how?", ("lo", "hi"))}


def test_roundtrip_and_miss(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    assert c.get_many("m", "h1", Q) == {}
    c.put_many("m", "h1", Q, {"a": Answer("noul", noul=0.8),
                              "b": Answer("score", probabilities={0: 0.25, 1: 0.75}, confidence=0.5)})
    got = c.get_many("m", "h1", Q)
    assert got["a"].noul == 0.8
    assert got["b"].probabilities == {0: 0.25, 1: 0.75}
    assert c.get_many("m", "other-hash", Q) == {}
    assert c.get_many("other-model", "h1", Q) == {}
    c.close()
```

Run: `uv run pytest tests/test_cache.py -q` — Expected: FAIL, module not found.

- [ ] **Step 7: Implement `src/jevviz/cache.py`**

```python
"""Sqlite cache of (model, state_hash, question) -> Answer."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path

from jevviz.types import Answer, Question


def _digest(model: str, state_hash: str, q: Question) -> str:
    return hashlib.sha256(f"{model}\x1f{state_hash}\x1f{q.key()}".encode()).hexdigest()


class Cache:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._con.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._con.commit()

    def get_many(self, model: str, state_hash: str, questions: dict[str, Question]) -> dict[str, Answer]:
        out: dict[str, Answer] = {}
        with self._lock:
            for qid, q in questions.items():
                row = self._con.execute("SELECT value FROM cache WHERE key = ?", (_digest(model, state_hash, q),)).fetchone()
                if row:
                    d = json.loads(row[0])
                    probs = {int(k): v for k, v in d["probabilities"].items()} if d["probabilities"] else None
                    out[qid] = Answer(d["kind"], d["noul"], probs, d["confidence"])
        return out

    def put_many(self, model: str, state_hash: str, questions: dict[str, Question], answers: dict[str, Answer]) -> None:
        rows = [
            (_digest(model, state_hash, questions[qid]),
             json.dumps({"kind": a.kind, "noul": a.noul, "probabilities": a.probabilities, "confidence": a.confidence}))
            for qid, a in answers.items() if qid in questions
        ]
        with self._lock:
            self._con.executemany("INSERT INTO cache (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", rows)
            self._con.commit()

    def close(self) -> None:
        with self._lock:
            self._con.close()
```

Run: `uv run pytest -q && uv run ruff check` — Expected: 8 passed, no lint errors.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src tests
git commit -m "feat: scaffold jevviz with shared types, Jev/demo backends and cache"
```

---

### Task 1: Question-count probe (throwaway, live key) — GATE 1

Answers the spec's open unknown: can one request carry 24 / 48 / 72 / 144 Score questions, and what does it cost in latency? The script is throwaway; only its findings are kept.

**Files:**
- Create: `scripts/probe_questions.py`, `docs/probe-results.md`

**Interfaces:**
- Consumes: `JevBackend`, `Question` from Task 0.
- Produces: a decision recorded in `docs/probe-results.md`: `MAX_QUESTIONS_PER_REQUEST = <int>`, consumed by Task 9.

- [ ] **Step 1: Write the probe**

`scripts/probe_questions.py`:

```python
"""THROWAWAY probe: how many Score questions fit in one Jev request, and how fast?"""

import asyncio
import time

from dotenv import load_dotenv

from jevviz.backend import JevBackend
from jevviz.types import Question

LEVELS = (
    "The panel shows columns that have nothing to do with what was asked.",
    "The panel uses relevant columns, but its form hides what was asked.",
    "The panel partly answers the question: right measure, missing a breakdown.",
    "The panel directly answers the question in a form that makes the pattern visible.",
)
STATE = {"sql": "SELECT region, month, sum(revenue) AS revenue FROM orders GROUP BY ALL",
         "columns": {"region": {"kind": "nominal", "distinct": 5}, "month": {"kind": "temporal", "distinct": 24},
                     "revenue": {"kind": "quantitative"}}, "row_count": 120}
FORMS = ["Line chart", "Bar chart", "Pie chart", "Heatmap", "Scatter plot", "Histogram"]


def questions(n: int) -> dict[str, Question]:
    return {f"i0.c{i:02d}": Question("score",
            f'The analyst asked: "how are regions trending". Proposed panel: "{FORMS[i % 6]} of `revenue` variant {i}." '
            "How well would this panel answer what the analyst asked?", LEVELS) for i in range(n)}


async def main() -> None:
    load_dotenv()
    backend = JevBackend()
    for n in (1, 24, 48, 72, 144):
        t0 = time.perf_counter()
        res = await backend.judge(STATE, questions(n))
        ms = (time.perf_counter() - t0) * 1000
        print(f"n={n:4d}  answered={len(res.answers):4d}  {ms:7.0f} ms  tokens={res.input_tokens}  error={res.error}")
    await backend.aclose()


asyncio.run(main())
```

- [ ] **Step 2: Run it (three times, to see variance)**

Run: `uv run python scripts/probe_questions.py`
Expected: five lines, one per n. Never print or log the API key.

- [ ] **Step 3: Record findings and decide**

Write `docs/probe-results.md` with the raw table from all three runs and one decision line:
`MAX_QUESTIONS_PER_REQUEST = N` where N is the largest n that answered every question with no error in all three runs. If n=1 already fails, stop and report the error to the project owner — do not continue.

- [ ] **Step 4: Commit**

```bash
git add scripts/probe_questions.py docs/probe-results.md
git commit -m "chore: probe Jev question-count limits and record results"
```

---

### Task 2: `extract_viz` — the VISUALIZE clause parser

**Files:**
- Create: `src/jevviz/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Produces: `extract_viz(sql: str) -> tuple[str, list[str] | None]` — `None` = no clause, `[]` = bare clause. Raises `VizSyntaxError(ValueError)`. Constant `BARE_INTENT = "the main pattern in this query's result"`, `MAX_INTENTS = 6`.

- [ ] **Step 1: Write the failing tests**

`tests/test_parse.py`:

```python
import pytest
from jevviz.parse import VizSyntaxError, extract_viz


def test_no_clause():
    assert extract_viz("SELECT 1") == ("SELECT 1", None)


def test_single_intent_case_insensitive_and_semicolon():
    sql, intents = extract_viz("SELECT a FROM t\nvisualize 'how is a trending';")
    assert sql == "SELECT a FROM t"
    assert intents == ["how is a trending"]


def test_multiple_intents_and_escaped_quote():
    _, intents = extract_viz("SELECT 1 VISUALIZE 'what''s up', 'second'")
    assert intents == ["what's up", "second"]


def test_bare_clause():
    assert extract_viz("SELECT 1 VISUALIZE") == ("SELECT 1", [])


def test_keyword_inside_string_or_comment_is_ignored():
    q = "SELECT 'VISUALIZE ''x''' AS s -- VISUALIZE 'nope'\n/* VISUALIZE 'no' */"
    assert extract_viz(q) == (q, None)


def test_keyword_as_part_of_identifier_is_ignored():
    assert extract_viz("SELECT visualize_me FROM t")[1] is None


def test_garbage_after_clause_raises():
    with pytest.raises(VizSyntaxError):
        extract_viz("SELECT 1 VISUALIZE 'a' LIMIT 5")


def test_too_many_intents_raises():
    with pytest.raises(VizSyntaxError):
        extract_viz("SELECT 1 VISUALIZE " + ", ".join(f"'i{n}'" for n in range(7)))
```

Run: `uv run pytest tests/test_parse.py -q` — Expected: FAIL, module not found.

- [ ] **Step 2: Implement `src/jevviz/parse.py`**

```python
"""Split a trailing VISUALIZE clause off a SQL statement."""

from __future__ import annotations

import re

BARE_INTENT = "the main pattern in this query's result"
MAX_INTENTS = 6
_INTENT = re.compile(r"\s*'((?:[^']|'')*)'\s*")


class VizSyntaxError(ValueError):
    pass


def _find_keyword(sql: str) -> int | None:
    """Index of the last top-level VISUALIZE keyword, skipping strings, quoted idents and comments."""
    i, n, found = 0, len(sql), None
    while i < n:
        ch = sql[i]
        if ch in "'\"":
            i += 1
            while i < n:
                if sql[i] == ch:
                    if i + 1 < n and sql[i + 1] == ch:
                        i += 2
                        continue
                    break
                i += 1
            i += 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j + 1
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
        elif sql[i:i + 9].upper() == "VISUALIZE":
            before = sql[i - 1] if i else " "
            after = sql[i + 9] if i + 9 < n else " "
            if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                found = i
            i += 9
        else:
            i += 1
    return found


def extract_viz(sql: str) -> tuple[str, list[str] | None]:
    at = _find_keyword(sql)
    if at is None:
        return sql, None
    tail = sql[at + 9:].strip().removesuffix(";").strip()
    intents: list[str] = []
    pos = 0
    while pos < len(tail):
        m = _INTENT.match(tail, pos)
        if not m:
            raise VizSyntaxError(f"expected a quoted intent after VISUALIZE, got: {tail[pos:pos + 30]!r}")
        intents.append(m.group(1).replace("''", "'"))
        pos = m.end()
        if pos < len(tail):
            if tail[pos] != ",":
                raise VizSyntaxError(f"unexpected text after VISUALIZE clause: {tail[pos:pos + 30]!r}")
            pos += 1
            if pos >= len(tail):
                raise VizSyntaxError("trailing comma in VISUALIZE clause")
    if len(intents) > MAX_INTENTS:
        raise VizSyntaxError(f"at most {MAX_INTENTS} intents per query")
    return sql[:at].rstrip(), intents
```

Run: `uv run pytest tests/test_parse.py -q` — Expected: 8 passed.

- [ ] **Step 3: Commit**

```bash
git add src/jevviz/parse.py tests/test_parse.py
git commit -m "feat: parse trailing VISUALIZE clause"
```

---

### Task 3: Synthetic retailer dataset

**Files:**
- Create: `src/jevviz/data.py`
- Test: `tests/test_data.py`

**Interfaces:**
- Produces: `generate(path: Path | str, seed: int = 7, n_orders: int = 50_000) -> None` writing tables `orders`, `customers`, `products`; CLI `uv run python -m jevviz.data [path]` (default `jevviz.duckdb`).

- [ ] **Step 1: Write the failing tests** (they assert the planted patterns, so the golden set has right answers)

`tests/test_data.py`:

```python
import duckdb
import pytest
from jevviz.data import generate


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    path = tmp_path_factory.mktemp("d") / "t.duckdb"
    generate(path, seed=7, n_orders=20_000)
    return duckdb.connect(str(path), read_only=True)


def test_tables_and_trap_columns(con):
    cols = {r[0]: r[1] for r in con.execute("DESCRIBE orders").fetchall()}
    assert {"order_date", "region", "channel", "revenue", "profit", "customer_id", "product_id"} <= set(cols)
    assert con.execute("SELECT typeof(signup_year) FROM customers LIMIT 1").fetchone()[0] in ("INTEGER", "BIGINT")
    assert con.execute("SELECT min(profit) FROM orders").fetchone()[0] < 0


def test_one_region_declines(con):
    first, last = con.execute("""
        SELECT sum(revenue) FILTER (WHERE order_date < DATE '2024-07-01'),
               sum(revenue) FILTER (WHERE order_date >= DATE '2025-07-01')
        FROM orders WHERE region = 'LATAM'""").fetchone()
    assert last < first * 0.7


def test_seasonal_spike_in_november_december(con):
    peak, base = con.execute("""
        SELECT avg(r) FILTER (WHERE m IN (11, 12)), avg(r) FILTER (WHERE m NOT IN (11, 12))
        FROM (SELECT month(order_date) m, sum(revenue) r FROM orders GROUP BY ALL)""").fetchone()
    assert peak > base * 1.4


def test_high_revenue_low_profit_category(con):
    rows = con.execute("""
        SELECT p.category, sum(o.revenue) rev, sum(o.profit) / sum(o.revenue) margin
        FROM orders o JOIN products p USING (product_id) GROUP BY ALL ORDER BY rev DESC""").fetchall()
    assert rows[0][0] == "Electronics" and rows[0][2] == min(r[2] for r in rows)


def test_price_rating_correlation(con):
    assert con.execute("SELECT corr(price, rating) FROM products").fetchone()[0] > 0.4


def test_deterministic(tmp_path):
    a, b = tmp_path / "a.duckdb", tmp_path / "b.duckdb"
    generate(a, seed=7, n_orders=2_000); generate(b, seed=7, n_orders=2_000)
    q = "SELECT sum(revenue), count(*) FROM orders"
    assert duckdb.connect(str(a)).execute(q).fetchone() == duckdb.connect(str(b)).execute(q).fetchone()
```

Run: `uv run pytest tests/test_data.py -q` — Expected: FAIL, module not found.

- [ ] **Step 2: Implement `src/jevviz/data.py`**

```python
"""Seeded synthetic retailer with planted patterns and column-type traps."""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb

REGIONS = ["EMEA", "APAC", "LATAM", "NA", "ANZ"]
CHANNELS = ["web", "store", "partner"]
SEGMENTS = ["consumer", "smb", "enterprise"]
COUNTRIES = ["NL", "DE", "US", "BR", "AU", "JP", "GB", "FR"]
CATEGORIES = {"Electronics": (400, 0.04), "Home": (120, 0.22), "Garden": (80, 0.25), "Toys": (35, 0.30), "Books": (18, 0.35)}
START, DAYS = date(2024, 1, 1), 730


def generate(path: Path | str, seed: int = 7, n_orders: int = 50_000) -> None:
    rng = random.Random(seed)
    path = Path(path)
    path.unlink(missing_ok=True)

    products = []
    for pid in range(1, 201):
        cat = rng.choice(list(CATEGORIES))
        base, _ = CATEGORIES[cat]
        price = round(base * rng.uniform(0.5, 1.8), 2)
        quality = (price / (base * 1.8))                       # planted: price correlates with rating
        rating = max(1, min(5, round(1 + 4 * (0.7 * quality + 0.3 * rng.random()))))
        products.append((pid, cat, price, rating))

    customers = [(cid, rng.choice(SEGMENTS), rng.randint(2015, 2025), rng.randint(10000, 99999), rng.choice(COUNTRIES))
                 for cid in range(1, 5001)]

    weights = [5 if CATEGORIES[p[1]][0] >= 400 else 2 for p in products]   # planted: Electronics dominates revenue
    orders = []
    for oid in range(1, n_orders + 1):
        day = rng.randrange(DAYS)
        d = START + timedelta(days=day)
        if d.month in (11, 12) or rng.random() < 0.55:                   # planted: Nov/Dec spike
            region = rng.choice(REGIONS)
            if region == "LATAM" and rng.random() < day / DAYS * 0.85:   # planted: LATAM declines
                region = rng.choice(["EMEA", "APAC", "NA"])
            pid, cat, price, _ = rng.choices(products, weights)[0]
            qty = rng.randint(1, 4)
            revenue = round(price * qty, 2)
            margin = CATEGORIES[cat][1] + rng.uniform(-0.12, 0.08)       # can go negative
            orders.append((oid, d, region, rng.choice(CHANNELS), revenue, round(revenue * margin, 2),
                           rng.randint(1, 5000), pid))

    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE products (product_id INTEGER, category VARCHAR, price DOUBLE, rating INTEGER)")
    con.execute("CREATE TABLE customers (customer_id INTEGER, segment VARCHAR, signup_year INTEGER, zip INTEGER, country VARCHAR)")
    con.execute("CREATE TABLE orders (order_id INTEGER, order_date DATE, region VARCHAR, channel VARCHAR, "
                "revenue DOUBLE, profit DOUBLE, customer_id INTEGER, product_id INTEGER)")
    con.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", products)
    con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", customers)
    con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)", orders)
    con.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "jevviz.duckdb"
    generate(target)
    print(f"wrote {target}")
```

Run: `uv run pytest tests/test_data.py -q` — Expected: 6 passed. If a planted-pattern assertion fails, tune the generator constants (weights, decline factor `0.85`, spike probability `0.55`), not the test thresholds.

- [ ] **Step 3: Commit**

```bash
git add src/jevviz/data.py tests/test_data.py
git commit -m "feat: seeded synthetic retailer dataset with planted patterns"
```

---

### Task 4: Safe DuckDB access and result profiling

**Files:**
- Create: `src/jevviz/db.py`, `src/jevviz/profile.py`
- Test: `tests/test_db.py`, `tests/test_profile.py`

**Interfaces:**
- Consumes: `Column`, `Profile` (Task 0); `generate` (Task 3) in tests.
- Produces (`db.py`): `open_db(path) -> duckdb.DuckDBPyConnection` (read-only, external access off); `QueryResult(columns: list[str], types: list[str], rows: list[tuple], row_count: int, truncated: bool)`; `run_query(con, sql: str, row_cap: int = 5000) -> QueryResult`; `QueryError(Exception)`.
- Produces (`profile.py`): `profile(result: QueryResult) -> Profile`.

- [ ] **Step 1: Write the failing tests**

`tests/test_db.py`:

```python
import pytest
from jevviz.data import generate
from jevviz.db import QueryError, open_db, run_query


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    path = tmp_path_factory.mktemp("d") / "t.duckdb"
    generate(path, n_orders=8_000)
    return open_db(path)


def test_runs_and_caps_rows(con):
    r = run_query(con, "SELECT order_id, revenue FROM orders", row_cap=100)
    assert r.columns == ["order_id", "revenue"] and len(r.rows) == 100
    assert r.truncated is True and r.row_count > 100


def test_writes_are_rejected(con):
    with pytest.raises(QueryError):
        run_query(con, "DELETE FROM orders")


def test_external_access_is_blocked(con):
    with pytest.raises(QueryError):
        run_query(con, "SELECT * FROM read_csv('/etc/passwd')")


def test_sql_error_is_wrapped(con):
    with pytest.raises(QueryError):
        run_query(con, "SELEKT 1")
```

`tests/test_profile.py`:

```python
from datetime import date
from jevviz.db import QueryResult
from jevviz.profile import profile


def result(columns, types, rows):
    return QueryResult(columns, types, rows, len(rows), False)


def test_kinds_and_stats():
    rows = [(date(2024, m, 1), "EMEA" if m % 2 else "APAC", float(m * 10)) for m in range(1, 13)]
    p = profile(result(["month", "region", "revenue"], ["DATE", "VARCHAR", "DOUBLE"], rows))
    month, region, revenue = p.columns
    assert month.kind == ("temporal",) and month.evenly_spaced is False  # months differ in length
    assert region.kind == ("nominal",) and region.distinct == 2 and region.samples == ("APAC", "EMEA")
    assert revenue.kind == ("quantitative",) and revenue.min == 10.0 and revenue.max == 120.0
    assert p.row_count == 12 and [c.position for c in p.columns] == [0, 1, 2]


def test_integer_year_is_temporal():
    p = profile(result(["signup_year", "n"], ["INTEGER", "BIGINT"], [(y, y * 3) for y in range(2015, 2026)]))
    assert p.columns[0].kind == ("temporal",)


def test_small_integer_domain_is_dual_tagged():
    p = profile(result(["rating"], ["INTEGER"], [(r,) for r in (1, 2, 3, 4, 5, 5, 4)]))
    assert p.columns[0].kind == ("nominal", "quantitative")


def test_date_strings_are_temporal_and_nulls_counted():
    p = profile(result(["d"], ["VARCHAR"], [("2024-01-01",), ("2024-02-01",), (None,), ("2024-03-01",)]))
    assert p.columns[0].kind == ("temporal",) and p.columns[0].null_share == 0.25


def test_profile_is_deterministic():
    rows = [("b", 2.0), ("a", 1.0), ("c", 3.0)]
    r = result(["k", "v"], ["VARCHAR", "DOUBLE"], rows)
    assert profile(r).hash() == profile(r).hash()
```

Run: `uv run pytest tests/test_db.py tests/test_profile.py -q` — Expected: FAIL, modules not found.

- [ ] **Step 2: Implement `src/jevviz/db.py`**

```python
"""Read-only, sandboxed DuckDB access."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb


class QueryError(Exception):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    types: list[str]
    rows: list[tuple]
    row_count: int
    truncated: bool


def open_db(path: Path | str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path), read_only=True, config={"enable_external_access": "false"})
    con.execute("SET lock_configuration = true")
    return con


def run_query(con: duckdb.DuckDBPyConnection, sql: str, row_cap: int = 5000) -> QueryResult:
    try:
        cur = con.cursor()
        cur.execute(sql)
        if cur.description is None:
            raise QueryError("statement returned no result set")
        columns = [d[0] for d in cur.description]
        types = [str(d[1]) for d in cur.description]
        rows = cur.fetchmany(row_cap + 1)
        truncated = len(rows) > row_cap
        rows = rows[:row_cap]
        row_count = len(rows)
        if truncated:
            row_count = con.cursor().execute(f"SELECT count(*) FROM ({sql.rstrip().rstrip(';')})").fetchone()[0]
        return QueryResult(columns, types, rows, row_count, truncated)
    except duckdb.Error as exc:
        raise QueryError(str(exc)) from exc
```

- [ ] **Step 3: Implement `src/jevviz/profile.py`**

```python
"""Deterministic column profiling. All numeric judgment lives here, never in Jev."""

from __future__ import annotations

from datetime import date, datetime

from jevviz.db import QueryResult
from jevviz.types import Column, Profile

_NUMERIC = ("INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "REAL")
_TEMPORAL = ("DATE", "TIMESTAMP")
_BOOL_STR = ("VARCHAR", "BOOLEAN")


def _parses_as_date(v: object) -> bool:
    if isinstance(v, (date, datetime)):
        return True
    if isinstance(v, int):
        return 1900 <= v <= 2100
    if isinstance(v, str):
        try:
            datetime.fromisoformat(v)
        except ValueError:
            return False
        return True
    return False


def _kind(type_name: str, values: list, distinct: int) -> tuple[str, ...]:
    t = type_name.upper()
    if any(t.startswith(x) for x in _TEMPORAL):
        return ("temporal",)
    is_numeric = any(x in t for x in _NUMERIC)
    is_int_like = is_numeric and all(isinstance(v, int) or float(v).is_integer() for v in values)
    if values and (not is_numeric or is_int_like):
        if sum(_parses_as_date(int(v) if is_int_like else v) for v in values) / len(values) >= 0.95:
            return ("temporal",)
    if is_numeric:
        return ("nominal", "quantitative") if is_int_like and distinct <= 12 else ("quantitative",)
    return ("nominal",)


def _evenly_spaced(sorted_vals: list) -> bool:
    if len(sorted_vals) < 3:
        return False
    try:
        gaps = {sorted_vals[i + 1] - sorted_vals[i] for i in range(len(sorted_vals) - 1)}
    except TypeError:
        return False
    return len(gaps) == 1


def profile(result: QueryResult) -> Profile:
    cols = []
    n = len(result.rows)
    for pos, (name, type_name) in enumerate(zip(result.columns, result.types)):
        raw = [row[pos] for row in result.rows]
        values = [v for v in raw if v is not None]
        uniq = sorted(set(values), key=lambda v: (str(type(v)), v))
        kind = _kind(type_name, values, len(uniq))
        ordered = kind != ("nominal",) and bool(uniq)
        cols.append(Column(
            name=name, kind=kind, distinct=len(uniq),
            null_share=round((n - len(values)) / n, 4) if n else 0.0,
            min=uniq[0] if ordered else None, max=uniq[-1] if ordered else None,
            samples=tuple(uniq[:3]), evenly_spaced=_evenly_spaced(uniq) if ordered else False, position=pos,
        ))
    return Profile(columns=tuple(cols), row_count=result.row_count)
```

Run: `uv run pytest tests/test_db.py tests/test_profile.py -q && uv run ruff check` — Expected: 9 passed, lint clean.

- [ ] **Step 4: Commit**

```bash
git add src/jevviz/db.py src/jevviz/profile.py tests/test_db.py tests/test_profile.py
git commit -m "feat: sandboxed DuckDB access and deterministic result profiling"
```

---

### Task 5: Rule registry, titles, and the basic rules

**Files:**
- Create: `src/jevviz/rules/__init__.py`, `src/jevviz/rules/titles.py`, `src/jevviz/rules/basic.py`
- Test: `tests/test_rules_basic.py`, `tests/helpers.py`

**Interfaces:**
- Consumes: `Column`, `Profile`, `Candidate` (Task 0).
- Produces (`rules/__init__.py`): `rule(fn)` decorator registering `fn(profile: Profile) -> list[Candidate]`; `RULES: list`; `enumerate_candidates(profile: Profile, cap: int = 24, per_rule: int = 4) -> tuple[list[Candidate], int]` returning `(candidates_with_final_ids, total_before_cap)`. Rules emit `id=""`; `enumerate_candidates` assigns `c00`, `c01`, ….
- Produces (`rules/titles.py`): `humanise(name: str) -> str`; `vl(mark, encoding: dict, **extra) -> dict` building a Vega-Lite spec with `data: {"name": "rows"}`.
- Produces (`tests/helpers.py`): `make_profile(**cols) -> Profile` used by all later rule tests.

- [ ] **Step 1: Write the test helper and failing tests**

`tests/helpers.py`:

```python
from jevviz.types import Column, Profile

_KINDS = {"t": ("temporal",), "q": ("quantitative",), "n": ("nominal",), "nq": ("nominal", "quantitative")}


def make_profile(row_count=100, **cols) -> Profile:
    """make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 500.0))"""
    out = []
    for pos, (name, spec) in enumerate(cols.items()):
        kind, distinct, *rng = spec
        lo, hi = (rng + [None, None])[:2]
        out.append(Column(name, _KINDS[kind], distinct, 0.0, lo, hi, (), False, pos))
    return Profile(tuple(out), row_count)
```

`tests/test_rules_basic.py`:

```python
from helpers import make_profile
from jevviz.rules import enumerate_candidates
from jevviz.rules.titles import humanise


def kinds(profile):
    return [c.kind for c in enumerate_candidates(profile)[0]]


def test_humanise_strips_aggregates():
    assert humanise("sum_revenue") == "Revenue"
    assert humanise("avg(order_value)") == "Order Value"
    assert humanise("region") == "Region"


def test_time_series_with_breakdown():
    ks = kinds(make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 500.0)))
    assert "line" in ks and "multi_line" in ks and "bar" in ks and ks[-1] == "table"


def test_multi_line_blocked_by_high_cardinality():
    assert "multi_line" not in kinds(make_profile(month=("t", 24), sku=("n", 40), revenue=("q", 90, 0.0, 9.0)))


def test_pie_needs_few_nonnegative_slices():
    assert "pie" in kinds(make_profile(row_count=4, channel=("n", 4), revenue=("q", 4, 10.0, 90.0)))
    assert "pie" not in kinds(make_profile(row_count=4, channel=("n", 4), profit=("q", 4, -5.0, 90.0)))
    assert "pie" not in kinds(make_profile(row_count=9, channel=("n", 9), revenue=("q", 9, 1.0, 9.0)))


def test_bar_blocked_above_30_and_horizontal_above_8():
    assert "bar" not in kinds(make_profile(sku=("n", 31), revenue=("q", 31, 0.0, 9.0)))
    cands, _ = enumerate_candidates(make_profile(row_count=12, country=("n", 12), revenue=("q", 12, 0.0, 9.0)))
    bar = next(c for c in cands if c.kind == "bar")
    assert bar.vega["encoding"]["y"]["field"] == "country"


def test_kpi_only_for_single_row():
    assert "kpi" in kinds(make_profile(row_count=1, total=("q", 1, 5.0, 5.0)))
    assert "kpi" not in kinds(make_profile(row_count=2, total=("q", 2, 5.0, 6.0)))


def test_ids_titles_descriptions_and_data_binding():
    cands, total = enumerate_candidates(make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 9.0)))
    assert [c.id for c in cands] == [f"c{i:02d}" for i in range(len(cands))] and total == len(cands)
    ml = next(c for c in cands if c.kind == "multi_line")
    assert ml.title == "Revenue over Month by Region"
    assert "`revenue`" in ml.description and "over time" in ml.description
    assert ml.measures == ("revenue",) and set(ml.columns) == {"month", "region", "revenue"}
    assert all(c.vega.get("data") == {"name": "rows"} for c in cands if c.kind not in ("table", "kpi"))


def test_cap_and_per_rule_limit():
    wide = make_profile(**{f"d{i}": ("n", 5) for i in range(4)}, **{f"m{i}": ("q", 50, 0.0, 9.0) for i in range(5)})
    cands, total = enumerate_candidates(wide)
    assert total > len(cands)
    assert sum(c.kind not in ("table", "kpi") for c in cands) <= 24
    assert sum(c.kind == "bar" for c in cands) <= 4
    assert next(c for c in cands if c.kind == "bar").columns == ("d0", "m0")   # SELECT order wins
```

Add to `pyproject.toml` under `[tool.pytest.ini_options]`: `pythonpath = ["tests"]`.
Run: `uv run pytest tests/test_rules_basic.py -q` — Expected: FAIL, `jevviz.rules` not found.

- [ ] **Step 2: Implement `src/jevviz/rules/titles.py`**

```python
"""Templated titles and Vega-Lite helpers. Jev never writes text; these do."""

from __future__ import annotations

import re

_AGG = re.compile(r"^(sum|avg|mean|count|min|max|total|median)[_(\s]+", re.I)


def humanise(name: str) -> str:
    n = _AGG.sub("", name.strip()).strip("()\"` ")
    return re.sub(r"[_\s]+", " ", n).title() or name


def vl(mark: str | dict, encoding: dict, **extra) -> dict:
    return {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "data": {"name": "rows"},
            "mark": mark, "encoding": encoding, "width": "container", "height": 280, **extra}


def enc(field: str, type_: str, **kw) -> dict:
    return {"field": field, "type": type_, "title": humanise(field), **kw}
```

- [ ] **Step 3: Implement `src/jevviz/rules/__init__.py`**

```python
"""Rule registry and capped, deterministic candidate enumeration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from jevviz.types import Candidate, Profile

Rule = Callable[[Profile], list[Candidate]]
RULES: list[Rule] = []
_UNCAPPED = ("table", "kpi")


def rule(fn: Rule) -> Rule:
    RULES.append(fn)
    return fn


def _prerank(profile: Profile, c: Candidate) -> tuple:
    cols = [profile.get(n) for n in c.columns]
    return (sum(col.position for col in cols), sum(col.null_share for col in cols))


def enumerate_candidates(profile: Profile, cap: int = 24, per_rule: int = 4) -> tuple[list[Candidate], int]:
    capped: list[Candidate] = []
    uncapped: list[Candidate] = []
    total = 0
    for fn in RULES:
        found = sorted(fn(profile), key=lambda c: _prerank(profile, c))
        total += len(found)
        for c in found[:per_rule]:
            (uncapped if c.kind in _UNCAPPED else capped).append(c)
    capped = sorted(capped, key=lambda c: _prerank(profile, c))[:cap]
    ordered = [c for c in uncapped if c.kind == "kpi"] + capped + [c for c in uncapped if c.kind == "table"]
    return [replace(c, id=f"c{i:02d}") for i, c in enumerate(ordered)], total


from jevviz.rules import advanced, basic  # noqa: E402,F401  (import for registration side effect)
```

For this task create `src/jevviz/rules/advanced.py` containing only `"""Advanced rules (Task 6)."""` so the import resolves.

- [ ] **Step 4: Implement `src/jevviz/rules/basic.py`**

```python
"""table, kpi, bar, pie, line, multi_line."""

from __future__ import annotations

from itertools import product

from jevviz.rules import rule
from jevviz.rules.titles import enc, humanise, vl
from jevviz.types import Candidate, Profile


def _c(kind, columns, measures, title, description, vega) -> Candidate:
    return Candidate("", kind, tuple(columns), tuple(measures), title, description, vega)


@rule
def table(p: Profile) -> list[Candidate]:
    names = [c.name for c in p.columns]
    return [_c("table", names, (), "Result table",
               "Plain table of every row and column in the result. Shows exact values without revealing any pattern.",
               {"columns": names})]


@rule
def kpi(p: Profile) -> list[Candidate]:
    qs = p.by_kind("quantitative")
    if p.row_count != 1 or not 1 <= len(qs) <= 4:
        return []
    return [_c("kpi", [q.name], [q.name], humanise(q.name),
               f"Single headline number for `{q.name}`. Shows one total value with no breakdown.",
               {"field": q.name}) for q in qs]


@rule
def bar(p: Profile) -> list[Candidate]:
    out = []
    for n, q in product(p.by_kind("nominal"), p.by_kind("quantitative")):
        if n.name == q.name or n.distinct > 30:
            continue
        cat, val = enc(n.name, "nominal", sort="-x" if n.distinct > 8 else "-y"), enc(q.name, "quantitative")
        encoding = {"y": cat, "x": val} if n.distinct > 8 else {"x": cat, "y": val}
        out.append(_c("bar", [n.name, q.name], [q.name], f"{humanise(q.name)} by {humanise(n.name)}",
                      f"Bar chart of `{q.name}` for each `{n.name}`, sorted from largest to smallest. "
                      f"Shows which {humanise(n.name).lower()} values are highest and lowest and lets them be compared.",
                      vl("bar", encoding)))
    return out


@rule
def pie(p: Profile) -> list[Candidate]:
    out = []
    for n, q in product(p.by_kind("nominal"), p.by_kind("quantitative")):
        if n.name == q.name or n.distinct > 6 or q.min is None or q.min < 0:
            continue
        out.append(_c("pie", [n.name, q.name], [q.name], f"Share of {humanise(q.name)} by {humanise(n.name)}",
                      f"Pie chart of `{q.name}` split by `{n.name}`. "
                      f"Shows each {humanise(n.name).lower()}'s share of the whole, as a proportion.",
                      vl({"type": "arc", "innerRadius": 50},
                         {"theta": enc(q.name, "quantitative"), "color": enc(n.name, "nominal")})))
    return out


@rule
def line(p: Profile) -> list[Candidate]:
    out = []
    for t, q in product(p.by_kind("temporal"), p.by_kind("quantitative")):
        if t.name == q.name or t.distinct < 3:
            continue
        out.append(_c("line", [t.name, q.name], [q.name], f"{humanise(q.name)} over {humanise(t.name)}",
                      f"Line chart of `{q.name}` over `{t.name}`. "
                      "Shows how the overall value changes over time, including trends and seasonal peaks.",
                      vl({"type": "line", "point": True},
                         {"x": enc(t.name, "temporal"), "y": enc(q.name, "quantitative", aggregate="sum")})))
    return out


@rule
def multi_line(p: Profile) -> list[Candidate]:
    out = []
    for t, q, n in product(p.by_kind("temporal"), p.by_kind("quantitative"), p.by_kind("nominal")):
        if len({t.name, q.name, n.name}) < 3 or t.distinct < 3 or n.distinct > 8:
            continue
        out.append(_c("multi_line", [t.name, n.name, q.name], [q.name],
                      f"{humanise(q.name)} over {humanise(t.name)} by {humanise(n.name)}",
                      f"Multi-series line chart of `{q.name}` over `{t.name}`, one line per `{n.name}`. "
                      f"Shows how each {humanise(n.name).lower()}'s value changes over time and lets them be compared.",
                      vl("line", {"x": enc(t.name, "temporal"), "y": enc(q.name, "quantitative"),
                                  "color": enc(n.name, "nominal")})))
    return out
```

Run: `uv run pytest tests/test_rules_basic.py -q` — Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/jevviz/rules tests/helpers.py tests/test_rules_basic.py
git commit -m "feat: rule registry, templated titles and basic chart rules"
```

---

### Task 6: Advanced rules and Vega-Lite schema validation

**Files:**
- Modify: `src/jevviz/rules/advanced.py` (replace the one-line stub)
- Create: `tests/fixtures/vega-lite-v5.json` (downloaded schema)
- Test: `tests/test_rules_advanced.py`, `tests/test_vega_valid.py`

**Interfaces:**
- Consumes: `rule`, `enc`, `vl`, `humanise`, `Candidate`, `Profile`, `make_profile`.
- Produces: rules `grouped_bar`, `stacked_bar`, `scatter`, `histogram`, `heatmap` registered in `RULES`.

- [ ] **Step 1: Write the failing tests**

`tests/test_rules_advanced.py`:

```python
from helpers import make_profile
from jevviz.rules import enumerate_candidates


def kinds(profile):
    return {c.kind for c in enumerate_candidates(profile)[0]}


def test_two_dimensions_and_a_measure():
    ks = kinds(make_profile(row_count=15, region=("n", 5), channel=("n", 3), revenue=("q", 15, 0.0, 9.0)))
    assert {"grouped_bar", "stacked_bar", "heatmap"} <= ks


def test_grouping_blocked_when_inner_dimension_too_wide():
    ks = kinds(make_profile(row_count=90, region=("n", 9), country=("n", 10), revenue=("q", 90, 0.0, 9.0)))
    assert "grouped_bar" not in ks and "stacked_bar" not in ks and "heatmap" in ks


def test_scatter_needs_ten_rows_and_two_measures():
    assert "scatter" in kinds(make_profile(row_count=200, price=("q", 150, 1.0, 9.0), rating=("q", 40, 1.0, 5.0)))
    assert "scatter" not in kinds(make_profile(row_count=6, price=("q", 6, 1.0, 9.0), rating=("q", 6, 1.0, 5.0)))


def test_histogram_needs_volume_and_spread():
    assert "histogram" in kinds(make_profile(row_count=500, revenue=("q", 400, 0.0, 9.0)))
    assert "histogram" not in kinds(make_profile(row_count=500, rating=("nq", 5, 1, 5)))
    assert "histogram" not in kinds(make_profile(row_count=20, revenue=("q", 20, 0.0, 9.0)))
```

`tests/test_vega_valid.py`:

```python
import json
from pathlib import Path

import jsonschema
from helpers import make_profile
from jevviz.rules import enumerate_candidates

SCHEMA = json.loads((Path(__file__).parent / "fixtures" / "vega-lite-v5.json").read_text())
PROFILES = [
    make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 9.0)),
    make_profile(row_count=15, region=("n", 5), channel=("n", 3), revenue=("q", 15, 0.0, 9.0)),
    make_profile(row_count=200, price=("q", 150, 1.0, 9.0), rating=("nq", 5, 1, 5), category=("n", 5)),
    make_profile(row_count=500, revenue=("q", 400, 0.0, 9.0)),
]


def test_every_chart_spec_is_valid_vega_lite():
    validator = jsonschema.Draft7Validator(SCHEMA)
    checked = 0
    for p in PROFILES:
        for c in enumerate_candidates(p)[0]:
            if c.kind in ("table", "kpi"):
                continue
            errors = list(validator.iter_errors(c.vega))
            assert not errors, f"{c.kind}: {errors[0].message}"
            checked += 1
    assert checked >= 12
```

- [ ] **Step 2: Fetch the schema fixture**

```bash
mkdir -p tests/fixtures && curl -fsSL https://vega.github.io/schema/vega-lite/v5.json -o tests/fixtures/vega-lite-v5.json
```

Run: `uv run pytest tests/test_rules_advanced.py tests/test_vega_valid.py -q` — Expected: advanced tests FAIL (kinds missing); vega test passes or fails on `checked >= 12`.

- [ ] **Step 3: Implement `src/jevviz/rules/advanced.py`**

```python
"""grouped_bar, stacked_bar, scatter, histogram, heatmap."""

from __future__ import annotations

from itertools import combinations, permutations, product

from jevviz.rules import rule
from jevviz.rules.titles import enc, humanise, vl
from jevviz.types import Candidate, Profile


def _c(kind, columns, measures, title, description, vega) -> Candidate:
    return Candidate("", kind, tuple(columns), tuple(measures), title, description, vega)


def _two_dims(p: Profile):
    for (a, b), q in product(permutations(p.by_kind("nominal"), 2), p.by_kind("quantitative")):
        if len({a.name, b.name, q.name}) == 3:
            yield a, b, q


@rule
def grouped_bar(p: Profile) -> list[Candidate]:
    return [_c("grouped_bar", [a.name, b.name, q.name], [q.name],
               f"{humanise(q.name)} by {humanise(a.name)} and {humanise(b.name)}",
               f"Grouped bar chart of `{q.name}` for each `{a.name}`, with side-by-side bars per `{b.name}`. "
               f"Shows how {humanise(b.name).lower()} values compare within each {humanise(a.name).lower()}.",
               vl("bar", {"x": enc(a.name, "nominal"), "xOffset": {"field": b.name, "type": "nominal"},
                          "y": enc(q.name, "quantitative"), "color": enc(b.name, "nominal")}))
            for a, b, q in _two_dims(p) if a.distinct <= 30 and b.distinct <= 6]


@rule
def stacked_bar(p: Profile) -> list[Candidate]:
    return [_c("stacked_bar", [a.name, b.name, q.name], [q.name],
               f"{humanise(q.name)} by {humanise(a.name)}, stacked by {humanise(b.name)}",
               f"Stacked bar chart of `{q.name}` for each `{a.name}`, stacked by `{b.name}`. "
               f"Shows each {humanise(a.name).lower()}'s total and how much each {humanise(b.name).lower()} contributes to it.",
               vl("bar", {"x": enc(a.name, "nominal"), "y": enc(q.name, "quantitative", aggregate="sum"),
                          "color": enc(b.name, "nominal")}))
            for a, b, q in _two_dims(p) if a.distinct <= 30 and b.distinct <= 6 and (q.min is None or q.min >= 0)]


@rule
def heatmap(p: Profile) -> list[Candidate]:
    seen, out = set(), []
    for a, b, q in _two_dims(p):
        key = (frozenset((a.name, b.name)), q.name)
        if key in seen or a.distinct > 30 or b.distinct > 30:
            continue
        seen.add(key)
        out.append(_c("heatmap", [a.name, b.name, q.name], [q.name],
                      f"{humanise(q.name)} by {humanise(a.name)} and {humanise(b.name)}",
                      f"Heatmap of `{q.name}` with `{a.name}` across and `{b.name}` down, darker cells meaning higher values. "
                      "Shows which combinations of the two are strongest and weakest.",
                      vl("rect", {"x": enc(a.name, "nominal"), "y": enc(b.name, "nominal"),
                                  "color": enc(q.name, "quantitative", aggregate="sum")})))
    return out


@rule
def scatter(p: Profile) -> list[Candidate]:
    if p.row_count < 10:
        return []
    out = []
    for x, y in combinations(p.by_kind("quantitative"), 2):
        out.append(_c("scatter", [x.name, y.name], [x.name, y.name], f"{humanise(y.name)} against {humanise(x.name)}",
                      f"Scatter plot of `{y.name}` against `{x.name}`, one point per row. "
                      "Shows the relationship or correlation between the two quantities and any outliers.",
                      vl({"type": "point", "filled": True, "opacity": 0.6},
                         {"x": enc(x.name, "quantitative"), "y": enc(y.name, "quantitative")})))
    return out


@rule
def histogram(p: Profile) -> list[Candidate]:
    if p.row_count < 30:
        return []
    return [_c("histogram", [q.name], [q.name], f"Distribution of {humanise(q.name)}",
               f"Histogram of `{q.name}`, counting rows in each value range. "
               "Shows the distribution and spread of values: where most fall and how long the tails are.",
               vl("bar", {"x": enc(q.name, "quantitative", bin={"maxbins": 30}),
                          "y": {"aggregate": "count", "type": "quantitative", "title": "Rows"}}))
            for q in p.by_kind("quantitative") if q.distinct > 12]
```

Run: `uv run pytest -q && uv run ruff check` — Expected: all pass (including Task 5's tests), lint clean. If `test_vega_valid` reports a schema error, fix the offending encoding in the rule — never loosen the test.

- [ ] **Step 4: Commit**

```bash
git add src/jevviz/rules/advanced.py tests/test_rules_advanced.py tests/test_vega_valid.py tests/fixtures
git commit -m "feat: advanced chart rules, all specs validated against Vega-Lite schema"
```

---

### Task 7: Jev question builder

**Files:**
- Create: `src/jevviz/viz_questions.py`
- Test: `tests/test_viz_questions.py`

**Interfaces:**
- Consumes: `Question`, `Profile`, `Candidate`; `BARE_INTENT` from `parse.py`.
- Produces: `LEVELS: tuple[str, str, str, str]`; `state_for(sql: str, profile: Profile) -> dict`; `build_questions(profile, candidates: list[Candidate], intents: list[str]) -> dict[str, Question]` with ids `i{n}.{cid}` (Score) and `id.{column}` (Noul); `effective_intents(intents: list[str]) -> list[str]` (maps `[]` to `[BARE_INTENT]`).

- [ ] **Step 1: Write the failing tests**

`tests/test_viz_questions.py`:

```python
from helpers import make_profile
from jevviz.parse import BARE_INTENT
from jevviz.rules import enumerate_candidates
from jevviz.viz_questions import LEVELS, build_questions, effective_intents, state_for

P = make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 9.0), customer_id=("q", 80, 1, 5000))


def test_one_score_per_intent_candidate_pair_excluding_table():
    cands, _ = enumerate_candidates(P)
    qs = build_questions(P, cands, ["trend by region", "top regions"])
    scored = [c for c in cands if c.kind != "table"]
    assert sum(k.startswith("i0.") for k in qs) == len(scored)
    assert sum(k.startswith("i1.") for k in qs) == len(scored)
    q = qs[f"i0.{scored[0].id}"]
    assert q.kind == "score" and q.levels == LEVELS
    assert '"trend by region"' in q.instructions and scored[0].description in q.instructions


def test_noul_only_for_numeric_looking_columns_used_as_measures():
    cands, _ = enumerate_candidates(P)
    qs = build_questions(P, cands, ["x"])
    assert "id.customer_id" in qs and "id.revenue" in qs
    assert "id.region" not in qs and "id.month" not in qs
    assert "`customer_id`" in qs["id.customer_id"].instructions


def test_state_is_compact_and_has_no_rows():
    s = state_for("SELECT 1", P)
    assert s["sql"] == "SELECT 1" and s["row_count"] == 100
    assert s["columns"]["region"] == {"kind": "nominal", "distinct": 5, "samples": []}
    assert "rows" not in s


def test_bare_clause_uses_pseudo_intent():
    assert effective_intents([]) == [BARE_INTENT] and effective_intents(["a"]) == ["a"]
```

Run: `uv run pytest tests/test_viz_questions.py -q` — Expected: FAIL, module not found.

- [ ] **Step 2: Implement `src/jevviz/viz_questions.py`**

```python
"""Build the single batched Jev request. The candidate lives in the question, never in the state."""

from __future__ import annotations

from jevviz.parse import BARE_INTENT
from jevviz.types import Candidate, Profile, Question

LEVELS = (
    "The panel shows columns that have nothing to do with what was asked.",
    "The panel uses relevant columns, but its form hides what was asked, such as totals when the question is about change over time.",
    "The panel partly answers the question: right measure, but missing a breakdown or comparison the question mentions.",
    "The panel directly answers the question: right measure, right breakdown, in a form that makes the asked pattern visible.",
)


def effective_intents(intents: list[str]) -> list[str]:
    return intents or [BARE_INTENT]


def state_for(sql: str, profile: Profile) -> dict:
    columns = {}
    for c in profile.columns:
        entry: dict = {"kind": "/".join(c.kind), "distinct": c.distinct, "samples": [str(s) for s in c.samples]}
        if c.min is not None:
            entry["range"] = f"{c.min} → {c.max}"
        columns[c.name] = entry
    return {"sql": sql, "columns": columns, "row_count": profile.row_count}


def build_questions(profile: Profile, candidates: list[Candidate], intents: list[str]) -> dict[str, Question]:
    qs: dict[str, Question] = {}
    for n, intent in enumerate(effective_intents(intents)):
        for c in candidates:
            if c.kind == "table":
                continue
            qs[f"i{n}.{c.id}"] = Question(
                "score",
                f'The analyst asked: "{intent}". Proposed panel: "{c.description}" '
                "How well would this panel answer what the analyst asked?",
                LEVELS,
            )
    measures = {m for c in candidates for m in c.measures}
    for name in sorted(measures):
        qs[f"id.{name}"] = Question(
            "noul",
            f"Is `{name}` an identifier, code or label rather than a quantity that is meaningful to sum or average?",
        )
    return qs
```

Run: `uv run pytest tests/test_viz_questions.py -q` — Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add src/jevviz/viz_questions.py tests/test_viz_questions.py
git commit -m "feat: build batched Jev relevance and identifier questions"
```

---

### Task 8: Ranking — `rank_key`, bands, alternates, collisions

`rank_key()` and the thresholds are the **owner-written** piece (learning mode). The implementer writes everything else and a default `rank_key` that satisfies the tests; the owner then reviews/rewrites those ~8 lines.

**Files:**
- Create: `src/jevviz/rank.py`
- Test: `tests/test_rank.py`

**Interfaces:**
- Consumes: `Answer`, `Candidate`.
- Produces: `STRONG = 0.6`, `WEAK = 0.3`, `ID_NOUL = 0.5`; `rank_key(answer: Answer) -> float`; `match_band(p: float) -> Literal["strong","weak","none"]`; `Ranked(candidate: Candidate, p: float)`; `PanelChoice(intent: str, chosen: Ranked, alternates: list[Ranked], match: str)`; `rank_panels(candidates, intents: list[str], answers: dict[str, Answer]) -> list[PanelChoice]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_rank.py`:

```python
from jevviz.rank import match_band, rank_key, rank_panels
from jevviz.types import Answer, Candidate


def cand(cid, kind, measures=("revenue",)):
    return Candidate(cid, kind, ("region", *measures), measures, f"T {cid}", f"D {cid}", {})


def score(p_hi, conf=0.5):
    return Answer("score", probabilities={0: (1 - p_hi) / 2, 1: (1 - p_hi) / 2, 2: p_hi / 2, 3: p_hi / 2}, confidence=conf)


TABLE = Candidate("c99", "table", ("region",), (), "Result table", "table", {})


def test_rank_key_is_mass_on_top_two_levels():
    assert abs(rank_key(score(0.8)) - 0.8) < 1e-9


def test_bands():
    assert (match_band(0.6), match_band(0.59), match_band(0.3), match_band(0.29)) == ("strong", "weak", "weak", "none")


def test_picks_best_and_diverse_alternates():
    cs = [cand("c00", "bar"), cand("c01", "bar"), cand("c02", "line"), cand("c03", "pie"), cand("c04", "heatmap"), TABLE]
    ans = {"i0.c00": score(0.9), "i0.c01": score(0.8), "i0.c02": score(0.7), "i0.c03": score(0.5), "i0.c04": score(0.4)}
    [panel] = rank_panels(cs, ["q"], ans)
    assert panel.chosen.candidate.id == "c00" and panel.match == "strong"
    assert [a.candidate.id for a in panel.alternates] == ["c02", "c03", "c04"]   # c01 skipped: second bar


def test_identifier_measures_are_dropped():
    cs = [cand("c00", "bar", ("customer_id",)), cand("c01", "bar"), TABLE]
    ans = {"i0.c00": score(0.95), "i0.c01": score(0.7), "id.customer_id": Answer("noul", noul=0.9),
           "id.revenue": Answer("noul", noul=0.05)}
    assert rank_panels(cs, ["q"], ans)[0].chosen.candidate.id == "c01"


def test_no_strong_match_falls_back_to_table():
    cs = [cand("c00", "bar"), TABLE]
    [panel] = rank_panels(cs, ["q"], {"i0.c00": score(0.1)})
    assert panel.chosen.candidate.kind == "table" and panel.match == "none"
    assert [a.candidate.id for a in panel.alternates] == ["c00"]


def test_dashboard_collision_takes_next_best():
    cs = [cand("c00", "bar"), cand("c01", "line"), TABLE]
    ans = {"i0.c00": score(0.9), "i0.c01": score(0.5), "i1.c00": score(0.8), "i1.c01": score(0.7)}
    panels = rank_panels(cs, ["a", "b"], ans)
    assert [p.chosen.candidate.id for p in panels] == ["c00", "c01"]


def test_missing_answers_fall_back_to_table():
    [panel] = rank_panels([cand("c00", "bar"), TABLE], ["q"], {})
    assert panel.chosen.candidate.kind == "table" and panel.match == "none"
```

Run: `uv run pytest tests/test_rank.py -q` — Expected: FAIL, module not found.

- [ ] **Step 2: Implement `src/jevviz/rank.py`**

```python
"""Turn Jev answers into chosen panels. Policy is explicit and isolated here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jevviz.types import Answer, Candidate

STRONG = 0.6     # placeholder — tune on the golden set (Task 10)
WEAK = 0.3       # placeholder — tune on the golden set (Task 10)
ID_NOUL = 0.5    # placeholder — tune on the golden set (Task 10)


def rank_key(answer: Answer) -> float:
    """OWNER-WRITTEN. Default: probability mass on levels >= 2 ("answers it").

    The interpolated score is deliberately unused (docs: numerically weak).
    Open question for the owner: should low `answer.confidence` discount this?
    """
    probs = answer.probabilities or {}
    return sum(p for level, p in probs.items() if level >= 2)


def match_band(p: float) -> Literal["strong", "weak", "none"]:
    return "strong" if p >= STRONG else "weak" if p >= WEAK else "none"


@dataclass(frozen=True)
class Ranked:
    candidate: Candidate
    p: float


@dataclass(frozen=True)
class PanelChoice:
    intent: str
    chosen: Ranked
    alternates: list[Ranked]
    match: str


def _diverse(ranked: list[Ranked], exclude_kind: str, limit: int = 3) -> list[Ranked]:
    out, seen = [], {exclude_kind}
    for r in ranked:
        if r.candidate.kind not in seen:
            out.append(r)
            seen.add(r.candidate.kind)
        if len(out) == limit:
            break
    return out


def rank_panels(candidates: list[Candidate], intents: list[str], answers: dict[str, Answer]) -> list[PanelChoice]:
    flagged = {qid[3:] for qid, a in answers.items() if qid.startswith("id.") and (a.noul or 0.0) > ID_NOUL}
    table = next(c for c in candidates if c.kind == "table")
    usable = [c for c in candidates if c.kind != "table" and not (set(c.measures) & flagged)]
    taken: set[str] = set()
    panels = []
    for n, intent in enumerate(intents):
        ranked = sorted(
            (Ranked(c, rank_key(answers[f"i{n}.{c.id}"])) for c in usable if f"i{n}.{c.id}" in answers),
            key=lambda r: (-r.p, -(answers[f"i{n}.{r.candidate.id}"].confidence or 0.0), r.candidate.id),
        )
        free = [r for r in ranked if r.candidate.id not in taken]
        if not free or match_band(free[0].p) == "none":
            panels.append(PanelChoice(intent, Ranked(table, 0.0), _diverse(free, "table"), "none"))
            continue
        best = free[0]
        taken.add(best.candidate.id)
        panels.append(PanelChoice(intent, best, _diverse(free[1:], best.candidate.kind), match_band(best.p)))
    return panels
```

Run: `uv run pytest tests/test_rank.py -q` — Expected: 7 passed.

- [ ] **Step 3: Owner checkpoint** — pause and ask the project owner to review/rewrite `rank_key()` (and decide whether confidence should discount it). Re-run the tests after their edit.

- [ ] **Step 4: Commit**

```bash
git add src/jevviz/rank.py tests/test_rank.py
git commit -m "feat: rank panels by P(level>=2) with bands, diverse alternates and collision handling"
```

---

### Task 9: Spec assembly and the `visualize()` pipeline

**Files:**
- Create: `src/jevviz/spec.py`, `src/jevviz/pipeline.py`
- Test: `tests/test_spec.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 0, 4–8; `MAX_QUESTIONS_PER_REQUEST` decision from `docs/probe-results.md` (Task 1).
- Produces (`spec.py`): `element_for(r: Ranked, intent: str, match: str) -> dict` (a `Panel` element dict with one inline child descriptor); `assemble_spec(panels: list[PanelChoice]) -> dict` returning `{"root": "grid", "elements": {...}}`; `panel_payload(panels) -> list[dict]` (the `panels[]` wire shape from spec §7).
- Produces (`pipeline.py`): `VizOutcome(spec: dict, panels: list[dict], ms: dict, input_tokens: int, usd: float, scored: str, cache: str, simulated: bool, error: str | None)`; `async visualize(sql: str, result: QueryResult, intents: list[str], backend: Backend, cache: Cache | None, max_questions: int) -> VizOutcome`.

- [ ] **Step 1: Write the failing tests**

`tests/test_spec.py`:

```python
from jevviz.rank import PanelChoice, Ranked
from jevviz.spec import assemble_spec, panel_payload
from jevviz.types import Candidate

LINE = Candidate("c01", "line", ("month", "revenue"), ("revenue",), "Revenue over Month", "d", {"mark": "line"})
KPI = Candidate("c00", "kpi", ("total",), ("total",), "Total", "d", {"field": "total"})
TABLE = Candidate("c09", "table", ("month", "revenue"), (), "Result table", "d", {"columns": ["month", "revenue"]})
ALLOWED = {"Grid", "Panel", "Chart", "Kpi", "Table"}


def test_flat_spec_uses_only_catalog_types_and_resolves_children():
    panels = [PanelChoice("trend", Ranked(LINE, 0.82), [Ranked(KPI, 0.4)], "strong"),
              PanelChoice("none", Ranked(TABLE, 0.0), [], "none")]
    spec = assemble_spec(panels)
    els = spec["elements"]
    assert spec["root"] == "grid" and els["grid"]["type"] == "Grid" and els["grid"]["props"]["columns"] == 2
    assert {e["type"] for e in els.values()} <= ALLOWED
    assert all(child in els for e in els.values() for child in e["children"])
    p0 = els[els["grid"]["children"][0]]
    assert p0["props"] == {"title": "Revenue over Month", "intent": "trend", "p": 0.82, "match": "strong", "panelIndex": 0}
    assert els[p0["children"][0]] == {"type": "Chart", "props": {"vega": {"mark": "line"}}, "children": []}


def test_single_panel_grid_is_one_column_and_payload_carries_full_alternate_elements():
    panels = [PanelChoice("trend", Ranked(LINE, 0.82), [Ranked(KPI, 0.4)], "strong")]
    assert assemble_spec(panels)["elements"]["grid"]["props"]["columns"] == 1
    [p] = panel_payload(panels)
    assert p["chosen"]["id"] == "c01" and p["match"] == "strong"
    alt = p["alternates"][0]
    assert alt["kind"] == "kpi" and alt["p"] == 0.4 and alt["element"]["type"] == "Kpi"
    assert alt["element"]["props"] == {"label": "Total", "field": "total"}
```

`tests/test_pipeline.py`:

```python
from datetime import date

from jevviz.backend import DemoBackend
from jevviz.cache import Cache
from jevviz.db import QueryResult
from jevviz.pipeline import visualize
from jevviz.types import JudgeResult

ROWS = [(date(2024, m, 1), r, float(m * (i + 1))) for m in range(1, 13) for i, r in enumerate(["EMEA", "APAC", "NA"])]
RESULT = QueryResult(["month", "region", "revenue"], ["DATE", "VARCHAR", "DOUBLE"], ROWS, len(ROWS), False)
SQL = "SELECT month, region, revenue FROM t"


async def test_demo_pipeline_picks_a_time_chart_for_a_trend_intent():
    out = await visualize(SQL, RESULT, ["how does revenue change over time per region"], DemoBackend(), None, 72)
    assert out.error is None and out.simulated is True
    assert out.panels[0]["chosen"]["kind"] in ("multi_line", "line")
    assert set(out.ms) == {"profile", "enumerate", "jev"} and out.cache == "miss"
    assert out.scored.endswith(f"of {out.scored.split(' of ')[1]}")


async def test_second_run_is_a_cache_hit_with_zero_tokens(tmp_path):
    cache = Cache(tmp_path / "c.sqlite")
    await visualize(SQL, RESULT, ["trend"], DemoBackend(), cache, 72)
    again = await visualize(SQL, RESULT, ["trend"], DemoBackend(), cache, 72)
    assert again.cache == "hit" and again.input_tokens == 0


async def test_questions_are_chunked_when_over_the_limit():
    calls = []

    class Counting(DemoBackend):
        async def judge(self, state, questions):
            calls.append(len(questions))
            return await super().judge(state, questions)

    await visualize(SQL, RESULT, ["a", "b", "c"], Counting(), None, 10)
    assert len(calls) > 1 and max(calls) <= 10


async def test_backend_failure_degrades_to_table_with_error():
    class Broken(DemoBackend):
        async def judge(self, state, questions):
            return JudgeResult(answers={}, input_tokens=0, error="RateLimitError: slow down")

    out = await visualize(SQL, RESULT, ["trend"], Broken(), None, 72)
    assert out.error == "RateLimitError: slow down"
    assert out.panels[0]["chosen"]["kind"] == "table" and out.panels[0]["match"] == "none"
```

Run: `uv run pytest tests/test_spec.py tests/test_pipeline.py -q` — Expected: FAIL, modules not found.

- [ ] **Step 2: Implement `src/jevviz/spec.py`**

```python
"""Assemble the flat json-render spec in code. Jev never writes JSON."""

from __future__ import annotations

from jevviz.rank import PanelChoice, Ranked


def _leaf(r: Ranked) -> dict:
    c = r.candidate
    if c.kind == "table":
        return {"type": "Table", "props": {"columns": c.vega["columns"], "maxRows": 200}, "children": []}
    if c.kind == "kpi":
        return {"type": "Kpi", "props": {"label": c.title, "field": c.vega["field"]}, "children": []}
    return {"type": "Chart", "props": {"vega": c.vega}, "children": []}


def _entry(r: Ranked) -> dict:
    c = r.candidate
    return {"id": c.id, "kind": c.kind, "title": c.title, "p": round(r.p, 4), "element": _leaf(r)}


def assemble_spec(panels: list[PanelChoice]) -> dict:
    elements: dict[str, dict] = {}
    children = []
    for i, p in enumerate(panels):
        elements[f"leaf-{i}"] = _leaf(p.chosen)
        elements[f"panel-{i}"] = {
            "type": "Panel",
            "props": {"title": p.chosen.candidate.title, "intent": p.intent, "p": round(p.chosen.p, 4),
                      "match": p.match, "panelIndex": i},
            "children": [f"leaf-{i}"],
        }
        children.append(f"panel-{i}")
    elements["grid"] = {"type": "Grid", "props": {"columns": 1 if len(panels) == 1 else 2}, "children": children}
    return {"root": "grid", "elements": elements}


def panel_payload(panels: list[PanelChoice]) -> list[dict]:
    return [{"intent": p.intent, "chosen": _entry(p.chosen), "alternates": [_entry(a) for a in p.alternates],
             "match": p.match} for p in panels]
```

- [ ] **Step 3: Implement `src/jevviz/pipeline.py`**

```python
"""profile -> candidates -> one batched judgment -> rank -> spec."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from jevviz.backend import Backend
from jevviz.cache import Cache
from jevviz.db import QueryResult
from jevviz.profile import profile
from jevviz.rank import rank_panels
from jevviz.rules import enumerate_candidates
from jevviz.spec import assemble_spec, panel_payload
from jevviz.types import Answer, Question
from jevviz.viz_questions import build_questions, effective_intents, state_for

PRICE_PER_MTOK_USD = 0.042


@dataclass
class VizOutcome:
    spec: dict
    panels: list[dict]
    ms: dict
    input_tokens: int
    usd: float
    scored: str
    cache: str
    simulated: bool
    error: str | None


def _chunks(qs: dict[str, Question], size: int) -> list[dict[str, Question]]:
    items = list(qs.items())
    return [dict(items[i:i + size]) for i in range(0, len(items), size)]


async def visualize(sql: str, result: QueryResult, intents: list[str], backend: Backend,
                    cache: Cache | None, max_questions: int) -> VizOutcome:
    t0 = time.perf_counter()
    prof = profile(result)
    t1 = time.perf_counter()
    candidates, total = enumerate_candidates(prof)
    t2 = time.perf_counter()

    intents = effective_intents(intents)
    questions = build_questions(prof, candidates, intents)
    state, state_hash = state_for(sql, prof), prof.hash()
    answers: dict[str, Answer] = cache.get_many(backend.name, state_hash, questions) if cache else {}
    missing = {qid: q for qid, q in questions.items() if qid not in answers}
    tokens, error = 0, None
    if missing:
        results = await asyncio.gather(*(backend.judge(state, chunk) for chunk in _chunks(missing, max_questions)))
        fresh: dict[str, Answer] = {}
        for r in results:
            fresh.update(r.answers)
            tokens += r.input_tokens
            error = error or r.error
        if cache and fresh:
            cache.put_many(backend.name, state_hash, questions, fresh)
        answers.update(fresh)
    t3 = time.perf_counter()

    panels = rank_panels(candidates, intents, answers)
    scored = sum(c.kind not in ("table",) for c in candidates)
    return VizOutcome(
        spec=assemble_spec(panels), panels=panel_payload(panels),
        ms={"profile": round((t1 - t0) * 1000, 1), "enumerate": round((t2 - t1) * 1000, 1), "jev": round((t3 - t2) * 1000, 1)},
        input_tokens=tokens, usd=round(tokens * PRICE_PER_MTOK_USD / 1_000_000, 6),
        scored=f"{scored} of {total}", cache="miss" if missing else "hit",
        simulated=backend.simulated, error=error,
    )
```

Run: `uv run pytest -q && uv run ruff check` — Expected: all pass, lint clean.

- [ ] **Step 4: Commit**

```bash
git add src/jevviz/spec.py src/jevviz/pipeline.py tests/test_spec.py tests/test_pipeline.py
git commit -m "feat: assemble flat render spec and end-to-end visualize pipeline"
```

---

### Task 10: Golden-set eval, Jev vs rules-only — GATE 2

The golden-set **intents are owner-written** (learning mode): the implementer ships the 10 seed entries below and the harness; the owner extends `golden.toml` to ~30 before the gate is judged.

**Files:**
- Create: `src/jevviz/golden.toml`, `src/jevviz/eval.py`, `docs/eval-results.md`
- Test: `tests/test_eval.py`

**Interfaces:**
- Consumes: `open_db`, `run_query`, `visualize`, `make_backend`, `enumerate_candidates`, `profile`, `generate`.
- Produces: `load_golden(path=None) -> list[GoldenCase(name, sql, intent, accept: list[str])]` where `accept` holds acceptable candidate **kinds** plus required columns as `"kind:col1+col2"`; `matches(candidate_kind, candidate_columns, accept) -> bool`; `async run_eval(db_path, backend, max_questions) -> EvalReport(top1, top3, baseline_top1, rows)`; CLI `uv run python -m jevviz.eval`.

- [ ] **Step 1: Write the failing tests**

`tests/test_eval.py`:

```python
import pytest
from jevviz.backend import DemoBackend
from jevviz.data import generate
from jevviz.eval import load_golden, matches, run_eval


def test_matches_kind_and_required_columns():
    assert matches("multi_line", ("order_month", "region", "revenue"), ["multi_line:region+revenue"])
    assert not matches("multi_line", ("order_month", "channel", "revenue"), ["multi_line:region+revenue"])
    assert matches("bar", ("region", "revenue"), ["pie", "bar"])
    assert not matches("pie", ("region", "revenue"), ["bar"])


def test_golden_set_is_well_formed():
    cases = load_golden()
    assert len(cases) >= 10 and len({c.name for c in cases}) == len(cases)
    assert all(c.sql.strip() and c.intent.strip() and c.accept for c in cases)


@pytest.mark.asyncio
async def test_eval_runs_offline_and_reports_all_metrics(tmp_path):
    db = tmp_path / "e.duckdb"
    generate(db, n_orders=6_000)
    report = await run_eval(db, DemoBackend(), 72)
    assert 0.0 <= report.baseline_top1 <= 1.0 and 0.0 <= report.top1 <= report.top3 <= 1.0
    assert len(report.rows) == len(load_golden())
```

Run: `uv run pytest tests/test_eval.py -q` — Expected: FAIL, module not found.

- [ ] **Step 2: Write `src/jevviz/golden.toml`** (seed of 10; owner extends to ~30)

```toml
[region_trend]
sql = "SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue FROM orders GROUP BY ALL"
intent = "how are regions trending"
accept = ["multi_line:region+revenue"]

[declining_region]
sql = "SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue FROM orders GROUP BY ALL"
intent = "which region is losing ground over time"
accept = ["multi_line:region+revenue"]

[seasonality]
sql = "SELECT date_trunc('month', order_date) AS order_month, sum(revenue) AS revenue FROM orders GROUP BY ALL"
intent = "is there a seasonal peak"
accept = ["line:revenue"]

[top_categories]
sql = "SELECT category, sum(revenue) AS revenue FROM orders JOIN products USING (product_id) GROUP BY ALL"
intent = "which categories bring in the most money"
accept = ["bar:category+revenue"]

[channel_share]
sql = "SELECT channel, sum(revenue) AS revenue FROM orders GROUP BY ALL"
intent = "what share of revenue comes from each channel"
accept = ["pie:channel+revenue", "bar:channel+revenue"]

[price_vs_rating]
sql = "SELECT price, rating, category FROM products"
intent = "do more expensive products get better ratings"
accept = ["scatter:price+rating"]

[order_value_distribution]
sql = "SELECT revenue FROM orders"
intent = "how are order values distributed"
accept = ["histogram:revenue"]

[region_channel_mix]
sql = "SELECT region, channel, sum(revenue) AS revenue FROM orders GROUP BY ALL"
intent = "which region and channel combinations are strongest"
accept = ["heatmap:revenue", "grouped_bar:revenue"]

[margin_problem]
sql = "SELECT category, sum(revenue) AS revenue, sum(profit) AS profit FROM orders JOIN products USING (product_id) GROUP BY ALL"
intent = "which category earns the least profit"
accept = ["bar:category+profit"]

[identifier_trap]
sql = "SELECT segment, customer_id, sum(revenue) AS revenue FROM orders JOIN customers USING (customer_id) GROUP BY ALL LIMIT 2000"
intent = "which customer segment spends the most"
accept = ["bar:segment+revenue"]
```

- [ ] **Step 3: Implement `src/jevviz/eval.py`**

```python
"""Golden-set eval: does Jev beat 'first valid candidate'? This is the project's go/no-go gate."""

from __future__ import annotations

import asyncio
import sys
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from dotenv import load_dotenv

from jevviz.backend import Backend, make_backend
from jevviz.db import open_db, run_query
from jevviz.pipeline import visualize
from jevviz.profile import profile
from jevviz.rules import enumerate_candidates


@dataclass(frozen=True)
class GoldenCase:
    name: str
    sql: str
    intent: str
    accept: list[str]


@dataclass
class EvalReport:
    top1: float
    top3: float
    baseline_top1: float
    rows: list[dict]


def load_golden(path: Path | None = None) -> list[GoldenCase]:
    raw = Path(path).read_bytes() if path else resources.files("jevviz").joinpath("golden.toml").read_bytes()
    return [GoldenCase(name, t["sql"], t["intent"], list(t["accept"])) for name, t in tomllib.loads(raw.decode()).items()]


def matches(kind: str, columns: tuple[str, ...], accept: list[str]) -> bool:
    for rule in accept:
        want_kind, _, cols = rule.partition(":")
        if want_kind == kind and set(filter(None, cols.split("+"))) <= set(columns):
            return True
    return False


async def run_eval(db_path: Path | str, backend: Backend, max_questions: int) -> EvalReport:
    con = open_db(db_path)
    rows = []
    for case in load_golden():
        result = run_query(con, case.sql)
        candidates, _ = enumerate_candidates(profile(result))
        by_id = {c.id: c for c in candidates}
        first = next(c for c in candidates if c.kind != "kpi")
        out = await visualize(case.sql, result, [case.intent], backend, None, max_questions)
        panel = out.panels[0]
        picks = [panel["chosen"]["id"], *[a["id"] for a in panel["alternates"]]][:3]
        hit = [matches(by_id[i].kind, by_id[i].columns, case.accept) for i in picks]
        rows.append({"name": case.name, "chosen": by_id[picks[0]].kind, "p": panel["chosen"]["p"],
                     "top1": hit[0], "top3": any(hit), "baseline": matches(first.kind, first.columns, case.accept)})
    n = len(rows)
    return EvalReport(sum(r["top1"] for r in rows) / n, sum(r["top3"] for r in rows) / n,
                      sum(r["baseline"] for r in rows) / n, rows)


if __name__ == "__main__":
    load_dotenv()
    db = sys.argv[1] if len(sys.argv) > 1 else "jevviz.duckdb"
    backend = make_backend()
    report = asyncio.run(run_eval(db, backend, int(sys.argv[2]) if len(sys.argv) > 2 else 72))
    print(f"backend={backend.name} simulated={backend.simulated}")
    for r in report.rows:
        print(f"{'✓' if r['top1'] else '✗'} {r['name']:28s} chose={r['chosen']:12s} p={r['p']:.2f} top3={r['top3']} baseline={r['baseline']}")
    print(f"\nJev top-1 {report.top1:.0%} · top-3 {report.top3:.0%} · rules-only top-1 {report.baseline_top1:.0%}")
```

Run: `uv run pytest tests/test_eval.py -q` — Expected: 3 passed.

- [ ] **Step 4: Owner checkpoint** — ask the project owner to extend `golden.toml` to ~30 cases (their analyst intuition about what people actually ask). Re-run `uv run pytest tests/test_eval.py -q`.

- [ ] **Step 5: Run the live gate**

```bash
uv run python -m jevviz.data jevviz.duckdb
uv run python -m jevviz.eval jevviz.duckdb <MAX_QUESTIONS_PER_REQUEST from docs/probe-results.md>
```

Expected: first line shows `simulated=False`. Paste the full output into `docs/eval-results.md`.

**GATE 2:** proceed to Task 11 only if Jev top-1 exceeds rules-only top-1 by ≥ 15 percentage points. If it does not: inspect the failing rows (state, question text, candidate descriptions, probabilities), improve the per-rule description templates or `LEVELS` wording, and re-run — at most 3 tuning rounds, each recorded in `docs/eval-results.md`. If the gate still fails, **stop and report to the owner**; do not build the API or frontend. Use the passing run to set `STRONG`, `WEAK` and `ID_NOUL` in `rank.py` and note the chosen values in `docs/eval-results.md`.

- [ ] **Step 6: Commit**

```bash
git add src/jevviz/golden.toml src/jevviz/eval.py src/jevviz/rank.py tests/test_eval.py docs/eval-results.md
git commit -m "feat: golden-set eval comparing Jev ranking against rules-only baseline"
```

---

### Task 11: FastAPI `/run` NDJSON stream

**Files:**
- Create: `src/jevviz/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `extract_viz`, `VizSyntaxError`, `open_db`, `run_query`, `QueryError`, `visualize`, `make_backend`, `Cache`.
- Produces: `create_app(db_path, backend=None, cache_path=None, max_questions=72) -> FastAPI`; `POST /run {"sql": str}` → `application/x-ndjson` events `parsed` / `result` / `spec` / `error` exactly as in spec §7; `GET /health` → `{"simulated": bool, "model": str}`. Run with `uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000`. Env: `JEVVIZ_DB` (default `jevviz.duckdb`), `JEVVIZ_MAX_QUESTIONS` (default `72`).

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:

```python
import json

import pytest
from fastapi.testclient import TestClient
from jevviz.api import create_app
from jevviz.backend import DemoBackend
from jevviz.data import generate
from jevviz.types import JudgeResult

TREND = "SELECT date_trunc('month', order_date) AS m, region, sum(revenue) AS revenue FROM orders GROUP BY ALL"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("d") / "api.duckdb"
    generate(path, n_orders=6_000)
    return path


def run(client, sql):
    resp = client.post("/run", json={"sql": sql})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in resp.text.splitlines() if line]


def test_full_stream_order_and_payload(db):
    events = run(TestClient(create_app(db, DemoBackend())), TREND + " VISUALIZE 'how are regions trending'")
    assert [e["type"] for e in events] == ["parsed", "result", "spec"]
    parsed, result, spec = events
    assert parsed["intents"] == ["how are regions trending"] and "VISUALIZE" not in parsed["sql"]
    assert result["columns"] == ["m", "region", "revenue"] and isinstance(result["rows"][0], dict)
    assert "query" in result["ms"] and result["truncated"] is False
    assert spec["simulated"] is True and spec["spec"]["root"] == "grid"
    assert {"profile", "enumerate", "jev"} <= set(spec["ms"]) and "usd" in spec["usage"]


def test_no_clause_ends_after_result(db):
    events = run(TestClient(create_app(db, DemoBackend())), "SELECT 1 AS x")
    assert [e["type"] for e in events] == ["parsed", "result"] and events[0]["intents"] is None


def test_sql_error_is_a_query_stage_error(db):
    events = run(TestClient(create_app(db, DemoBackend())), "SELEKT 1 VISUALIZE 'x'")
    assert [e["type"] for e in events] == ["parsed", "error"] and events[1]["stage"] == "query"


def test_parse_error_is_a_parse_stage_error(db):
    events = run(TestClient(create_app(db, DemoBackend())), "SELECT 1 VISUALIZE 'a' LIMIT 1")
    assert events == [{"type": "error", "stage": "parse", "message": events[0]["message"]}]


def test_viz_failure_keeps_the_data(db):
    class Broken(DemoBackend):
        async def judge(self, state, questions):
            return JudgeResult({}, 0, "OverloadedError: 529")

    events = run(TestClient(create_app(db, Broken())), TREND + " VISUALIZE 'x'")
    assert [e["type"] for e in events] == ["parsed", "result", "spec", "error"]
    assert events[2]["panels"][0]["chosen"]["kind"] == "table" and events[3]["stage"] == "jev"


def test_dates_are_json_serialised(db):
    events = run(TestClient(create_app(db, DemoBackend())), "SELECT order_date FROM orders LIMIT 1")
    assert isinstance(events[1]["rows"][0]["order_date"], str)
```

Run: `uv run pytest tests/test_api.py -q` — Expected: FAIL, module not found.

- [ ] **Step 2: Implement `src/jevviz/api.py`**

```python
"""FastAPI app: POST /run streams NDJSON events as each stage completes."""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from jevviz.backend import Backend, make_backend
from jevviz.cache import Cache
from jevviz.db import QueryError, open_db, run_query
from jevviz.parse import VizSyntaxError, extract_viz
from jevviz.pipeline import visualize


class RunRequest(BaseModel):
    sql: str


def _line(event: dict) -> bytes:
    return (json.dumps(event, default=str) + "\n").encode()


def create_app(db_path: Path | str, backend: Backend | None = None, cache_path: Path | str | None = None,
               max_questions: int = 72) -> FastAPI:
    app = FastAPI(title="jevviz")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["POST", "GET"], allow_headers=["*"])
    con = open_db(db_path)
    judge = backend or make_backend()
    cache = Cache(cache_path) if cache_path else None

    @app.get("/health")
    def health() -> dict:
        return {"simulated": judge.simulated, "model": judge.name}

    @app.post("/run")
    async def run(req: RunRequest) -> StreamingResponse:
        async def stream() -> AsyncIterator[bytes]:
            try:
                sql, intents = extract_viz(req.sql)
            except VizSyntaxError as exc:
                yield _line({"type": "error", "stage": "parse", "message": str(exc)})
                return
            yield _line({"type": "parsed", "sql": sql, "intents": intents})
            t0 = time.perf_counter()
            try:
                result = run_query(con, sql)
            except QueryError as exc:
                yield _line({"type": "error", "stage": "query", "message": str(exc)})
                return
            rows = [dict(zip(result.columns, row)) for row in result.rows]
            yield _line({"type": "result", "columns": result.columns, "rows": rows, "row_count": result.row_count,
                         "truncated": result.truncated, "ms": {"query": round((time.perf_counter() - t0) * 1000, 1)}})
            if intents is None:
                return
            out = await visualize(sql, result, intents, judge, cache, max_questions)
            yield _line({"type": "spec", "spec": out.spec, "panels": out.panels, "ms": out.ms,
                         "usage": {"input_tokens": out.input_tokens, "usd": out.usd},
                         "scored": out.scored, "cache": out.cache, "simulated": out.simulated})
            if out.error:
                yield _line({"type": "error", "stage": "jev", "message": out.error})

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    return app


load_dotenv()
app = create_app(os.environ.get("JEVVIZ_DB", "jevviz.duckdb"), cache_path=".jev_cache.sqlite",
                 max_questions=int(os.environ.get("JEVVIZ_MAX_QUESTIONS", "72"))) \
    if Path(os.environ.get("JEVVIZ_DB", "jevviz.duckdb")).exists() else None
```

Run: `uv run pytest -q && uv run ruff check` — Expected: all pass, lint clean.

- [ ] **Step 3: Smoke it by hand**

```bash
uv run python -m jevviz.data jevviz.duckdb
uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000 &
curl -sN -X POST localhost:8000/run -H 'content-type: application/json' \
  -d "{\"sql\": \"SELECT channel, sum(revenue) AS revenue FROM orders GROUP BY ALL VISUALIZE 'share per channel'\"}" | cut -c1-160
kill %1
```

Expected: three lines beginning `{"type": "parsed"`, `{"type": "result"`, `{"type": "spec"`.

- [ ] **Step 4: Commit**

```bash
git add src/jevviz/api.py tests/test_api.py
git commit -m "feat: stream parsed/result/spec/error events from POST /run"
```

---

### Task 12: Frontend scaffold, catalog and registry

**Files:**
- Create: `web/` via Vite, then `web/src/catalog.ts`, `web/src/registry.tsx`, `web/src/components/{Chart,Kpi,DataTable,Panel}.tsx`, `web/src/rows.ts`
- Test: `web/src/registry.test.tsx`

**Interfaces:**
- Consumes: the flat spec and `panels[]` wire shapes from Task 9/11.
- Produces: `catalog`, `registry` (json-render), `RowsContext` (`React.Context<Record<string, unknown>[]>`), `PanelActionsContext` (`React.Context<{ alternates: (panelIndex: number) => AltEntry[]; swap: (panelIndex: number, altId: string) => void }>`), type `AltEntry = { id: string; kind: string; title: string; p: number; element: SpecElement }`, type `SpecElement = { type: string; props: Record<string, unknown>; children: string[] }`.

- [ ] **Step 1: Scaffold and install**

```bash
npm create vite@latest web -- --template react-ts
cd web && npm install @json-render/core @json-render/react zod vega vega-lite vega-embed \
  codemirror @codemirror/lang-sql @codemirror/view @codemirror/state
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom @playwright/test
```

Add to `web/vite.config.ts`: `test: { environment: "jsdom", globals: true }` (import `defineConfig` from `vitest/config`), and `server: { proxy: { "/run": "http://127.0.0.1:8000", "/health": "http://127.0.0.1:8000" } }`.

- [ ] **Step 2: Verify the installed json-render API before writing against it**

Run: `ls web/node_modules/@json-render/react/dist && grep -n "export" web/node_modules/@json-render/react/dist/index.d.ts | head -40`
Expected exports (from the docs read during planning): `defineRegistry`, `Renderer`, `StateProvider`, `VisibilityProvider`, `schema`; and `defineCatalog` from `@json-render/core`. Documented usage:

```tsx
import { defineCatalog } from "@json-render/core";
import { defineRegistry, Renderer, StateProvider, VisibilityProvider, schema } from "@json-render/react";
const catalog = defineCatalog(schema, { components: { Card: { props: z.object({...}), description: "…" } }, actions: {} });
const { registry } = defineRegistry(catalog, { components: { Card: ({ props, children }) => <div>{children}</div> } });
<StateProvider initialState={{}}><VisibilityProvider><Renderer spec={spec} registry={registry} /></VisibilityProvider></StateProvider>
```

If an export name differs in the installed version, use the installed name and record the difference in `web/README.md`. Do not use anything prefixed `experimental_`.

- [ ] **Step 3: Write the failing test**

`web/src/registry.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { Renderer, StateProvider, VisibilityProvider } from "@json-render/react";
import { vi, test, expect } from "vitest";
import { registry } from "./registry";
import { RowsContext, PanelActionsContext } from "./rows";

vi.mock("vega-embed", () => ({ default: vi.fn(async () => ({ view: { finalize() {} } })) }));

const spec = {
  root: "grid",
  elements: {
    grid: { type: "Grid", props: { columns: 1 }, children: ["panel-0"] },
    "panel-0": { type: "Panel", props: { title: "Revenue by Region", intent: "top regions", p: 0.82, match: "strong", panelIndex: 0 }, children: ["leaf-0"] },
    "leaf-0": { type: "Table", props: { columns: ["region", "revenue"], maxRows: 200 }, children: [] },
  },
};

test("renders panel chrome, table rows and alternates", () => {
  const actions = { alternates: () => [{ id: "c07", kind: "pie", title: "Share", p: 0.41, element: spec.elements["leaf-0"] }], swap: vi.fn() };
  render(
    <RowsContext.Provider value={[{ region: "EMEA", revenue: 10 }]}>
      <PanelActionsContext.Provider value={actions}>
        <StateProvider initialState={{}}><VisibilityProvider><Renderer spec={spec} registry={registry} /></VisibilityProvider></StateProvider>
      </PanelActionsContext.Provider>
    </RowsContext.Provider>,
  );
  expect(screen.getByText("Revenue by Region")).toBeInTheDocument();
  expect(screen.getByText("82% match")).toBeInTheDocument();
  expect(screen.getByText("EMEA")).toBeInTheDocument();
  screen.getByRole("button", { name: /Share/ }).click();
  expect(actions.swap).toHaveBeenCalledWith(0, "c07");
});
```

Run: `cd web && npx vitest run` — Expected: FAIL, `./registry` not found.

- [ ] **Step 4: Implement contexts, catalog, components, registry**

`web/src/rows.ts`:

```ts
import { createContext } from "react";

export type SpecElement = { type: string; props: Record<string, unknown>; children: string[] };
export type AltEntry = { id: string; kind: string; title: string; p: number; element: SpecElement };
export type PanelActions = { alternates: (panelIndex: number) => AltEntry[]; swap: (panelIndex: number, altId: string) => void };

export const RowsContext = createContext<Record<string, unknown>[]>([]);
export const PanelActionsContext = createContext<PanelActions>({ alternates: () => [], swap: () => {} });
```

Rows travel through React context rather than json-render `$state` so a 5,000-row array is never copied into the spec or diffed by the renderer; the effect is the same as spec §8 (rows sent once, every chart reads them by name).

`web/src/catalog.ts`:

```ts
import { defineCatalog } from "@json-render/core";
import { schema } from "@json-render/react";
import { z } from "zod";

export const catalog = defineCatalog(schema, {
  components: {
    Grid: { props: z.object({ columns: z.number().int().min(1).max(3) }), slots: ["default"], description: "Dashboard grid" },
    Panel: {
      props: z.object({ title: z.string(), intent: z.string(), p: z.number(), match: z.enum(["strong", "weak", "none"]), panelIndex: z.number().int() }),
      slots: ["default"], description: "Framed panel with match chip and alternates",
    },
    Chart: { props: z.object({ vega: z.record(z.string(), z.unknown()) }), description: "Vega-Lite chart over the shared rows" },
    Kpi: { props: z.object({ label: z.string(), field: z.string() }), description: "Single headline number from row 0" },
    Table: { props: z.object({ columns: z.array(z.string()), maxRows: z.number().int() }), description: "Result table" },
  },
  actions: {},
});
```

`web/src/components/Chart.tsx`:

```tsx
import { useContext, useEffect, useRef } from "react";
import embed from "vega-embed";
import { RowsContext } from "../rows";

export function Chart({ vega }: { vega: Record<string, unknown> }) {
  const rows = useContext(RowsContext);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const t0 = performance.now();
    let finalize = () => {};
    embed(ref.current, { ...vega, datasets: { rows } } as never, { actions: false, renderer: "canvas" }).then((res) => {
      finalize = () => res.view.finalize();
      window.dispatchEvent(new CustomEvent("jevviz:rendered", { detail: performance.now() - t0 }));
    });
    return () => finalize();
  }, [vega, rows]);
  return <div ref={ref} className="chart" data-testid="chart" />;
}
```

`web/src/components/Kpi.tsx`:

```tsx
import { useContext } from "react";
import { RowsContext } from "../rows";

export function Kpi({ label, field }: { label: string; field: string }) {
  const value = useContext(RowsContext)[0]?.[field];
  const text = typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value ?? "—");
  return <div className="kpi"><div className="kpi-value">{text}</div><div className="kpi-label">{label}</div></div>;
}
```

`web/src/components/DataTable.tsx`:

```tsx
import { useContext } from "react";
import { RowsContext } from "../rows";

export function DataTable({ columns, maxRows }: { columns: string[]; maxRows: number }) {
  const rows = useContext(RowsContext).slice(0, maxRows);
  return (
    <div className="table-wrap"><table>
      <thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{columns.map((c) => <td key={c}>{String(r[c] ?? "")}</td>)}</tr>)}</tbody>
    </table></div>
  );
}
```

`web/src/components/Panel.tsx`:

```tsx
import { useContext, type ReactNode } from "react";
import { PanelActionsContext } from "../rows";

type Props = { title: string; intent: string; p: number; match: "strong" | "weak" | "none"; panelIndex: number; children?: ReactNode };

export function Panel({ title, intent, p, match, panelIndex, children }: Props) {
  const { alternates, swap } = useContext(PanelActionsContext);
  const alts = alternates(panelIndex);
  return (
    <section className={`panel match-${match}`}>
      <header>
        <h3>{title}</h3>
        <span className="intent">“{intent}”</span>
        {match === "none" ? <span className="chip none">no strong match</span> : <span className="chip">{Math.round(p * 100)}% match</span>}
        {match === "weak" && <span className="chip weak">weak match</span>}
      </header>
      {children}
      {alts.length > 0 && (
        <footer>also consider:{" "}
          {alts.map((a) => <button key={a.id} onClick={() => swap(panelIndex, a.id)}>{a.title} · {Math.round(a.p * 100)}%</button>)}
        </footer>
      )}
    </section>
  );
}
```

`web/src/registry.tsx`:

```tsx
import { defineRegistry } from "@json-render/react";
import { catalog } from "./catalog";
import { Chart } from "./components/Chart";
import { DataTable } from "./components/DataTable";
import { Kpi } from "./components/Kpi";
import { Panel } from "./components/Panel";

export const { registry } = defineRegistry(catalog, {
  components: {
    Grid: ({ props, children }) => <div className="grid" style={{ gridTemplateColumns: `repeat(${props.columns}, minmax(0, 1fr))` }}>{children}</div>,
    Panel: ({ props, children }) => <Panel {...props}>{children}</Panel>,
    Chart: ({ props }) => <Chart vega={props.vega} />,
    Kpi: ({ props }) => <Kpi label={props.label} field={props.field} />,
    Table: ({ props }) => <DataTable columns={props.columns} maxRows={props.maxRows} />,
  },
});
```

Run: `cd web && npx vitest run && npx tsc --noEmit` — Expected: 1 passed, no type errors.

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat(web): json-render catalog and registry with Vega-Lite chart component"
```

---

### Task 13: Frontend app — editor, stream client, timing bar, alternate swapping

**Files:**
- Create: `web/src/stream.ts`, `web/src/reducer.ts`, `web/src/Editor.tsx`, `web/src/TimingBar.tsx`, `web/src/examples.ts`, `web/src/app.css`
- Modify: `web/src/App.tsx` (replace Vite's default), `web/src/main.tsx` (import `./app.css` instead of `./index.css`)
- Test: `web/src/reducer.test.ts`, `web/src/stream.test.ts`

**Interfaces:**
- Consumes: `registry`, `RowsContext`, `PanelActionsContext`, `AltEntry`, `SpecElement` (Task 12); NDJSON events (Task 11).
- Produces: `type RunEvent` (union of the four events); `async function* runQuery(sql: string, signal?: AbortSignal): AsyncGenerator<RunEvent>`; `type AppState`; `reduce(state: AppState, action: Action): AppState` with actions `start`, `event`, `swap`, `rendered`.

- [ ] **Step 1: Write the failing tests**

`web/src/reducer.test.ts`:

```ts
import { expect, test } from "vitest";
import { initialState, reduce } from "./reducer";

const leaf = (type: string) => ({ type, props: {}, children: [] });
const specEvent = {
  type: "spec" as const,
  spec: { root: "grid", elements: { grid: { type: "Grid", props: { columns: 1 }, children: ["panel-0"] },
    "panel-0": { type: "Panel", props: { title: "Bar", intent: "q", p: 0.8, match: "strong", panelIndex: 0 }, children: ["leaf-0"] },
    "leaf-0": leaf("Chart") } },
  panels: [{ intent: "q", match: "strong", chosen: { id: "c00", kind: "bar", title: "Bar", p: 0.8, element: leaf("Chart") },
    alternates: [{ id: "c05", kind: "pie", title: "Pie", p: 0.4, element: leaf("Chart") }] }],
  ms: { profile: 1, enumerate: 1, jev: 250 }, usage: { input_tokens: 2400, usd: 0.0001 }, scored: "9 of 9", cache: "miss", simulated: true,
};
const resultEvent = { type: "result" as const, columns: ["a"], rows: [{ a: 1 }], row_count: 1, truncated: false, ms: { query: 3 } };

test("result paints a table immediately, spec replaces it", () => {
  let s = reduce(initialState, { type: "start" });
  s = reduce(s, { type: "event", event: resultEvent });
  expect(s.spec?.elements[s.spec.root].type).toBe("Table");
  expect(s.rows).toEqual([{ a: 1 }]);
  s = reduce(s, { type: "event", event: specEvent });
  expect(s.spec?.root).toBe("grid");
  expect(s.timings).toMatchObject({ query: 3, jev: 250 });
});

test("swap exchanges chosen and alternate without losing the old one", () => {
  let s = reduce(reduce(initialState, { type: "event", event: resultEvent }), { type: "event", event: specEvent });
  s = reduce(s, { type: "swap", panelIndex: 0, altId: "c05" });
  expect(s.spec?.elements["panel-0"].props).toMatchObject({ title: "Pie", p: 0.4 });
  expect(s.panels[0].chosen.id).toBe("c05");
  expect(s.panels[0].alternates.map((a) => a.id)).toEqual(["c00"]);
});

test("jev error keeps the rendered spec and records a warning", () => {
  let s = reduce(reduce(initialState, { type: "event", event: resultEvent }), { type: "event", event: specEvent });
  s = reduce(s, { type: "event", event: { type: "error", stage: "jev", message: "boom" } });
  expect(s.spec?.root).toBe("grid");
  expect(s.error).toEqual({ stage: "jev", message: "boom" });
});

test("start clears the previous run", () => {
  const s = reduce(reduce(initialState, { type: "event", event: resultEvent }), { type: "start" });
  expect(s.spec).toBeNull();
  expect(s.running).toBe(true);
});
```

`web/src/stream.test.ts`:

```ts
import { expect, test, vi } from "vitest";
import { runQuery } from "./stream";

test("parses NDJSON split across chunk boundaries", async () => {
  const enc = new TextEncoder();
  const chunks = ['{"type":"parsed","sql":"s","inte', 'nts":null}\n{"type":"result","columns":[],', '"rows":[],"row_count":0,"truncated":false,"ms":{"query":1}}\n'];
  const body = new ReadableStream({ start(c) { chunks.forEach((x) => c.enqueue(enc.encode(x))); c.close(); } });
  vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status: 200 })));
  const events = [];
  for await (const e of runQuery("s")) events.push(e.type);
  expect(events).toEqual(["parsed", "result"]);
});
```

Run: `cd web && npx vitest run` — Expected: FAIL, modules not found.

- [ ] **Step 2: Implement `web/src/stream.ts`**

```ts
import type { AltEntry, SpecElement } from "./rows";

export type Spec = { root: string; elements: Record<string, SpecElement> };
export type PanelInfo = { intent: string; match: "strong" | "weak" | "none"; chosen: AltEntry; alternates: AltEntry[] };
export type RunEvent =
  | { type: "parsed"; sql: string; intents: string[] | null }
  | { type: "result"; columns: string[]; rows: Record<string, unknown>[]; row_count: number; truncated: boolean; ms: { query: number } }
  | { type: "spec"; spec: Spec; panels: PanelInfo[]; ms: { profile: number; enumerate: number; jev: number };
      usage: { input_tokens: number; usd: number }; scored: string; cache: string; simulated: boolean }
  | { type: "error"; stage: string; message: string };

export async function* runQuery(sql: string, signal?: AbortSignal): AsyncGenerator<RunEvent> {
  const resp = await fetch("/run", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ sql }), signal });
  if (!resp.ok || !resp.body) throw new Error(`server returned ${resp.status}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) yield JSON.parse(line) as RunEvent;
    }
    if (done) break;
  }
}
```

- [ ] **Step 3: Implement `web/src/reducer.ts`**

```ts
import type { PanelInfo, RunEvent, Spec } from "./stream";

export type AppState = {
  running: boolean; rows: Record<string, unknown>[]; spec: Spec | null; panels: PanelInfo[];
  timings: Partial<Record<"query" | "profile" | "enumerate" | "jev" | "render", number>>;
  usage: { input_tokens: number; usd: number } | null; scored: string | null; cache: string | null; simulated: boolean;
  rowNote: string | null; error: { stage: string; message: string } | null;
};
export type Action =
  | { type: "start" } | { type: "done" } | { type: "event"; event: RunEvent }
  | { type: "swap"; panelIndex: number; altId: string } | { type: "rendered"; ms: number };

export const initialState: AppState = { running: false, rows: [], spec: null, panels: [], timings: {}, usage: null,
  scored: null, cache: null, simulated: false, rowNote: null, error: null };

export function reduce(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "start": return { ...initialState, running: true, simulated: state.simulated };
    case "done": return { ...state, running: false };
    case "rendered": return { ...state, timings: { ...state.timings, render: Math.round(action.ms) } };
    case "swap": {
      const panel = state.panels[action.panelIndex];
      const alt = panel?.alternates.find((a) => a.id === action.altId);
      if (!state.spec || !panel || !alt) return state;
      const panels = state.panels.map((p, i) => i !== action.panelIndex ? p
        : { ...p, chosen: alt, alternates: [panel.chosen, ...p.alternates.filter((a) => a.id !== alt.id)] });
      const pid = `panel-${action.panelIndex}`, lid = `leaf-${action.panelIndex}`;
      const elements = { ...state.spec.elements, [lid]: alt.element,
        [pid]: { ...state.spec.elements[pid], props: { ...state.spec.elements[pid].props, title: alt.title, p: alt.p } } };
      return { ...state, panels, spec: { ...state.spec, elements } };
    }
    case "event": {
      const e = action.event;
      if (e.type === "parsed") return state;
      if (e.type === "error") return { ...state, error: { stage: e.stage, message: e.message } };
      if (e.type === "result") {
        const spec: Spec = { root: "table", elements: { table: { type: "Table", props: { columns: e.columns, maxRows: 200 }, children: [] } } };
        return { ...state, rows: e.rows, spec, timings: { query: e.ms.query },
          rowNote: e.truncated ? `showing ${e.rows.length.toLocaleString()} of ${e.row_count.toLocaleString()} rows` : null };
      }
      return { ...state, spec: e.spec, panels: e.panels, timings: { ...state.timings, ...e.ms }, usage: e.usage,
        scored: e.scored, cache: e.cache, simulated: e.simulated };
    }
  }
}
```

Run: `cd web && npx vitest run` — Expected: all tests pass (Task 12's test included).

- [ ] **Step 4: Implement the UI shell**

`web/src/examples.ts`:

```ts
export const EXAMPLES: { label: string; sql: string }[] = [
  { label: "Regions trending", sql: "SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue\nFROM orders GROUP BY ALL\nVISUALIZE 'how are regions trending'" },
  { label: "Same query, different question", sql: "SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue\nFROM orders GROUP BY ALL\nVISUALIZE 'which region sold the most overall'" },
  { label: "Channel share", sql: "SELECT channel, sum(revenue) AS revenue FROM orders GROUP BY ALL\nVISUALIZE 'what share of revenue comes from each channel'" },
  { label: "Price vs rating", sql: "SELECT price, rating, category FROM products\nVISUALIZE 'do more expensive products get better ratings'" },
  { label: "Identifier trap", sql: "SELECT segment, customer_id, sum(revenue) AS revenue\nFROM orders JOIN customers USING (customer_id) GROUP BY ALL LIMIT 2000\nVISUALIZE 'which customer segment spends the most'" },
  { label: "Dashboard (3 intents)", sql: "SELECT date_trunc('month', order_date) AS order_month, region, channel, sum(revenue) AS revenue\nFROM orders GROUP BY ALL\nVISUALIZE 'how are regions trending', 'which channel is biggest', 'where do region and channel combine best'" },
  { label: "Plain SQL (no clause)", sql: "SELECT * FROM products LIMIT 20" },
];
```

`web/src/Editor.tsx`:

```tsx
import { sql } from "@codemirror/lang-sql";
import { EditorState } from "@codemirror/state";
import { Decoration, EditorView, MatchDecorator, ViewPlugin, keymap, type DecorationSet, type ViewUpdate } from "@codemirror/view";
import { basicSetup } from "codemirror";
import { useEffect, useRef } from "react";

const matcher = new MatchDecorator({ regexp: /\bVISUALIZE\b/gi, decoration: Decoration.mark({ class: "cm-visualize" }) });
const visualizeKeyword = ViewPlugin.fromClass(class {
  decorations: DecorationSet;
  constructor(view: EditorView) { this.decorations = matcher.createDeco(view); }
  update(u: ViewUpdate) { this.decorations = matcher.updateDeco(u, this.decorations); }
}, { decorations: (v) => v.decorations });

export function Editor({ value, onChange, onRun }: { value: string; onChange: (v: string) => void; onRun: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const run = useRef(onRun); run.current = onRun;
  const change = useRef(onChange); change.current = onChange;

  useEffect(() => {
    view.current = new EditorView({ parent: host.current!, state: EditorState.create({ doc: value, extensions: [
      keymap.of([{ key: "Mod-Enter", run: () => { run.current(); return true; } }]),
      basicSetup, sql(), visualizeKeyword,
      EditorView.updateListener.of((u) => { if (u.docChanged) change.current(u.state.doc.toString()); }),
    ] }) });
    return () => view.current?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const v = view.current;
    if (v && v.state.doc.toString() !== value) v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } });
  }, [value]);

  return <div ref={host} className="editor" />;
}
```

`web/src/TimingBar.tsx`:

```tsx
import type { AppState } from "./reducer";

export function TimingBar({ s }: { s: AppState }) {
  const t = s.timings;
  const part = (label: string, v?: number) => (v === undefined ? null : <span key={label}>{label} <b>{v}ms</b></span>);
  return (
    <div className="timing" data-testid="timing">
      {part("query", t.query)}{part("profile", t.profile)}{part("jev", s.cache === "hit" ? 0 : t.jev)}{part("render", t.render)}
      {s.usage && <span><b>{s.usage.input_tokens.toLocaleString()}</b> tok · ${s.usage.usd.toFixed(4)}</span>}
      {s.scored && <span>{s.scored} scored</span>}
      {s.cache && <span>cache: {s.cache}</span>}
      {s.rowNote && <span>{s.rowNote}</span>}
      {s.simulated && <span className="simulated" data-testid="simulated">SIMULATED</span>}
    </div>
  );
}
```

`web/src/App.tsx`:

```tsx
import { Renderer, StateProvider, VisibilityProvider } from "@json-render/react";
import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { Editor } from "./Editor";
import { EXAMPLES } from "./examples";
import { initialState, reduce } from "./reducer";
import { registry } from "./registry";
import { PanelActionsContext, RowsContext } from "./rows";
import { runQuery } from "./stream";
import { TimingBar } from "./TimingBar";

export default function App() {
  const [sql, setSql] = useState(EXAMPLES[0].sql);
  const [s, dispatch] = useReducer(reduce, initialState);

  const run = useCallback(async () => {
    dispatch({ type: "start" });
    try {
      for await (const event of runQuery(sql)) dispatch({ type: "event", event });
    } catch (err) {
      dispatch({ type: "event", event: { type: "error", stage: "network", message: String(err) } });
    } finally {
      dispatch({ type: "done" });
    }
  }, [sql]);

  useEffect(() => {
    const onRendered = (e: Event) => dispatch({ type: "rendered", ms: (e as CustomEvent<number>).detail });
    window.addEventListener("jevviz:rendered", onRendered);
    return () => window.removeEventListener("jevviz:rendered", onRendered);
  }, []);

  const actions = useMemo(() => ({
    alternates: (i: number) => s.panels[i]?.alternates ?? [],
    swap: (panelIndex: number, altId: string) => dispatch({ type: "swap", panelIndex, altId }),
  }), [s.panels]);

  return (
    <div className="app">
      <aside>
        <h1>Jev <code>VISUALIZE</code></h1>
        <Editor value={sql} onChange={setSql} onRun={run} />
        <div className="controls">
          <select aria-label="examples" onChange={(e) => setSql(EXAMPLES[Number(e.target.value)].sql)}>
            {EXAMPLES.map((ex, i) => <option key={ex.label} value={i}>{ex.label}</option>)}
          </select>
          <button onClick={run} disabled={s.running}>{s.running ? "Running…" : "Run ⌘↵"}</button>
        </div>
        {s.error && <p className={`error stage-${s.error.stage}`} role="alert">{s.error.stage}: {s.error.message}</p>}
      </aside>
      <main>
        {s.spec ? (
          <RowsContext.Provider value={s.rows}>
            <PanelActionsContext.Provider value={actions}>
              <StateProvider initialState={{}}><VisibilityProvider><Renderer spec={s.spec} registry={registry} /></VisibilityProvider></StateProvider>
            </PanelActionsContext.Provider>
          </RowsContext.Provider>
        ) : <p className="empty">Run a query. End it with <code>VISUALIZE '…'</code> to let Jev pick the chart.</p>}
      </main>
      <TimingBar s={s} />
    </div>
  );
}
```

`web/src/app.css`:

```css
:root { --bg:#0f1115; --panel:#171a21; --line:#262b36; --text:#e6e8ee; --muted:#8b93a7; --accent:#ff7a3d; --warn:#f2c14e; color-scheme: dark; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.5 ui-sans-serif,system-ui,sans-serif; }
.app { display:grid; grid-template:1fr auto / minmax(340px,38%) 1fr; height:100vh; }
aside { padding:16px; border-right:1px solid var(--line); display:flex; flex-direction:column; gap:12px; min-width:0; }
h1 { font-size:16px; margin:0; } h1 code, .cm-visualize { color:var(--accent); font-weight:700; }
.editor { flex:1; min-height:0; border:1px solid var(--line); border-radius:8px; overflow:auto; background:var(--panel); }
.editor .cm-editor { height:100%; } .controls { display:flex; gap:8px; } .controls select { flex:1; }
button, select { background:var(--panel); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 10px; cursor:pointer; }
button:hover { border-color:var(--accent); }
main { padding:16px; overflow:auto; min-width:0; } .empty { color:var(--muted); }
.grid { display:grid; gap:16px; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; min-width:0; }
.panel header { display:flex; flex-wrap:wrap; align-items:baseline; gap:8px; margin-bottom:8px; }
.panel h3 { margin:0; font-size:15px; } .intent { color:var(--muted); font-style:italic; }
.chip { margin-left:auto; font-size:12px; padding:2px 8px; border-radius:99px; border:1px solid var(--accent); color:var(--accent); }
.chip.weak, .chip.none { margin-left:0; border-color:var(--warn); color:var(--warn); }
.panel footer { margin-top:8px; color:var(--muted); font-size:12px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
.panel footer button { font-size:12px; padding:2px 8px; }
.chart { width:100%; } .kpi-value { font-size:40px; font-weight:700; } .kpi-label { color:var(--muted); }
.table-wrap { overflow:auto; max-height:420px; } table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th, td { text-align:left; padding:4px 10px; border-bottom:1px solid var(--line); white-space:nowrap; } th { color:var(--muted); position:sticky; top:0; background:var(--panel); }
.error { color:#ff8080; margin:0; } .error.stage-jev { color:var(--warn); }
.timing { grid-column:1 / -1; display:flex; flex-wrap:wrap; gap:16px; padding:8px 16px; border-top:1px solid var(--line); color:var(--muted); font:12px ui-monospace,monospace; }
.timing b { color:var(--text); } .simulated { margin-left:auto; color:#000; background:var(--warn); font-weight:700; padding:0 8px; border-radius:4px; }
```

In `web/src/main.tsx` replace `import './index.css'` with `import './app.css'` and delete `web/src/index.css` and `web/src/App.css`.

Run: `cd web && npx vitest run && npx tsc --noEmit && npm run build` — Expected: tests pass, no type errors, build succeeds.

- [ ] **Step 5: Look at it**

```bash
uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000 &
(cd web && npm run dev) &
```

Open `http://localhost:5173`, run each example. Check: the table appears first and the chart replaces it; the timing bar fills in; clicking an "also consider" button swaps the chart with no network request (verify in devtools Network tab); the "Identifier trap" example never charts `customer_id` as a measure; the dashboard example shows three different panels. Stop both processes afterwards.

- [ ] **Step 6: Commit**

```bash
git add web
git commit -m "feat(web): SQL editor, NDJSON stream client, timing bar and alternate swapping"
```

---

### Task 14: End-to-end smoke test, demo script and docs

**Files:**
- Create: `web/playwright.config.ts`, `web/e2e/smoke.spec.ts`, `README.md`, `CLAUDE.md`, `demo.sql`
- Modify: `web/package.json` (add script `"e2e": "playwright test"`)

**Interfaces:**
- Consumes: the running backend (demo mode) and frontend.

- [ ] **Step 1: Write the Playwright config and smoke test**

`web/playwright.config.ts`:

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:5173" },
  webServer: [
    { command: "cd .. && uv run python -m jevviz.data e2e.duckdb && env -u TYPESAFE_API_KEY JEVVIZ_DB=e2e.duckdb DOTENV_DISABLE=1 uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health", reuseExistingServer: false, timeout: 60_000 },
    { command: "npm run dev", url: "http://localhost:5173", reuseExistingServer: false },
  ],
});
```

The e2e run must be offline and simulated. `load_dotenv()` would re-read the key from `.env`, so make `api.py` honour the opt-out: replace its module-level `load_dotenv()` call with

```python
if not os.environ.get("DOTENV_DISABLE"):
    load_dotenv()
```

`web/e2e/smoke.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("run example: table first, then a chart, in simulated mode", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("chart")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("chart").locator("canvas")).toBeVisible();
  await expect(page.getByTestId("simulated")).toHaveText("SIMULATED");
  await expect(page.getByTestId("timing")).toContainText("jev");
  await expect(page.getByText(/% match/)).toBeVisible();
});

test("plain SQL shows a table and no panel", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("examples").selectOption({ label: "Plain SQL (no clause)" });
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.locator("table")).toBeVisible();
  await expect(page.getByText(/% match/)).toHaveCount(0);
});

test("swapping an alternate makes no network request", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("chart")).toBeVisible({ timeout: 10_000 });
  let calls = 0;
  page.on("request", (r) => { if (r.url().includes("/run")) calls += 1; });
  const title = await page.locator(".panel h3").first().textContent();
  await page.locator(".panel footer button").first().click();
  await expect(page.locator(".panel h3").first()).not.toHaveText(title ?? "");
  expect(calls).toBe(0);
});
```

Add `e2e.duckdb` to `.gitignore` (already covered by `*.duckdb`).

Run: `cd web && npx playwright install chromium && npm run e2e` — Expected: 3 passed.

- [ ] **Step 2: Write `demo.sql`** — the recordable script, one statement per beat

```sql
-- 1. Plain SQL still works.
SELECT * FROM products LIMIT 20;

-- 2. Same data, one new clause. Jev picks the chart.
SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue
FROM orders GROUP BY ALL
VISUALIZE 'how are regions trending';

-- 3. Same query, different question -> different chart. No SQL changed.
SELECT date_trunc('month', order_date) AS order_month, region, sum(revenue) AS revenue
FROM orders GROUP BY ALL
VISUALIZE 'which region sold the most overall';

-- 4. Run #2 again: cache hit, jev 0ms.

-- 5. Jev knows customer_id is not a measure. Type rules cannot.
SELECT segment, customer_id, sum(revenue) AS revenue
FROM orders JOIN customers USING (customer_id) GROUP BY ALL LIMIT 2000
VISUALIZE 'which customer segment spends the most';

-- 6. Three intents -> a dashboard, still one Jev request.
SELECT date_trunc('month', order_date) AS order_month, region, channel, sum(revenue) AS revenue
FROM orders GROUP BY ALL
VISUALIZE 'how are regions trending', 'which channel is biggest', 'where do region and channel combine best';
```

- [ ] **Step 3: Write `README.md`**

Sections, each with real content: **What this is** (two sentences + the example query); **How it works** (the six pipeline steps and the "code proposes, Jev selects, code assembles" principle); **Run it** —

```bash
uv sync
uv run python -m jevviz.data jevviz.duckdb
uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000
cd web && npm install && npm run dev      # second terminal, then open http://localhost:5173
```

— **Demo mode** (no `TYPESAFE_API_KEY` → deterministic offline backend, `SIMULATED` badge; never present simulated output as real); **Tests** (`uv run pytest -q`, `cd web && npx vitest run`, `npm run e2e`; live eval `uv run python -m jevviz.eval`); **Results** (copy the headline numbers from `docs/probe-results.md` and `docs/eval-results.md`, with the date and model version); **Adding a chart type** (write one `@rule` function returning `Candidate`s with a description in the fixed grammar "form, measure, breakdown, what it reveals"; nothing else changes); **Limits** (no generated titles, Vega-Lite chart types only, localhost only, thresholds tuned on a small golden set).

- [ ] **Step 4: Write `CLAUDE.md`**

```markdown
# CLAUDE.md

Jev VISUALIZE demo: a SQL `VISUALIZE '<intent>'` clause where TypeSafe's Jev model ranks code-generated chart candidates. Spec: `docs/superpowers/specs/2026-09-21-jev-visualize-design.md`.

## Commands
- Backend: `uv sync`, `uv run python -m jevviz.data jevviz.duckdb`, `uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000`
- Frontend: `cd web && npm install && npm run dev`
- Tests: `uv run pytest -q` · `uv run ruff check` · `cd web && npx vitest run` · `cd web && npm run e2e`
- Live eval (needs key): `uv run python -m jevviz.eval jevviz.duckdb`

## Rules
- Never read, print or log `.env` or `TYPESAFE_API_KEY`. The key stays server-side.
- Jev never counts, compares numbers or writes text. Numeric guards live in `profile.py` and `rules/`; titles are templates.
- Rank by `P(level >= 2)`; never use the interpolated Score value.
- Every rule emits only valid charts; `tests/test_vega_valid.py` must stay green. Never loosen it.
- Demo mode must always show the `SIMULATED` badge. Do not report simulated numbers as real.
- The backend emits only `Grid`, `Panel`, `Chart`, `Kpi`, `Table`. No json-render `experimental_*` APIs.
- A viz failure never hides the data: the table stays on screen.
- Changing a rule description or `LEVELS` wording changes model behaviour: re-run the live eval and update `docs/eval-results.md`.
```

- [ ] **Step 5: Full verification**

Run: `uv run pytest -q && uv run ruff check && (cd web && npx vitest run && npx tsc --noEmit && npm run e2e)`
Expected: everything passes. Then, with the key present, start both servers and run `demo.sql` beat by beat; confirm the badge is absent, timings are sub-second, and beat 4 shows `cache: hit`.

- [ ] **Step 6: Commit**

```bash
git add web/playwright.config.ts web/e2e web/package.json src/jevviz/api.py README.md CLAUDE.md demo.sql
git commit -m "test: e2e smoke in simulated mode; docs and recordable demo script"
```

---

## Spec coverage map

| Spec section | Task |
|---|---|
| §1 success criteria 1 (beats baseline) | 10 (Gate 2) |
| §1 success criteria 2 (sub-second, timing bar) | 11, 13, 14 step 5 |
| §1 success criteria 3 (offline demo mode) | 0, 14 |
| §3 VISUALIZE clause | 2 |
| §4 Profile | 4 |
| §5 Candidates, rules, cap | 5, 6 |
| §6 Questions, state, cache, open unknown | 1, 7, 9 |
| §6 Ranking, bands, alternates, collisions | 8, 10 (threshold tuning) |
| §7 API contract, failure rule | 11 |
| §8 Frontend, catalog, timing bar, keyword highlight | 12, 13 |
| §9 Safety | 4 (`open_db`), 11 (localhost, CORS), 0/14 (key handling) |
| §10 Dataset | 3 |
| §11 Testing | every task; 14 (e2e) |
| §12 Build order and gates | 1 (Gate 1), 10 (Gate 2) |

Deviations from the spec, deliberate: `Kpi` takes `{label, field}` and reads row 0 rather than carrying `{value, format}`; rows reach components through React context rather than json-render `$state` (same effect — sent once — without copying 5,000 rows into renderer state); `Panel` props gain `panelIndex` so the alternates strip can address its panel.
