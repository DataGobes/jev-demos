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
