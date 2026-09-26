"""Scorecard: compares stored Jev and regex-baseline test failures against the hidden golden key.

Numbers printed here are the ones that go in the public LinkedIn post, so precision matters:
this module contains no invented fallbacks — a missing table or an uncaptured run summary is
reported, never silently papered over.

    uv run python scripts/score.py --run --fresh --mode demo   # smoke, no live calls
    uv run python scripts/score.py --run --mode live --append  # real run, records to docs/

See TESTS below for the four semantic tests scored, and the sibling
`scripts/show_failures.py` for inspecting individual stored failures.
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb
from rich.console import Console

ROOT = Path(__file__).resolve().parents[1]
JAFFLE_DIR = ROOT / "jaffle_shop"
DEFAULT_DB = JAFFLE_DIR / "jaffle_shop.duckdb"
GOLDEN_PATH = ROOT / "eval" / "golden_defects.csv"
DOCS_PATH = ROOT / "docs" / "eval-results.md"

# test name -> id column of the underlying model
TESTS = {
    "customers_full_name_is_a_person": "customer_id",
    "returns_comment_matches_reason_code": "return_id",
    "reviews_body_matches_stars": "review_id",
    "tickets_body_has_no_pii": "ticket_id",
}

# models that must already be built (via `dbt build --exclude tag:semantic`) before
# `dbt test --select tag:semantic tag:baseline` can run
REQUIRED_MODELS = {"stg_customers", "stg_returns", "stg_reviews", "stg_tickets"}

DBT_TEST_CMD = "uv run dbt test --profiles-dir . --select tag:semantic tag:baseline"
DBT_BUILD_CMD = "uv run dbt build --profiles-dir . --exclude tag:semantic"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_MODE_PACK_RE = re.compile(r"(LIVE|SIMULATED)\s+\S+\s+pack=(\d+(?:/\w+)?)")


@dataclass(frozen=True)
class Metrics:
    flagged: int
    tp: int
    fp: int
    fn: int
    hard_neg_flagged: int
    precision: float
    recall: float
    f1: float


def load_golden(path: str | Path) -> dict[str, dict[int, str]]:
    """`eval/golden_defects.csv` (test_name, id, label, note) -> {test_name: {id: label}}."""
    golden: dict[str, dict[int, str]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            golden.setdefault(row["test_name"], {})[int(row["id"])] = row["label"]
    return golden


def metrics(flagged: set[int], golden: dict[int, str]) -> Metrics:
    """Precision/recall/F1 of `flagged` ids against a test's {id: label} golden key."""
    flagged = set(flagged)
    defects = {i for i, label in golden.items() if label == "defect"}
    hard_negs = {i for i, label in golden.items() if label == "hard_negative"}
    tp = len(flagged & defects)
    fp = len(flagged - defects)
    fn = len(defects - flagged)
    hard_neg_flagged = len(flagged & hard_negs)
    precision = tp / len(flagged) if flagged else 0.0
    recall = tp / len(defects) if defects else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return Metrics(len(flagged), tp, fp, fn, hard_neg_flagged, precision, recall, f1)


def parse_summary(stdout: str) -> str | None:
    """Strip ANSI codes and return the `Jev · ...` tail of the last matching line, else None."""
    clean = _ANSI_RE.sub("", stdout)
    line = None
    for candidate in clean.splitlines():
        if "Jev · " in candidate:
            line = candidate
    if line is None:
        return None
    return line[line.index("Jev · ") :].strip()


def read_last_run_summary(con: duckdb.DuckDBPyConnection) -> str | None:
    """The summary line from `main_dbt_test__audit.jev_last_run`, written by the
    `jev_summary` on-run-end macro, or None if it doesn't exist (project never ran, or the
    dbt-core version predates it). Used when this script is called without --run, so the
    gate + mode still show. It reflects the last dbt invocation that made judgments -- the
    same invocation the stored-failure tables scored below were written by, since both are
    written within that run.
    """
    try:
        row = con.execute("select stats from main_dbt_test__audit.jev_last_run").fetchone()
    except duckdb.CatalogException:
        return None
    if row is None or row[0] is None:
        return None
    return json.loads(row[0]).get("summary")


GateResults = dict[str, tuple[Metrics, Metrics]]


