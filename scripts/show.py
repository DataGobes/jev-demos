"""Recording-friendly views of the semantic tests and their results on Databricks, sized for a
phone clip: each subcommand fits one screen at roughly 90 columns x 30 rows.

    uv run python scripts/show.py tests    # the jev_expect blocks, syntax-highlighted
    uv run python scripts/show.py rows     # one planted-defect example row per test
    uv run python scripts/show.py score    # compact Jev-vs-regex scorecard
    uv run python scripts/show.py function # DESCRIBE FUNCTION EXTENDED of the Jev function

Companion to `scripts/score.py` (the full precision/recall table this reuses). Never truncates
text: rows and tests wrap instead. Stored failures are read from
jev_demo.jaffle_shop_dbt_test__audit; `tests` needs no connection.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "jaffle_shop" / "models" / "staging" / "schema.yml"

# The block called out in the recording -- it's the one that relates two columns, which is the
# clearest "written as a sentence" example.
FEATURED_TEST = "returns_comment_matches_reason_code"

SHORT_NAMES = {
    "customers_full_name_is_a_person": "customers",
    "returns_comment_matches_reason_code": "returns",
    "reviews_body_matches_stars": "reviews",
    "tickets_body_has_no_pii": "tickets",
}


def _load_score_module():
    """Load `score.py` as a module by path, not by `sys.path` import, so this works the same
    whether `show.py` is run directly or loaded by pytest via `importlib`."""
    spec = importlib.util.spec_from_file_location("_show_score", Path(__file__).parent / "score.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


score = _load_score_module()
AUDIT = score.AUDIT_SCHEMA


class NoStoredFailures(LookupError):
    """The stored-failure table of a test does not exist yet (the test never ran)."""


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def load_jev_tests(schema_text: str) -> list[dict]:
    """Every `jev_expect` test in a `schema.yml` document, in file order, as
    `{"model": ..., "column": ..., "name": ..., "arguments": {...}, "config": {...}}`.
    Pure: parses the given text, never touches disk.
    """
    data = yaml.safe_load(schema_text) or {}
    tests: list[dict] = []
    for model in data.get("models") or []:
        for column in model.get("columns") or []:
            for data_test in column.get("data_tests") or []:
                if isinstance(data_test, dict) and "jev_expect" in data_test:
                    entry = dict(data_test["jev_expect"])
                    entry["model"] = model.get("name")
                    entry["column"] = column.get("name")
                    tests.append(entry)
    return tests


def render_tests(console: Console, schema_path: Path = SCHEMA_PATH) -> None:
    tests = load_jev_tests(schema_path.read_text())
    featured = next((t for t in tests if t["name"] == FEATURED_TEST), None)
    others = [t for t in tests if t is not featured]

    if featured is not None:
        block = {
            "jev_expect": {
                k: v for k, v in featured.items() if k in ("name", "arguments", "config")
            }
        }
        # width=10**6: don't let PyYAML fold long scalars itself -- Rich's word_wrap below
        # does that, wrapping to the actual console width instead of a fixed guess, so long
        # sentences never get cut off mid-word.
        yaml_text = yaml.dump(block, sort_keys=False, default_flow_style=False, width=10**6)
        console.print(
            Syntax(yaml_text, "yaml", theme="monokai", background_color="default", word_wrap=True)
        )

    console.print()
    for t in others:
        name = t.get("name", "?")
        fails_if = (t.get("arguments") or {}).get("fails_if", "")
        console.print(f"[bold cyan]{name}[/bold cyan] → {fails_if}")


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------


def _read(sql, statement: str, test_name: str, *, missing_ok: bool):
    """Run a read; a missing table is NoStoredFailures (or None when `missing_ok`)."""
    res = sql.run(statement)
    if res.state == "SUCCEEDED":
        return res
    err = res.error or res.state
    if "TABLE_OR_VIEW_NOT_FOUND" in err:
        if missing_ok:
            return None
        raise NoStoredFailures(test_name)
    raise RuntimeError(f"could not read stored failures of {test_name}: {err}")


def select_example_row(
    sql, test_name: str, id_col: str, defect_ids: set[int]
) -> tuple[int, float, bool] | None:
    """Pick one flagged row to showcase for `test_name`.

    Prefers a row Jev flagged that is a golden `defect` AND that the regex baseline did NOT
    flag (the clearest "Jev wins" example), highest jev_p first, tying on lowest id. Falls
    back to the highest-jev_p golden defect if no such row exists. Returns
    `(id, jev_p, caught_by_baseline)`, or None if nothing flagged by Jev is a golden defect.
    Only judged rows count (jev_p is not null). Raises NoStoredFailures if the test's table
    does not exist.
    """
    jev = _read(
        sql,
        f"select {id_col}, jev_p from {AUDIT}.{test_name} where jev_p is not null",
        test_name,
        missing_ok=False,
    )
    jev_by_id = {int(r[0]): float(r[1]) for r in jev.rows}
    flagged_defects = defect_ids & set(jev_by_id)
    if not flagged_defects:
        return None
    base = _read(
        sql, f"select {id_col} from {AUDIT}.baseline_{test_name}", test_name, missing_ok=True
    )
    baseline_ids = {int(r[0]) for r in base.rows} if base is not None else set()
    missed_by_baseline = flagged_defects - baseline_ids
    pool = missed_by_baseline or flagged_defects
    chosen = max(pool, key=lambda i: (jev_by_id[i], -i))
    return chosen, jev_by_id[chosen], chosen in baseline_ids


def fetch_row(sql, test_name: str, id_col: str, row_id: int) -> dict:
    """One stored-failure row as {column: value} (Statement API values are strings)."""
    res = _read(
        sql,
        f"select * from {AUDIT}.{test_name} where {id_col} = {int(row_id)}",
        test_name,
        missing_ok=False,
    )
    return dict(zip(res.columns, res.rows[0], strict=True))


def render_row_body(
    row: dict,
    id_col: str,
    row_id: int,
    jev_p: float,
    text_col: str,
    context_cols: list[str],
    caught_by_baseline: bool,
) -> str:
    """The text inside one row's panel. Pure: takes plain values, does no I/O."""
    verdict = "regex: caught" if caught_by_baseline else "regex: missed"
    lines = [f"[bold]{id_col}={row_id}[/bold]  jev_p={jev_p:.2f}  {verdict}"]
    if context_cols:
        ctx = "  ".join(f"{c}={row[c]}" for c in context_cols)
        lines.append(f"[dim]{ctx}[/dim]")
    lines.append("")
    lines.append(str(row[text_col]))
    return "\n".join(lines)


