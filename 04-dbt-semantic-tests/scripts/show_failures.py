"""Failure viewer: prints the top stored Jev failures per semantic test, for spot-checking.

    uv run python scripts/show_failures.py               # top 2 per test
    uv run python scripts/show_failures.py --limit 5
"""

import argparse
from pathlib import Path

import duckdb
from rich.console import Console
from rich.panel import Panel

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "jaffle_shop" / "jaffle_shop.duckdb"

# test name -> id column + the text (and context) columns to show, judged column last
TEST_COLUMNS = {
    "customers_full_name_is_a_person": ("customer_id", ["full_name"]),
    "returns_comment_matches_reason_code": ("return_id", ["reason_code", "comment"]),
    "reviews_body_matches_stars": ("review_id", ["stars", "body"]),
    "tickets_body_has_no_pii": ("ticket_id", ["body"]),
}

TRUNCATE_AT = 90


def _truncate(text: str, limit: int = TRUNCATE_AT) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _format_row(row: tuple, columns: list[str]) -> str:
    parts = [f"{col}={value!r}" for col, value in zip(columns, row, strict=True)]
    return _truncate(", ".join(parts))


def show_failures(con: duckdb.DuckDBPyConnection, console: Console, limit: int) -> None:
    for test_name, (id_col, text_cols) in TEST_COLUMNS.items():
        select_cols = [id_col, *text_cols, "jev_p"]
        try:
            rows = con.execute(
                f"select {', '.join(select_cols)} from main_dbt_test__audit.{test_name} "
                f"order by jev_p desc limit {limit}"
            ).fetchall()
        except duckdb.CatalogException:
            console.print(
                Panel(
                    "no stored failures (run `uv run dbt test --profiles-dir . "
                    "--select tag:semantic` first)",
                    title=test_name,
                )
            )
            continue

        if not rows:
            console.print(Panel("no stored failures", title=test_name))
            continue

        lines = []
        for row in rows:
            *rest, jev_p = row
            row_id = rest[0]
            text = _format_row(rest[1:], text_cols)
            lines.append(f"[bold]{row_id}[/bold]  jev_p={jev_p:.2f}  {text}")
        console.print(Panel("\n".join(lines), title=test_name))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=2, help="rows to show per test (default 2)")
    parser.add_argument("--db", type=Path, default=None, help="override the duckdb path")
    args = parser.parse_args(argv)

    db_path = args.db or DEFAULT_DB
    if not db_path.exists():
        print(f"No database at {db_path}.")
        return 2

    console = Console()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        show_failures(con, console, args.limit)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
