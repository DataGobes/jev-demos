"""Side-by-side view of two semantic-test runs at different pack sizes, for the packing recording.

dbt overwrites the stored failures and `jev_last_run` on every run, so `save` copies what a run
produced (its stats and the rows each test flagged) to `jaffle_shop/target/packing_compare/` right
after it finishes. `show` then puts two runs next to each other: requests, wall time and cost,
plus precision/recall per test against the golden key. The speed-up line is computed from the two
runs, never assumed.

Either side of `show` can also be a logged `scripts/pack_bench.py` run (a path to its JSON). The
recording uses the committed live one-row-per-request run, `eval/pack_bench/single_p1_a.json`, so
it doesn't have to spend a minute re-running it on camera. That run called Jev directly on the
same 1,057 rows and questions; its rows are flagged here with each test's own threshold, and it is
labelled "logged" in the table.

    uv run python scripts/packing_compare.py save pack64    # after a JEV_PACK=64 run
    uv run python scripts/packing_compare.py recap          # one line: the logged run's cost
    uv run python scripts/packing_compare.py show pack64    # vs the logged reference
    uv run python scripts/packing_compare.py show eval/pack_bench/single_p1_a.json pack64

A SIMULATED run is labelled as such: its numbers are wiring checks, not model results.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import duckdb
from rich.console import Console
from rich.table import Table

from jevdbt.stats import PRICE_PER_MTOK_USD, format_cost

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "jaffle_shop" / "jaffle_shop.duckdb"
SAVE_DIR = ROOT / "jaffle_shop" / "target" / "packing_compare"
AUDIT_SCHEMA = "main_dbt_test__audit"
REFERENCE = ROOT / "eval" / "pack_bench" / "single_p1_a.json"
SHORT_NAMES = {
    "customers_full_name_is_a_person": "customers",
    "returns_comment_matches_reason_code": "returns",
    "reviews_body_matches_stars": "reviews",
    "tickets_body_has_no_pii": "tickets",
}

_spec = importlib.util.spec_from_file_location("_pc_score", Path(__file__).parent / "score.py")
score = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(score)

_spec = importlib.util.spec_from_file_location("_pc_bench", Path(__file__).parent / "pack_bench.py")
pack_bench = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["_pc_bench"] = pack_bench  # its @dataclass looks the module up while loading
_spec.loader.exec_module(pack_bench)


def capture(con: duckdb.DuckDBPyConnection) -> dict:
    """The last run's stats plus the ids each semantic test flagged."""
    try:
        row = con.execute(f"select stats from {AUDIT_SCHEMA}.jev_last_run").fetchone()
    except duckdb.CatalogException:
        row = None
    if row is None or row[0] is None:
        raise SystemExit("no jev_last_run table: run `dbt test --select tag:semantic` first")
    flagged = {
        name: sorted(score.load_flagged(con, AUDIT_SCHEMA, name, id_col))
        for name, id_col in score.TESTS.items()
    }
    return {"stats": json.loads(row[0]), "flagged": flagged}


def from_bench(bench: dict, thresholds: dict[str, float]) -> dict:
    """A logged pack_bench run in the same shape `capture` produces."""
    flagged = {
        name: sorted(int(i) for i, p in bench["tests"][name].items()
                     if p is not None and p >= thresholds[name])
        for name in SHORT_NAMES
    }
    stats = {
        "pack": bench["pack"],
        "requests": bench["requests"],
        "wall_seconds": bench["seconds"],
        "input_tokens": bench["input_tokens"],
        "errors": bench["errors"],
        "simulated": False,  # pack_bench refuses to run without a key
        "logged": True,
    }
    return {"stats": stats, "flagged": flagged}


def load_run(spec: str) -> dict:
    """A saved label (`pack64`) or a path to a pack_bench JSON file."""
    path = Path(spec)
    if not path.is_absolute():
        path = ROOT / spec
    if spec.endswith(".json"):
        if not path.exists():
            raise SystemExit(f"no such logged run: {spec}")
        thresholds = {t.name: t.threshold for t in pack_bench.load_tests()}
        return from_bench(json.loads(path.read_text()), thresholds)
    saved = SAVE_DIR / f"{spec}.json"
    if not saved.exists():
        raise SystemExit(f"no saved run {spec!r}: run `packing_compare.py save {spec}`")
    return json.loads(saved.read_text())


def recap_line(run: dict) -> str:
    s = run["stats"]
    return f"{s['requests']:,} requests · {s['wall_seconds']:.1f} s · {format_cost(_cost(s))}"


