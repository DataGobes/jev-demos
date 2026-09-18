"""Question definitions and rubric loading for semantic SQL judgments."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Question:
    """A single judgment request: a noul, score, or choice question."""

    kind: Literal["noul", "score", "choice"]
    instructions: str
    levels: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    labels: tuple[str, ...] = field(
        default=(), compare=False
    )  # display only; not part of key()

    def __post_init__(self) -> None:
        if not self.instructions or not self.instructions.strip():
            raise ValueError("instructions must be non-empty")
        if self.kind == "score" and len(self.levels) < 2:
            raise ValueError("score questions need at least 2 levels")
        if self.labels and len(self.labels) != len(self.levels):
            raise ValueError("labels must match levels one-to-one")
        if self.kind == "choice" and not (2 <= len(self.options) <= 255):
            raise ValueError("choice questions need between 2 and 255 options")

    def key(self) -> str:
        """Stable identity string for caching, independent of object identity."""
        return "|".join(
            [
                self.kind,
                self.instructions,
                "\x1e".join(self.levels),
                "\x1e".join(self.options),
            ]
        )


def _question_from_table(name: str, table: dict) -> Question:
    instructions = table.get("instructions")
    if not isinstance(instructions, str):
        raise ValueError(f"rubric {name!r} is missing string 'instructions'")  # noqa: TRY004
    levels = table.get("levels")
    options = table.get("options")
    if levels is not None:
        if not isinstance(levels, list):
            raise ValueError(f"rubric {name!r} 'levels' must be a list")
        labels = tuple(table.get("labels", ()))
        return Question(
            kind="score", instructions=instructions, levels=tuple(levels), labels=labels
        )
    if options is not None:
        if not isinstance(options, list):
            raise ValueError(f"rubric {name!r} 'options' must be a list")
        return Question(
            kind="choice", instructions=instructions, options=tuple(options)
        )
    return Question(kind="noul", instructions=instructions)


def load_rubrics(path: Path | None = None) -> dict[str, Question]:
    """Load named rubrics from a TOML file (default: packaged rubrics.toml)."""
    if path is None:
        data = resources.files("semsql").joinpath("rubrics.toml").read_bytes()
    else:
        data = Path(path).read_bytes()
    parsed = tomllib.loads(data.decode("utf-8"))
    return {name: _question_from_table(name, table) for name, table in parsed.items()}
