"""profile -> candidates -> one batched judgment -> rank -> spec."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from jevviz.backend import Backend
from jevviz.cache import Cache
from jevviz.db import QueryResult
from jevviz.profile import profile
from jevviz.rank import rank_panels
from jevviz.rules import enumerate_candidates
from jevviz.spec import assemble_spec, panel_payload
from jevviz.types import Answer, Question
from jevviz.viz_questions import build_questions, effective_intents, state_for

PRICE_PER_MTOK_USD = 0.042


@dataclass
class VizOutcome:
    spec: dict
    panels: list[dict]
    ms: dict
    input_tokens: int
    usd: float
    scored: str
    cache: str
    simulated: bool
    error: str | None


def _chunks(qs: dict[str, Question], size: int) -> list[dict[str, Question]]:
    items = list(qs.items())
    return [dict(items[i:i + size]) for i in range(0, len(items), size)]


async def visualize(sql: str, result: QueryResult, intents: list[str], backend: Backend,
                    cache: Cache | None, max_questions: int) -> VizOutcome:
    t0 = time.perf_counter()
    prof = profile(result)
    t1 = time.perf_counter()
    candidates, total = enumerate_candidates(prof)
    t2 = time.perf_counter()

    intents = effective_intents(intents)
    questions = build_questions(prof, candidates, intents)
    state, state_hash = state_for(sql, prof), prof.hash()
    answers: dict[str, Answer] = cache.get_many(backend.name, state_hash, questions) if cache else {}
    missing = {qid: q for qid, q in questions.items() if qid not in answers}
    tokens, error = 0, None
    if missing:
        results = await asyncio.gather(*(backend.judge(state, chunk) for chunk in _chunks(missing, max_questions)))
        fresh: dict[str, Answer] = {}
        for r in results:
            fresh.update(r.answers)
            tokens += r.input_tokens
            error = error or r.error
        if cache and fresh:
            cache.put_many(backend.name, state_hash, questions, fresh)
        answers.update(fresh)
    t3 = time.perf_counter()

    panels = rank_panels(candidates, intents, answers)
    scored = sum(c.kind != "table" for c in candidates)
    # R4: `total` (from enumerate_candidates) counts every rule output including the
    # single `table` candidate, so the right-hand side excludes it — an untruncated
    # run reads "9 of 9", never a permanent off-by-one that looks like truncation.
    return VizOutcome(
        spec=assemble_spec(panels), panels=panel_payload(panels),
        ms={"profile": round((t1 - t0) * 1000, 1), "enumerate": round((t2 - t1) * 1000, 1), "jev": round((t3 - t2) * 1000, 1)},
        input_tokens=tokens, usd=round(tokens * PRICE_PER_MTOK_USD / 1_000_000, 6),
        scored=f"{scored} of {total - 1}", cache="miss" if missing else "hit",
        simulated=backend.simulated, error=error,
    )
