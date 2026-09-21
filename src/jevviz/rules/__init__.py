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
    # Invariant rank.py relies on: ids are zero-padded in this pre-rank `ordered`
    # sequence, so lexicographic string order over ids equals pre-rank order.
    return [replace(c, id=f"c{i:02d}") for i, c in enumerate(ordered)], total


from jevviz.rules import (  # noqa: F401  (import for registration side effect)
    advanced,
    basic,
)
