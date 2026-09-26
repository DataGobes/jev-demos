"""Request layouts ("pack styles"): how one or more records share one Jev request.

Jev reads the `state` once and judges every question against it independently. A record can
therefore live in two places in a packed request:

- in the shared state, with each question pointing at its record by path (`rows`). Every other
  record is then a distractor, and the model must bind the right fields to the right row;
  accuracy falls as the pack grows (returns recall 1.00 at pack=1, 0.67 at 8, 0.42 at 32);
- inside its own question's structured `instructions`, next to the sentence being judged
  (`nested`, `inline`) -- the pattern the TypeSafe Noul docs use for per-candidate checks. No
  question can see another's record, so the answer does not depend on the pack size.

The shared state for the second kind is empty on purpose: any text there is read as evidence.
A neutral-sounding "Data-quality check ..." note measurably pushed borderline rows towards
"defect". See docs/eval-results.md, "Pack layouts".

Every style maps `states` (JSON strings, one per record) to one request: a state plus one Noul
question per record, answered under the returned ids in record order.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from typesafe_sdk import Noul

from jevdbt.questions import Question

SHARED_STATE: Any = ""

_COLUMN_REF = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")

Request = tuple[Any, dict[str, Noul], list[str]]


def _rewrite(text: str | None, prefix: str) -> str | None:
    if text is None:
        return None
    return _COLUMN_REF.sub(lambda m: f"`{prefix}{m.group(1)}`", text)


def _criteria(true: str | None, false: str | None) -> dict[str, str | None] | None:
    if true is None and false is None:
        return None
    return {"true": true, "false": false}


def _noul(question: Question) -> Noul:
    return Noul(
        instructions=question.instructions,
        criteria=_criteria(question.criteria_true, question.criteria_false),
    )


def _ids(n: int) -> list[str]:
    return [f"r{i:03d}" for i in range(n)]


def single(states: list[str], question: Question) -> Request:
    """One record as the whole state: the unpacked layout (pack=1)."""
    if len(states) != 1:
        raise ValueError("single style takes exactly one record")
    return json.loads(states[0]), {"q": _noul(question)}, ["q"]


def rows(states: list[str], question: Question) -> Request:
    """Records nested under `rows.rNNN` in state; each question is scoped to its path."""
    if len(states) == 1:
        return single(states, question)
    ids = _ids(len(states))
    state = {"rows": {rid: json.loads(s) for rid, s in zip(ids, states, strict=True)}}
    return state, {rid: _noul(question.for_packed_row(rid)) for rid in ids}, ids


def nested(states: list[str], question: Question) -> Request:
    """Each question carries its record under `record`; column refs become `record.<column>`."""
    ids = _ids(len(states))
    questions = {
        rid: Noul(
            instructions={
                "record": json.loads(s),
                "question": _rewrite(question.instructions, "record."),
            },
            criteria=_criteria(
                _rewrite(question.criteria_true, "record."),
                _rewrite(question.criteria_false, "record."),
            ),
        )
        for rid, s in zip(ids, states, strict=True)
    }
    return SHARED_STATE, questions, ids


def inline(states: list[str], question: Question) -> Request:
    """Like `nested`, with the record's columns beside the sentence, which is sent verbatim."""
    ids = _ids(len(states))
    questions = {}
    for rid, s in zip(ids, states, strict=True):
        record = json.loads(s)
        if "question" in record:
            raise ValueError("inline style cannot carry a column named 'question'; use nested")
        questions[rid] = Noul(
            instructions={**record, "question": question.instructions},
            criteria=_criteria(question.criteria_true, question.criteria_false),
        )
    return SHARED_STATE, questions, ids


STYLES: dict[str, Callable[[list[str], Question], Request]] = {
    "single": single,
    "rows": rows,
    "nested": nested,
    "inline": inline,
}
