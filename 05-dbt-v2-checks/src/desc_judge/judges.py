"""The judge interface, and the deterministic mock that stands in for Jev.

Swapping judges is a one-class change: write a class with `id` and `judge()`, and register it
in `JUDGES`. Nothing else in the package knows which judge it is talking to.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ColumnFacts:
    """Everything a judge sees about one column, read from the dbt information schema."""

    unique_id: str  # the model's unique_id, e.g. model.desc_checks.stg_orders
    column_name: str
    data_type: str | None
    description: str
    sql: str | None  # the model's compiled SQL (raw SQL if it was never compiled)

    @property
    def fingerprint(self) -> str:
        """Cache key for a verdict: a hash of exactly what the judge sees.

        Unchanged (name, type, description, sql) means an unchanged verdict, so the column is
        never sent to the judge again. The model id is left out on purpose: the same column
        with the same SQL gets the same verdict wherever it is.
        """
        payload = json.dumps(
            [self.column_name, self.data_type, self.description, self.sql],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class Verdict:
    ok: bool  # True = the description matches the column
    reason: str
    score: float | None = None  # a judge that returns a probability puts it here


class Judge(Protocol):
    # Part of the cache key. Change it whenever a verdict could change for the same input
    # (another model, prompt or threshold), so stale verdicts are never reused.
    id: str

    def judge(self, items: Sequence[ColumnFacts]) -> list[Verdict]:
        """One verdict per item, in order. Batched so a remote judge can pack requests."""
        ...


# Keep in step with project/macros/mock_judge.sql and project/checks/*_macro.sql.
STOPWORDS = frozenset(
    ["the", "and", "for", "with", "from", "into", "per", "was", "were", "are", "this", "that", "its", "their", "which"]
)


def key_noun(description: str) -> str | None:
    """The description's last word of 3+ characters that is not a stopword."""
    words = re.sub(r"[^a-z0-9 ]", " ", description.lower()).split()
    content = [w for w in words if len(w) >= 3 and w not in STOPWORDS]
    return content[-1] if content else None


class MockJudge:
    """Deterministic stand-in: a mismatch when the key noun is in neither the name nor the SQL.

    It is a keyword rule, not a judgment. It misses a description that uses the right words
    for the wrong thing ("most recent order" on a min() column), which is what Jev is for.
    """

    id = "mock-v1"

    def judge(self, items: Sequence[ColumnFacts]) -> list[Verdict]:
        return [self._one(item) for item in items]

    @staticmethod
    def _one(item: ColumnFacts) -> Verdict:
        noun = key_noun(item.description)
        if noun is None:
            return Verdict(True, "no key noun to compare")
        if noun in item.column_name.lower():
            return Verdict(True, f"'{noun}' is in the column name")
        if item.sql and re.search(rf"\b{re.escape(noun)}\b", item.sql.lower()):
            return Verdict(True, f"'{noun}' is in the model SQL")
        return Verdict(False, f"key noun '{noun}' is in neither the column name nor the SQL")


# Adding Jev: write `class JevJudge` with an `id` (e.g. "jev-<model>-<prompt version>") and a
# `judge()` that sends the batch to Jev and maps each probability to a Verdict, then add it here.
JUDGES: dict[str, type[Judge]] = {"mock": MockJudge}
