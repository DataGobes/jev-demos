"""Turn Jev answers into chosen panels. Policy is explicit and isolated here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jevviz.types import Answer, Candidate

STRONG = 0.6     # confirmed on the seed golden set, see docs/eval-results.md
WEAK = 0.3       # spec default; not exercised by the seed golden set
ID_NOUL = 0.5    # confirmed on the seed golden set, see docs/eval-results.md


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
