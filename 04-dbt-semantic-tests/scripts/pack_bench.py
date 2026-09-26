"""Pack-style benchmark: how accurately each request layout judges the four semantic tests.

Calls Jev directly (no dbt) on the same rows and questions the `jev_expect` tests send, and
saves every row's probability, so layouts can be compared with each other row by row, not
only on the pass/fail gate. Live only: a simulated backend's numbers mean nothing here.

    uv run python scripts/pack_bench.py run --style single --pack 1 --tag a
    uv run python scripts/pack_bench.py run --style inline --pack 16
    uv run python scripts/pack_bench.py report            # table of every saved run

Needs the models built (`dbt build --exclude tag:semantic`) and `TYPESAFE_API_KEY` in `.env`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb
import yaml

from jevdbt.packing import STYLES

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "jaffle_shop" / "jaffle_shop.duckdb"
SCHEMA_PATH = ROOT / "jaffle_shop" / "models" / "staging" / "schema.yml"
OUT_DIR = ROOT / "eval" / "pack_bench"
REFERENCE = "single_p1"  # the unpacked layout every other run is compared against

_spec = importlib.util.spec_from_file_location("score", ROOT / "scripts" / "score.py")
score = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score)


@dataclass(frozen=True)
class SemanticTest:
    name: str
    model: str
    column: str
    context: list[str]
    threshold: float
    question_json: str


def load_tests(path: Path = SCHEMA_PATH) -> list[SemanticTest]:
    """Every `jev_expect` test in schema.yml, with the question exactly as the macro builds it."""
    tests = []
    for model in yaml.safe_load(path.read_text())["models"]:
        for col in model.get("columns", []):
            for t in col.get("data_tests", []):
                if not isinstance(t, dict) or "jev_expect" not in t:
                    continue
                spec = t["jev_expect"]
                args = spec["arguments"]
                question = {"instructions": args["fails_if"]}
                if "criteria" in args:
                    question["criteria"] = {str(k).lower(): v for k, v in args["criteria"].items()}
                tests.append(
                    SemanticTest(
                        name=spec["name"],
                        model=model["name"],
                        column=col["name"],
                        context=list(args.get("context", [])),
                        threshold=float(args.get("threshold", 0.5)),
                        question_json=json.dumps(question),
                    )
                )
    return tests


def load_states(con: duckdb.DuckDBPyConnection, test: SemanticTest) -> dict[int, str]:
    """id -> state JSON, built with the same `to_json(struct_pack(...))` the macro uses."""
    id_col = score.TESTS[test.name]
    fields = ", ".join(f"{f} := {f}" for f in [test.column, *test.context])
    rows = con.execute(
        f"select {id_col}, to_json(struct_pack({fields})) from {test.model} "
        f"where {test.column} is not null order by {id_col}"
    ).fetchall()
    return {int(i): s for i, s in rows}


def run(style: str, pack: int, tag: str, out_dir: Path, shared: str | None = None) -> Path:
    from dotenv import find_dotenv, load_dotenv

    from jevdbt.backend import JevBackend
    from jevdbt.questions import Question
    from jevdbt.scorer import Scorer
    from jevdbt.stats import Stats

    load_dotenv(find_dotenv(usecwd=True))
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is not set: this benchmark only runs live")
    if style == "single" and pack != 1:
        raise SystemExit("style 'single' is the unpacked layout: use --pack 1")

    if shared is not None:
        import jevdbt.packing

        jevdbt.packing.SHARED_STATE = json.loads(shared)
    stats = Stats()
    backend = JevBackend(pack_style=style)
    scorer = Scorer(backend, stats, None, pack=pack, pack_style=style, concurrency=32)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    result: dict = {"style": style, "pack": pack, "tag": tag, "shared": shared, "tests": {}}
    started = time.perf_counter()
    try:
        for test in load_tests():
            states = load_states(con, test)
            ids = list(states)
            question = Question.from_json(test.question_json)
            values = scorer.score_many([states[i] for i in ids], question)
            result["tests"][test.name] = {str(i): v for i, v in zip(ids, values, strict=True)}
            print(f"  {test.name}: {len(ids)} rows", file=sys.stderr)
    finally:
        con.close()
        scorer.close()
    snap = stats.snapshot()
    result.update(
        seconds=round(time.perf_counter() - started, 1),
        requests=snap.requests,
        input_tokens=snap.input_tokens,
        cost_usd=snap.cost_usd,
        errors=snap.errors,
        last_error=scorer.backend.last_error,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{style}_p{pack}_{tag}.json"
    path.write_text(json.dumps(result, indent=1))
    return path


def auc(probs: dict[int, float], defects: set[int]) -> float:
    """Rank AUC of defect vs non-defect rows: threshold-free separation of the golden defects."""
    pos = [p for i, p in probs.items() if i in defects]
    neg = [p for i, p in probs.items() if i not in defects]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def summarize(run_data: dict, reference: dict | None, golden: dict, tests: list[SemanticTest]):
    """Per-test metrics for one saved run; drift is measured against `reference`."""
    rows = []
    for test in tests:
        raw = run_data["tests"][test.name]
        probs = {int(i): v for i, v in raw.items() if v is not None}
        gold = golden.get(test.name, {})
        defects = {i for i, label in gold.items() if label == "defect"}
        flagged = {i for i, p in probs.items() if p >= test.threshold}
        m = score.metrics(flagged, gold)
        drift = flips = None
        if reference is not None:
            ref = {int(i): v for i, v in reference["tests"][test.name].items() if v is not None}
            common = probs.keys() & ref.keys()
            drift = sum(abs(probs[i] - ref[i]) for i in common) / len(common)
            flips = sum((probs[i] >= test.threshold) != (ref[i] >= test.threshold) for i in common)
        rows.append(
            {
                "test": test.name,
                "P": m.precision,
                "R": m.recall,
                "F1": m.f1,
                "AUC": auc(probs, defects),
                "drift": drift,
                "flips": flips,
                "missed": sorted(defects - flagged),
                "false_pos": sorted(flagged - defects),
                "none": sum(v is None for v in raw.values()),
            }
        )
    return rows


def report(out_dir: Path) -> None:
    golden = score.load_golden(score.GOLDEN_PATH)
    tests = load_tests()
    runs = sorted(out_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit(f"no saved runs in {out_dir}")
    data = {p.stem: json.loads(p.read_text()) for p in runs}
    ref_key = next((k for k in data if k.startswith(REFERENCE)), None)
    reference = data[ref_key] if ref_key else None
    short = {t.name: t.name.split("_")[0] for t in tests}

    print(f"reference for drift/flips: {ref_key or 'none saved yet'}\n")
    header = "| run | req | tokens | s | " + " | ".join(
        f"{short[t.name]} R · P · AUC · flips" for t in tests
    ) + " | mean drift |"
    print(header)
    print("|" + "---|" * (header.count("|") - 1))
    for key, d in data.items():
        rows = summarize(d, reference if key != ref_key else None, golden, tests)
        cells = []
        for r in rows:
            flips = "-" if r["flips"] is None else str(r["flips"])
            cells.append(f"{r['R']:.2f} · {r['P']:.2f} · {r['AUC']:.3f} · {flips}")
        drifts = [r["drift"] for r in rows if r["drift"] is not None]
        mean_drift = f"{sum(drifts) / len(drifts):.3f}" if drifts else "-"
        err = f" ⚠{d['errors']} err" if d["errors"] else ""
        print(
            f"| {key}{err} | {d['requests']:,} | {d['input_tokens']:,} | {d['seconds']} | "
            + " | ".join(cells)
            + f" | {mean_drift} |"
        )
    print()
    for key, d in data.items():
        rows = summarize(d, reference, golden, tests)
        misses = "; ".join(
            f"{short[r['test']]} missed={r['missed']} fp={r['false_pos']}"
            for r in rows
            if r["missed"] or r["false_pos"]
        )
        print(f"- {key}: {misses or 'no errors'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="judge every row live with one layout and save it")
    r.add_argument("--style", required=True, choices=list(STYLES))
    r.add_argument("--pack", type=int, required=True)
    r.add_argument("--tag", default="a", help="distinguishes repeat runs of the same layout")
    r.add_argument("--shared", default=None, help="JSON to use as the shared state (experiments)")
    sub.add_parser("report", help="print a comparison table of every saved run")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    if args.cmd == "run":
        path = run(args.style, args.pack, args.tag, args.out, args.shared)
        print(f"saved {path.relative_to(ROOT)}")
    else:
        report(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
