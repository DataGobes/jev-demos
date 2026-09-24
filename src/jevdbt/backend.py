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