def pack_label(stats: dict) -> str:
    pack = stats.get("pack", 1)
    label = "1 row / request" if pack == 1 else f"{pack} rows / request"
    return f"{label} (logged)" if stats.get("logged") else label


def comparison(a: dict, b: dict, golden: dict) -> tuple[list[tuple[str, str, str]], str]:
    """Table rows (label, run a, run b) and a one-line speed-up summary, b relative to a."""
    sa, sb = a["stats"], b["stats"]
    rows = [
        ("requests", f"{sa['requests']:,}", f"{sb['requests']:,}"),
        ("wall time", f"{sa['wall_seconds']:.1f} s", f"{sb['wall_seconds']:.1f} s"),
        ("input tokens", f"{sa['input_tokens']:,}", f"{sb['input_tokens']:,}"),
        ("cost", format_cost(_cost(sa)), format_cost(_cost(sb))),
    ]
    for name, short in SHORT_NAMES.items():
        gold = golden.get(name, {})
        ma = score.metrics(set(a["flagged"][name]), gold)
        mb = score.metrics(set(b["flagged"][name]), gold)
        rows.append(
            (
                f"{short}  P / R",
                f"{ma.precision:.2f} / {ma.recall:.2f}",
                f"{mb.precision:.2f} / {mb.recall:.2f}",
            )
        )
    parts = []
    if sb["wall_seconds"] > 0:
        parts.append(f"{sa['wall_seconds'] / sb['wall_seconds']:.0f}× faster")
    if sb["requests"] > 0:
        parts.append(f"{sa['requests'] / sb['requests']:.0f}× fewer requests")
    if _cost(sb) > 0:
        parts.append(f"{_cost(sa) / _cost(sb):.1f}× cheaper")
    return rows, " · ".join(parts)


def _cost(stats: dict) -> float:
    return stats["input_tokens"] * PRICE_PER_MTOK_USD / 1_000_000


def warnings(a: dict, b: dict) -> list[str]:
    """Anything that makes the comparison not a like-for-like, live, error-free result."""
    out = []
    if a["stats"].get("simulated") or b["stats"].get("simulated"):
        out.append("SIMULATED: no API key, so these numbers are wiring checks, not Jev results")
    for label, run in (("first", a), ("second", b)):
        if run["stats"].get("errors"):
            out.append(f"{label} run reported {run['stats']['errors']} errors")
        if run["stats"].get("sent", 0) < run["stats"].get("unique", 0):
            out.append(f"{label} run was partly served from cache")
    return out


def render(console: Console, a: dict, b: dict, golden: dict) -> None:
    rows, speedup = comparison(a, b, golden)
    for w in warnings(a, b):
        console.print(f"[bold black on yellow] {w} [/]")
    table = Table(title="Same tests, same rows, same answer key", title_style="bold")
    table.add_column("")
    table.add_column(pack_label(a["stats"]), justify="right")
    table.add_column(pack_label(b["stats"]), justify="right", style="bold green")
    for i, (label, va, vb) in enumerate(rows):
        table.add_row(label, va, vb, end_section=(i == 3))
    console.print(table)
    if speedup:
        simulated = a["stats"].get("simulated") or b["stats"].get("simulated")
        tag = "  [black on yellow] SIMULATED [/]" if simulated else ""
        console.print(f"\n[bold]{speedup}[/bold]{tag}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save", help="save the last run under a label")
    s.add_argument("label")
    v = sub.add_parser("show", help="compare two runs: saved labels or pack_bench JSON paths")
    v.add_argument("runs", nargs="+", metavar="run", help="one run (compared with the logged "
                   "one-row-per-request reference) or two runs")
    r = sub.add_parser("recap", help="one-line summary of a logged run (default: the reference)")
    r.add_argument("run", nargs="?", default=str(REFERENCE.relative_to(ROOT)))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)

    if args.cmd == "save":
        con = duckdb.connect(str(args.db), read_only=True)
        try:
            data = capture(con)
        finally:
            con.close()
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        (SAVE_DIR / f"{args.label}.json").write_text(json.dumps(data, indent=1))
        return 0

    if args.cmd == "recap":
        print(recap_line(load_run(args.run)))
        return 0

    if len(args.runs) > 2:
        parser.error("show takes one or two runs")
    specs = args.runs if len(args.runs) == 2 else [str(REFERENCE.relative_to(ROOT)), *args.runs]
    first, second = (load_run(spec) for spec in specs)
    render(Console(), first, second, score.load_golden(score.GOLDEN_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