def gate(results: GateResults, summary: str | None) -> tuple[bool, list[str]]:
    """Gate: captured, LIVE, error-free, and Jev beats P/R/F1 thresholds on every test."""
    reasons: list[str] = []
    if summary is None:
        reasons.append("summary not captured (run with --run)")
    else:
        if "LIVE" not in summary:
            reasons.append("run was not LIVE")
        if " errors" in summary:
            reasons.append("run reported errors")
    for name, (jev, baseline) in results.items():
        if jev.precision < 0.85:
            reasons.append(f"{name}: Jev precision {jev.precision:.2f} < 0.85")
        if jev.recall < 0.85:
            reasons.append(f"{name}: Jev recall {jev.recall:.2f} < 0.85")
        if jev.f1 <= baseline.f1:
            reasons.append(
                f"{name}: Jev f1 {jev.f1:.2f} does not beat baseline f1 {baseline.f1:.2f}"
            )
    return (len(reasons) == 0, reasons)


def scorecard_title(summary: str | None) -> str:
    """SIMULATED (or uncaptured -- same honesty problem) runs get a title that says so."""
    if summary is None or "SIMULATED" in summary:
        return "SIMULATED backend vs regex baseline"
    return "Jev vs regex baseline"


def simulated_banner(summary: str | None) -> str | None:
    """A banner to print above the table when the numbers behind it aren't from a live model."""
    if summary is None or "SIMULATED" in summary:
        return (
            "SIMULATED — no API key: Jev columns are wiring checks (hash noise), "
            "not model results"
        )
    return None