def current_run(sql):
    """Provenance of the latest invocation of the yardstick tests, or None when there is none or
    it is partial (never shown as the scored run)."""
    return score.current_run(sql, list(score.TESTS), score.load_budget())


def render_rows(
    console: Console,
    sql,
    schema_path: Path = SCHEMA_PATH,
    golden_path: Path = score.GOLDEN_PATH,
) -> None:
    banner = score.simulated_banner(current_run(sql))
    if banner is not None:
        console.print(f"[bold yellow]{banner}[/bold yellow]")
    tests = load_jev_tests(schema_path.read_text())
    golden = score.load_golden(golden_path)
    for t in tests:
        name = t["name"]
        id_col = score.TESTS.get(name)
        if id_col is None:
            continue
        defect_ids = {i for i, label in golden.get(name, {}).items() if label == "defect"}
        try:
            result = select_example_row(sql, name, id_col, defect_ids)
        except NoStoredFailures:
            console.print(
                Panel(
                    "no stored failures (run `uv run python scripts/dbtw.py build "
                    "--select +tag:semantic` first)",
                    title=f"planted defect · {name}",
                )
            )
            continue
        if result is None:
            console.print(
                Panel("no golden defect among the flagged rows", title=f"planted defect · {name}")
            )
            continue
        row_id, jev_p, caught = result
        row = fetch_row(sql, name, id_col, row_id)
        context_cols = (t.get("arguments") or {}).get("context") or []
        body = render_row_body(row, id_col, row_id, jev_p, t["column"], context_cols, caught)
        console.print(Panel(body, title=f"planted defect · {name}"))


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


def format_headline(label: str, tp: int, total_defects: int, fp: int) -> str:
    """`Jev    caught 74/75 · 1 false alarm` -- pure, no I/O."""
    noun = "false alarm" if fp == 1 else "false alarms"
    return f"{label:<6} caught {tp}/{total_defects} · {fp} {noun}"


