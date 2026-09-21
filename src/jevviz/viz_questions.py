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
