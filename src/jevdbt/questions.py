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