def render_score(console: Console, sql) -> None:
    golden = score.load_golden(score.GOLDEN_PATH)
    results: score.GateResults = {}
    for name, id_col in score.TESTS.items():
        gold = golden.get(name, {})
        jev_flagged = score.load_flagged(sql, name, id_col, judged_only=True)
        baseline_flagged = score.load_flagged(sql, f"baseline_{name}", id_col)
        results[name] = (score.metrics(jev_flagged, gold), score.metrics(baseline_flagged, gold))

    run = current_run(sql)
    banner = score.simulated_banner(run)
    if banner is not None:
        console.print(f"[bold yellow]{banner}[/bold yellow]")
        console.print()

    jev_tp = sum(jev.tp for jev, _ in results.values())
    jev_fp = sum(jev.fp for jev, _ in results.values())
    total_defects = sum(jev.tp + jev.fn for jev, _ in results.values())
    reg_tp = sum(baseline.tp for _, baseline in results.values())
    reg_fp = sum(baseline.fp for _, baseline in results.values())

    console.print(f"[bold]{format_headline('Jev', jev_tp, total_defects, jev_fp)}[/bold]")
    console.print(format_headline("Regex", reg_tp, total_defects, reg_fp))
    console.print()

    table = Table(show_header=True, box=None, padding=(0, 2, 0, 0))
    table.add_column("test")
    table.add_column("Jev", justify="right")
    table.add_column("regex", justify="right")
    for name, (jev, baseline) in results.items():
        defects = jev.tp + jev.fn
        table.add_row(
            SHORT_NAMES.get(name, name), f"{jev.tp}/{defects}", f"{baseline.tp}/{defects}"
        )
    console.print(table)
    console.print()
    console.print(score.run_line(run) if run is not None else "summary: not captured (use --run)")


# ---------------------------------------------------------------------------
# function
# ---------------------------------------------------------------------------

# DESCRIBE FUNCTION EXTENDED also prints the owner (a person), the session configs (150+ lines)
# and the body; none of that belongs on screen.
DESCRIBE_KEEP = ("Function", "Input", "Returns", "Comment", "Deterministic", "Language")


def function_name(mode: str | None = None) -> str:
    """The fully-qualified Jev function for the mode (JEV_MODE; demo -> the SIMULATED twin)."""
    mode = (mode or os.environ.get("JEV_MODE") or "live").lower()
    return "jev_demo.jev.noul_pack_demo" if mode == "demo" else "jev_demo.jev.noul_pack"


def describe_lines(rows: list[str]) -> list[str]:
    """The lines of a DESCRIBE FUNCTION EXTENDED result worth showing (pure).

    Keeps the `DESCRIBE_KEEP` fields, including the continuation lines of a multi-line field
    (Input lists one parameter per line); drops Owner, Create Time, Configs and Body."""
    kept: list[str] = []
    keep = False
    for row in rows:
        first = str(row).split("\n", 1)[0]
        if first[:1] not in (" ", "\t", "") and ":" in first:
            keep = first.split(":", 1)[0] in DESCRIBE_KEEP
            text = first
        else:
            text = first  # continuation of the previous field
        if keep:
            kept.append(text.rstrip())
    return kept


def render_function(console: Console, sql, name: str | None = None) -> int:
    name = name or function_name()
    statement = f"DESCRIBE FUNCTION EXTENDED {name}"
    res = sql.run(statement)
    if res.state != "SUCCEEDED":
        console.print(f"[bold red]{name}: {res.error or res.state}[/bold red]")
        return 1
    console.print(f"[dim]> {statement}[/dim]")
    for line in describe_lines([r[0] for r in res.rows]):
        console.print(line, markup=False, highlight=False, soft_wrap=True)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tests", help="the jev_expect blocks, syntax-highlighted")
    sub.add_parser("rows", help="one planted-defect example row per test")
    sub.add_parser("score", help="compact Jev-vs-regex scorecard")
    sub.add_parser("function", help="DESCRIBE FUNCTION EXTENDED of the Jev function")
    args = parser.parse_args(argv)

    console = Console()
    if args.command == "tests":
        render_tests(console)
        return 0

    from jevdbx.databricks import Sql

    sql = Sql()
    if args.command == "rows":
        render_rows(console, sql)
    elif args.command == "score":
        render_score(console, sql)
    elif args.command == "function":
        return render_function(console, sql)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
