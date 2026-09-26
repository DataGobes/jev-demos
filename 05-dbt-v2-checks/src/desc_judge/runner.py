"""Decide which columns to judge, judge only cache misses, and report failures as rows."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .cache import VerdictCache
from .judges import ColumnFacts, Judge, Verdict


@dataclass
class Failure:
    unique_id: str
    column_name: str
    description: str
    message: str


@dataclass
class Report:
    failures: list[Failure] = field(default_factory=list)
    in_scope: int = 0  # documented columns this run is responsible for
    judged: int = 0  # sent to the judge this run
    cached: int = 0  # answered from the cache
    unchanged: int = 0  # left out: same fingerprint as the baseline
    undocumented: int = 0  # left out: no description to judge


def changed_only(
    facts: Sequence[ColumnFacts], baseline: Iterable[ColumnFacts]
) -> tuple[list[ColumnFacts], int]:
    """Column-level `state:modified`: keep columns that are new or differ from the baseline.

    dbt's own `state:modified` does not compare descriptions (dbt CHANGELOG: "`description`
    is still not compared"), so a description-only edit would never be selected by it. The
    fingerprint covers name, type, description and SQL, which is exactly what a judge sees.
    """
    seen = {(f.unique_id, f.column_name, f.fingerprint) for f in baseline}
    kept = [f for f in facts if (f.unique_id, f.column_name, f.fingerprint) not in seen]
    return kept, len(facts) - len(kept)


def evaluate(
    facts: Sequence[ColumnFacts],
    judge: Judge,
    cache: VerdictCache,
    *,
    select: set[str] | None = None,
    baseline: Sequence[ColumnFacts] | None = None,
    batch_size: int = 32,
) -> Report:
    report = Report()
    todo = [f for f in facts if select is None or f.unique_id in select]
    if baseline is not None:
        todo, report.unchanged = changed_only(todo, baseline)

    documented = [f for f in todo if f.description.strip()]
    report.undocumented = len(todo) - len(documented)
    report.in_scope = len(documented)

    verdicts: dict[int, Verdict] = {}
    misses: list[int] = []
    for i, f in enumerate(documented):
        hit = cache.get(judge.id, f.fingerprint)
        if hit is None:
            misses.append(i)
        else:
            verdicts[i] = hit
    report.cached = len(verdicts)

    # Identical columns (same fingerprint) are judged once per run, not once per occurrence.
    unique: dict[str, int] = {}
    for i in misses:
        unique.setdefault(documented[i].fingerprint, i)
    to_send = list(unique.values())
    for start in range(0, len(to_send), batch_size):
        batch = [documented[i] for i in to_send[start : start + batch_size]]
        results = judge.judge(batch)
        if len(results) != len(batch):
            raise RuntimeError(f"judge {judge.id} returned {len(results)} verdicts for {len(batch)} items")
        for item, verdict in zip(batch, results):
            cache.put(judge.id, item.fingerprint, verdict)
    report.judged = len(to_send)
    for i in misses:
        verdicts[i] = cache.get(judge.id, documented[i].fingerprint)  # type: ignore[assignment]

    for i, f in enumerate(documented):
        v = verdicts[i]
        if not v.ok:
            report.failures.append(Failure(f.unique_id, f.column_name, f.description, v.reason))
    return report
