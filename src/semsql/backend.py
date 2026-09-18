"""Judgment backends: the real TypeSafe Jev API and a deterministic demo stand-in."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from dataclasses import dataclass
from typing import Protocol

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score, TypeSafeError

from semsql.questions import Question

Value = float | str


@dataclass
class BatchResult:
    """Outcome of one backend request. `None` marks a row that failed."""

    values: list[Value | None]
    input_tokens: int


class Backend(Protocol):
    name: str
    simulated: bool

    async def judge(self, texts: list[str], question: Question) -> BatchResult: ...

    async def aclose(self) -> None: ...


def _row_id(index: int) -> str:
    return f"r{index:03d}"


def _to_sdk_question(question: Question) -> Noul | Score | Choice:
    if question.kind == "noul":
        return Noul(instructions=question.instructions)
    if question.kind == "score":
        return Score(instructions=question.instructions, criteria=list(question.levels))
    return Choice(instructions=question.instructions, criteria={opt: None for opt in question.options})


def _packed_instructions(row_id: str, instructions: str) -> str:
    return f"Judge ONLY the text in `rows.{row_id}`, ignoring all other rows. {instructions}"


class JevBackend:
    """Backend that calls the real TypeSafe Jev API."""

    def __init__(self, model: str = "jev-latest") -> None:
        self.name = model
        self.simulated = False
        self.last_error: str | None = None
        self._client: AsyncTypeSafeClient | None = None

    def _ensure_client(self) -> AsyncTypeSafeClient:
        if self._client is None:
            self._client = AsyncTypeSafeClient(model=self.name)
        return self._client

    async def judge(self, texts: list[str], question: Question) -> BatchResult:
        client = self._ensure_client()
        try:
            if len(texts) == 1:
                state = texts[0]
                questions = {"q": _to_sdk_question(question)}
                resp = await client.system_one(state, questions)
                answer = resp.answers["q"]
                values: list[Value | None] = [_extract_value(answer, question.kind)]
            else:
                rows = {_row_id(i): text for i, text in enumerate(texts)}
                state = {"rows": rows}
                questions = {}
                for i in range(len(texts)):
                    row_id = _row_id(i)
                    packed = Question(
                        kind=question.kind,
                        instructions=_packed_instructions(row_id, question.instructions),
                        levels=question.levels,
                        options=question.options,
                    )
                    questions[row_id] = _to_sdk_question(packed)
                resp = await client.system_one(state, questions)
                values = [
                    _extract_value(resp.answers[_row_id(i)], question.kind) for i in range(len(texts))
                ]
            return BatchResult(values=values, input_tokens=resp.usage.input_tokens)
        except (TypeSafeError, KeyError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return BatchResult(values=[None] * len(texts), input_tokens=0)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


def _extract_value(answer: object, kind: str) -> Value:
    if kind == "noul":
        return answer.noul  # type: ignore[attr-defined]
    if kind == "score":
        return answer.score  # type: ignore[attr-defined]
    return answer.choice  # type: ignore[attr-defined]


_STOPWORDS_TEXT = (
    "a an the is are was were be been being to of in on for with and or but "
    "this that these those i you he she it we they my your his her its our "
    "their as at by from not no so if than then there here do does did have "
    "has had will would can could should may might just very"
)
_STOPWORDS = frozenset(_STOPWORDS_TEXT.split())

_NEGATIVE_WORDS = frozenset(
    {
        "angry",
        "furious",
        "hate",
        "hates",
        "terrible",
        "worst",
        "refund",
        "cancel",
        "cancelled",
        "disgusted",
        "unacceptable",
        "broken",
        "awful",
        "threat",
        "scam",
        "never",
        "ridiculous",
        "horrible",
        "useless",
        "disappointed",
        "disappointing",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_SUFFIXES = ("ing", "edly", "ed", "es", "s")


def _stem(word: str) -> str:
    for suf in _SUFFIXES:
        if len(word) > len(suf) + 2 and word.endswith(suf):
            return word[: -len(suf)]
    return word


def _tokenize(text: str) -> set[str]:
    return {_stem(w) for w in _TOKEN_RE.findall(text.lower()) if w not in _STOPWORDS}


def _hash_unit(*parts: str) -> float:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class DemoBackend:
    """Deterministic, offline stand-in for JevBackend. Never calls the network."""

    def __init__(self, latency: float | None = None) -> None:
        self.name = "demo"
        self.simulated = True
        self._latency = latency

    def _sleep_for(self, key: str) -> float:
        if self._latency is not None:
            return self._latency
        return 0.12 + _hash_unit(key) * 0.06

    async def judge(self, texts: list[str], question: Question) -> BatchResult:
        await asyncio.sleep(self._sleep_for("\x1f".join(texts) + question.key()))
        values = [self._judge_one(text, question) for text in texts]
        input_tokens = sum(len(t) // 4 for t in texts) + 40 * len(texts)
        return BatchResult(values=values, input_tokens=input_tokens)

    def _judge_one(self, text: str, question: Question) -> Value:
        if question.kind == "noul":
            return self._noul(text, question)
        if question.kind == "score":
            return self._score(text, question)
        return self._choice(text, question)

    def _noul(self, text: str, question: Question) -> float:
        q_tokens = _tokenize(question.instructions)
        t_tokens = _tokenize(text)
        if q_tokens:
            coverage = len(q_tokens & t_tokens) / len(q_tokens)
        else:
            union = q_tokens | t_tokens
            coverage = len(q_tokens & t_tokens) / len(union) if union else 0.0
        squashed = coverage**0.6  # spreads mid-range overlap upward for a punchier signal
        jitter = (_hash_unit(text, question.instructions) - 0.5) * 0.06
        return _clamp(0.05 + 0.9 * squashed + jitter, 0.0, 1.0)

    def _score(self, text: str, question: Question) -> float:
        n = len(question.levels)
        letters = [c for c in text if c.isalpha()]
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters) if letters else 0.0
        exclaim = min(text.count("!"), 5)
        neg_hits = len(_tokenize(text) & _NEGATIVE_WORDS)
        raw = caps_ratio * 3.0 + exclaim * 0.25 + neg_hits * 0.4
        jitter = (_hash_unit(text, question.key()) - 0.5) * 0.3
        level = round(_clamp(raw + jitter, 0.0, 3.0) / 3.0 * (n - 1))
        return float(_clamp(level, 0, n - 1))

    def _choice(self, text: str, question: Question) -> str:
        t_tokens = _tokenize(text)
        best_options: list[str] = []
        best_overlap = -1
        for option in question.options:
            overlap = len(_tokenize(option) & t_tokens)
            if overlap > best_overlap:
                best_overlap = overlap
                best_options = [option]
            elif overlap == best_overlap:
                best_options.append(option)
        if len(best_options) == 1:
            return best_options[0]
        idx = int(_hash_unit(text, question.key()) * len(best_options))
        return best_options[min(idx, len(best_options) - 1)]

    async def aclose(self) -> None:
        return None


def make_backend(*, demo: bool | None = None, model: str = "jev-latest") -> Backend:
    """Build a backend. `demo=None` auto-selects DemoBackend when no API key is set."""
    if demo is None:
        demo = not os.environ.get("TYPESAFE_API_KEY")
    if demo:
        return DemoBackend()
    return JevBackend(model=model)
