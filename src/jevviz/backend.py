"""Judgment backends: the real TypeSafe Jev API and a deterministic offline stand-in."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Protocol

from jevviz.types import Answer, JudgeResult, Question

_ID_HINTS = ("_id", "id", "zip", "code", "postcode", "sku", "number")
_WORD = re.compile(r"[a-z]+")
_STOP = frozenset(["a", "an", "the", "is", "are", "of", "in", "on", "for", "with", "and", "or", "to", "how", "what", "which", "by", "this", "that"])
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
        return JudgeResult(answers=answers, input_tokens=resp.usage.input_tokens or 0)

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
