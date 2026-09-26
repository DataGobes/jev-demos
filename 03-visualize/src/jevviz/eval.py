"""Golden-set eval: does Jev beat 'first valid candidate'? This is the project's go/no-go gate."""

from __future__ import annotations

import asyncio
import sys
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from dotenv import load_dotenv

from jevviz.backend import Backend, make_backend
from jevviz.db import open_db, run_query
from jevviz.pipeline import visualize
from jevviz.profile import profile
from jevviz.rules import enumerate_candidates


@dataclass(frozen=True)
class GoldenCase:
    name: str
    sql: str
    intent: str
    accept: list[str]


@dataclass
class EvalReport:
    top1: float
    top3: float
    baseline_top1: float
    rows: list[dict]


def load_golden(path: Path | None = None) -> list[GoldenCase]:
    raw = Path(path).read_bytes() if path else resources.files("jevviz").joinpath("golden.toml").read_bytes()
    return [GoldenCase(name, t["sql"], t["intent"], list(t["accept"])) for name, t in tomllib.loads(raw.decode()).items()]


def matches(kind: str, columns: tuple[str, ...], accept: list[str]) -> bool:
    for rule in accept:
        want_kind, _, cols = rule.partition(":")
        if want_kind == kind and set(filter(None, cols.split("+"))) <= set(columns):
            return True
    return False


async def run_eval(db_path: Path | str, backend: Backend, max_questions: int) -> EvalReport:
    con = open_db(db_path)
    rows = []
    for case in load_golden():
        result = run_query(con, case.sql)
        candidates, _ = enumerate_candidates(profile(result))
        by_id = {c.id: c for c in candidates}
        first = next(c for c in candidates if c.kind != "kpi")
        out = await visualize(case.sql, result, [case.intent], backend, None, max_questions)
        panel = out.panels[0]
        picks = [panel["chosen"]["id"], *[a["id"] for a in panel["alternates"]]][:3]
        hit = [matches(by_id[i].kind, by_id[i].columns, case.accept) for i in picks]
        rows.append({"name": case.name, "chosen": by_id[picks[0]].kind, "p": panel["chosen"]["p"],
                     "top1": hit[0], "top3": any(hit), "baseline": matches(first.kind, first.columns, case.accept)})
    n = len(rows)
    return EvalReport(sum(r["top1"] for r in rows) / n, sum(r["top3"] for r in rows) / n,
                      sum(r["baseline"] for r in rows) / n, rows)


if __name__ == "__main__":
    load_dotenv()
    db = sys.argv[1] if len(sys.argv) > 1 else "jevviz.duckdb"
    backend = make_backend()
    report = asyncio.run(run_eval(db, backend, int(sys.argv[2]) if len(sys.argv) > 2 else 72))
    print(f"backend={backend.name} simulated={backend.simulated}")
    for r in report.rows:
        print(f"{'✓' if r['top1'] else '✗'} {r['name']:28s} chose={r['chosen']:12s} p={r['p']:.2f} top3={r['top3']} baseline={r['baseline']}")
    print(f"\nJev top-1 {report.top1:.0%} · top-3 {report.top3:.0%} · rules-only top-1 {report.baseline_top1:.0%}")