def run_dbt(jaffle_dir: Path, *, pack: int | None, fresh: bool, mode: str | None) -> str:
    """Run the semantic+baseline dbt tests and return captured stdout.

    dbt exits non-zero on test failures (expected: that's how stored failures happen); we only
    fail loudly here if the run didn't get far enough to print its `Done.` line.
    """
    env = dict(os.environ)
    if pack is not None:
        env["JEV_PACK"] = str(pack)
    if fresh:
        env["JEV_NO_CACHE"] = "1"
    if mode is not None:
        env["JEV_MODE"] = mode
    cmd = [
        "uv", "run", "dbt", "test", "--profiles-dir", ".",
        "--select", "tag:semantic", "tag:baseline",
    ]
    result = subprocess.run(
        cmd,
        cwd=jaffle_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    if "Done." not in result.stdout:
        raise SystemExit(
            "dbt test produced no 'Done.' line; the run did not complete.\n"
            f"--- stdout (tail) ---\n{result.stdout[-4000:]}\n"
            f"--- stderr (tail) ---\n{result.stderr[-4000:]}"
        )
    return result.stdout


def _existing_main_tables(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "select table_name from information_schema.tables where table_schema = 'main'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        con.close()


def load_flagged(con: duckdb.DuckDBPyConnection, schema: str, table: str, id_col: str) -> set[int]:
    try:
        rows = con.execute(f"select {id_col} from {schema}.{table}").fetchall()
    except duckdb.CatalogException:
        print(
            f"Missing table {schema}.{table}. Run (from jaffle_shop/): {DBT_TEST_CMD}",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    return {r[0] for r in rows}


def _hard_neg_flagged_ids(flagged: set[int], golden: dict[int, str]) -> list[int]:
    return sorted(i for i in flagged if golden.get(i) == "hard_negative")


def _defects_missed_ids(flagged: set[int], golden: dict[int, str]) -> list[int]:
    return sorted(i for i, label in golden.items() if label == "defect" and i not in flagged)


def _mode_pack(summary: str) -> str:
    m = _MODE_PACK_RE.search(summary)
    if not m:
        return "unknown"
    return f"{m.group(1).lower()}/pack={m.group(2)}"


def print_report(
    console: Console,
    results: GateResults,
    summary: str | None,
) -> None:
    from rich.table import Table

    banner = simulated_banner(summary)
    if banner is not None:
        console.print(f"[bold yellow]{banner}[/bold yellow]")

    table = Table(title=scorecard_title(summary))
    table.add_column("test", no_wrap=True)
    table.add_column("defects", justify="right")
    table.add_column("Jev P", justify="right")
    table.add_column("Jev R", justify="right")
    table.add_column("Jev hard-neg", justify="right")
    table.add_column("regex P", justify="right")
    table.add_column("regex R", justify="right")
    table.add_column("regex hard-neg", justify="right")

    for name, (jev, baseline) in results.items():
        defects = jev.tp + jev.fn
        table.add_row(
            name,
            str(defects),
            f"[bold]{jev.precision:.2f}[/bold]",
            f"[bold]{jev.recall:.2f}[/bold]",
            f"[bold]{jev.hard_neg_flagged}[/bold]",
            f"{baseline.precision:.2f}",
            f"{baseline.recall:.2f}",
            str(baseline.hard_neg_flagged),
        )
    console.print(table)
    console.print(summary if summary is not None else "summary: not captured (use --run)")

    if summary is not None:
        ok, reasons = gate(results, summary)
        if ok:
            console.print("[bold green]GATE PASS[/bold green]")
        else:
            console.print("[bold red]GATE FAIL[/bold red]")
            for reason in reasons:
                console.print(f"[red]- {reason}[/red]")


def append_report(
    path: Path,
    results: GateResults,
    detail: dict[str, tuple[list[int], list[int]]],
    summary: str | None,
) -> None:
    ts = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok, reasons = gate(results, summary)

    header = (
        "| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |"
    )
    lines = [f"\n## {ts} · {_mode_pack(summary) if summary else 'summary not captured'}\n"]
    lines.append(summary if summary is not None else "summary: not captured (use --run)")
    lines.append("")
    lines.append(header)
    lines.append("|---|---|---|---|---|---|---|---|")
    for name, (jev, baseline) in results.items():
        defects = jev.tp + jev.fn
        lines.append(
            f"| {name} | {defects} | {jev.precision:.2f} | {jev.recall:.2f} "
            f"| {jev.hard_neg_flagged} | {baseline.precision:.2f} | {baseline.recall:.2f} "
            f"| {baseline.hard_neg_flagged} |"
        )
    lines.append("")
    gate_line = f"**Gate: {'PASS' if ok else 'FAIL'}**"
    if not ok:
        gate_line += " — " + "; ".join(reasons)
    lines.append(gate_line)
    lines.append("")
    for name, (hard_neg_ids, missed_ids) in detail.items():
        lines.append(
            f"- `{name}`: hard negatives flagged = {hard_neg_ids}, defects missed = {missed_ids}"
        )
    lines.append("")

    with open(path, "a") as f:
        f.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="store_true", help="run dbt test before scoring")
    parser.add_argument("--pack", type=int, default=None, help="override JEV_PACK")
    parser.add_argument("--fresh", action="store_true", help="set JEV_NO_CACHE=1")
    parser.add_argument("--mode", choices=["live", "demo"], default=None, help="set JEV_MODE")
    parser.add_argument("--append", action="store_true", help="append to docs/eval-results.md")
    parser.add_argument("--db", type=Path, default=None, help="override the duckdb path")
    args = parser.parse_args(argv)

    db_path = args.db or DEFAULT_DB
    summary: str | None = None

    if args.run:
        missing_models = REQUIRED_MODELS - _existing_main_tables(db_path)
        if missing_models:
            print(
                f"Missing model table(s): {', '.join(sorted(missing_models))}.\n"
                f"Run first (from jaffle_shop/): {DBT_BUILD_CMD}",
                file=sys.stderr,
            )
            return 2
        stdout = run_dbt(JAFFLE_DIR, pack=args.pack, fresh=args.fresh, mode=args.mode)
        summary = parse_summary(stdout)

    if not db_path.exists():
        print(
            f"No database at {db_path}.\n"
            f"Run first (from jaffle_shop/): {DBT_BUILD_CMD} && {DBT_TEST_CMD}",
            file=sys.stderr,
        )
        return 2

    golden = load_golden(GOLDEN_PATH)
    results: GateResults = {}
    detail: dict[str, tuple[list[int], list[int]]] = {}
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        if summary is None:
            summary = read_last_run_summary(con)
        for test_name, id_col in TESTS.items():
            gold = golden.get(test_name, {})
            audit = "main_dbt_test__audit"
            jev_flagged = load_flagged(con, audit, test_name, id_col)
            baseline_flagged = load_flagged(con, audit, f"baseline_{test_name}", id_col)
            results[test_name] = (metrics(jev_flagged, gold), metrics(baseline_flagged, gold))
            detail[test_name] = (
                _hard_neg_flagged_ids(jev_flagged, gold),
                _defects_missed_ids(jev_flagged, gold),
            )
    finally:
        con.close()

    console = Console()
    print_report(console, results, summary)

    if args.append:
        append_report(DOCS_PATH, results, detail, summary)
        console.print(f"Appended run to {DOCS_PATH.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
