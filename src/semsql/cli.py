"""semsql command-line interface: REPL, one-shot queries, `gen`, `eval-pack`.

Sibling modules (data, engine, backend, cache, stats, questions, udf) are imported
lazily inside the functions that need them, so this module — and its pure
formatting/parsing helpers — stay importable and testable even while those
modules are still being built.
"""

from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from semsql.backend import Backend
    from semsql.cache import Cache
    from semsql.questions import Question
    from semsql.stats import Stats

SIMULATED_BADGE = "SIMULATED — no TYPESAFE_API_KEY, judgments are fake"
JEV_PATTERN = re.compile(r"jev_", re.IGNORECASE)
_RESULT_KEYWORDS = frozenset(
    {"select", "with", "show", "describe", "explain", "pragma", "summarize", "values", "table", "from", "call"}
)
HELP_TEXT = (
    ".help         show this message\n"
    ".tables       list tables (SHOW TABLES)\n"
    ".rubrics      list named rubrics from rubrics.toml\n"
    ".stats        show the last query's stats snapshot\n"
    ".cache clear  clear the judgment cache\n"
    ".quit / .exit leave the REPL (Ctrl-D also works)"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the semsql argument parser."""
    parser = argparse.ArgumentParser(
        prog="semsql", description="Semantic SQL over DuckDB, powered by TypeSafe Jev."
    )
    parser.add_argument("--db", default="semsql.duckdb", help="DuckDB database file")
    parser.add_argument("--pack", type=int, default=1, help="rows packed per Jev request")
    parser.add_argument("--concurrency", type=int, default=32, help="max in-flight requests")
    parser.add_argument("--rpm", type=int, default=1200, help="requests per minute budget")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="force the deterministic demo backend")
    mode.add_argument("--live", action="store_true", help="force the real TypeSafe backend")
    parser.add_argument("--no-cache", action="store_true", help="disable the judgment cache")
    parser.add_argument("--cache-path", default=".semsql_cache.sqlite", help="cache sqlite path")
    parser.add_argument("--model", default="jev-latest", help="Jev model name")
    parser.add_argument("-c", "--command", default=None, metavar="SQL", help="run one SQL statement and exit")

    subparsers = parser.add_subparsers(dest="subcommand")

    gen = subparsers.add_parser("gen", help="load synthetic reviews into the database")
    gen.add_argument("--rows", type=int, default=10_000)
    gen.add_argument("--seed", type=int, default=7)

    eval_pack = subparsers.add_parser("eval-pack", help="compare pack=1 vs pack=K agreement")
    eval_pack.add_argument("--sample", type=int, default=200)
    eval_pack.add_argument("--pack", dest="eval_pack", type=int, default=16, help="pack size to test against 1")
    eval_pack.add_argument("--question", default="The customer is asking for their money back")

    return parser


def truncate(text: str, width: int = 80) -> str:
    """Truncate `text` to `width` characters, ending in an ellipsis if cut."""
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def is_probability_column(values: list) -> bool:
    """True when every non-null value is a float in [0, 1] (and at least one exists)."""
    non_null = [v for v in values if v is not None]
    if not non_null:
        return False
    return all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in non_null)


def format_bar(value: float) -> Text:
    """Render a 10-cell probability bar followed by the 2-decimal value."""
    filled = max(0, min(10, round(value * 10)))
    bar = "█" * filled + "░" * (10 - filled)
    if value >= 0.8:
        style = "green"
    elif value >= 0.5:
        style = "yellow"
    else:
        style = "dim"
    return Text(f"{bar} {value:.2f}", style=style)


def _format_cell(value: object, is_prob_col: bool) -> str | Text:
    if value is None:
        return Text("NULL", style="dim")
    if is_prob_col and isinstance(value, float):
        return format_bar(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, str):
        return truncate(value)
    return str(value)


def render_result(columns: list[str], rows: list[tuple], *, max_rows: int = 20) -> Table:
    """Build a Rich Table for a query result: bars for probability columns, truncated strings."""
    table = Table(show_header=True, header_style="bold")
    for name in columns:
        table.add_column(str(name))

    if rows:
        prob_cols = [is_probability_column([row[i] for row in rows]) for i in range(len(columns))]
    else:
        prob_cols = [False] * len(columns)

    for row in rows[:max_rows]:
        table.add_row(*[_format_cell(value, prob_cols[i]) for i, value in enumerate(row)])

    if len(rows) > max_rows:
        table.caption = f"… {len(rows) - max_rows} more rows"
    return table


class StatsPanel:
    """Rich renderable wrapping a live `Stats`; re-reads it on every `Live` refresh."""

    def __init__(self, stats: Stats, backend: Backend) -> None:
        self.stats = stats
        self.backend = backend

    def __rich__(self) -> Panel:
        snap = self.stats.snapshot()
        grid = Table.grid(padding=(0, 2))
        grid.add_column(justify="right", style="bold")
        grid.add_column()
        grid.add_row("rows scored", f"{snap.rows:,}")
        grid.add_row("rows/s", f"{snap.rows_per_s:.1f}")
        grid.add_row("requests", f"{snap.requests:,}")
        grid.add_row("input tokens", f"{snap.input_tokens:,}")
        grid.add_row("cost", f"${snap.cost_usd:.4f}")
        grid.add_row("cache hits", f"{snap.cache_hits:,}")
        grid.add_row("errors", Text(str(snap.errors), style="bold red" if snap.errors else "dim"))
        grid.add_row("backend", self.backend.name)
        grid.add_row("elapsed", f"{snap.elapsed_s:.1f}s")

        title: str | Text = "semsql"
        if self.backend.simulated:
            title = Text(f" {SIMULATED_BADGE} ", style="bold black on yellow")
        return Panel(grid, title=title, border_style="cyan")


def _first_keyword(sql: str) -> str:
    text = sql.strip()
    while text.startswith("--"):
        text = text.split("\n", 1)[1].strip() if "\n" in text else ""
    match = re.match(r"[A-Za-z_]+", text)
    return match.group(0).lower() if match else ""


def _produces_result_set(sql: str) -> bool:
    return _first_keyword(sql) in _RESULT_KEYWORDS


def run_sql(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    stats: Stats,
    backend: Backend,
    console: Console,
) -> bool:
    """Execute one SQL statement, rendering a live panel for `jev_` queries. Returns success."""
    stats.reset()
    uses_jev = bool(JEV_PATTERN.search(sql))
    start = time.perf_counter()
    try:
        if uses_jev:
            with Live(StatsPanel(stats, backend), console=console, refresh_per_second=12, transient=False):
                con.execute(sql)
        else:
            con.execute(sql)
    except duckdb.Error as exc:
        console.print(f"[red]{exc}[/red]")
        return False
    elapsed = time.perf_counter() - start

    if not _produces_result_set(sql):
        console.print("OK")
        return True

    columns = [d[0] for d in con.description]
    rows = con.fetchall()
    console.print(render_result(columns, rows))

    footer = f"{len(rows)} rows · {elapsed:.2f}s"
    if uses_jev:
        snap = stats.snapshot()
        footer += f" · ${snap.cost_usd:.4f} · {snap.requests:,} requests · {snap.cache_hits:,} cache hits"
    console.print(footer)
    if uses_jev and snap.errors:
        detail = getattr(backend, "last_error", None) or "unknown error"
        console.print(f"[red]{snap.errors:,} failed requests (rows returned as NULL): {detail}[/red]")
    return True


def cmd_gen(con: duckdb.DuckDBPyConnection, args: argparse.Namespace, console: Console) -> int:
    """`semsql gen`: load synthetic reviews and print a sample."""
    from semsql.data import load_reviews

    load_reviews(con, n=args.rows, seed=args.seed)
    count = con.execute("SELECT count(*) FROM reviews").fetchone()[0]
    console.print(f"loaded {count:,} reviews into `reviews`")
    samples = con.execute("SELECT body FROM reviews WHERE body IS NOT NULL AND body != '' LIMIT 3").fetchall()
    for i, (body,) in enumerate(samples, start=1):
        console.print(f"  {i}. {truncate(body, 100)}")
    return 0


def cmd_eval_pack(con: duckdb.DuckDBPyConnection, args: argparse.Namespace, console: Console) -> int:
    """`semsql eval-pack`: agreement between pack=1 and pack=K on a sample, no cache."""
    if not os.environ.get("TYPESAFE_API_KEY"):
        console.print(
            "[yellow]eval-pack needs a live backend to compare pack=1 vs pack=K; "
            "set TYPESAFE_API_KEY and pass --live.[/yellow]"
        )
        return 2

    from semsql.backend import make_backend
    from semsql.engine import Scorer
    from semsql.questions import Question
    from semsql.stats import Stats

    rows = con.execute(
        "SELECT body FROM reviews WHERE body IS NOT NULL AND body != '' LIMIT ?", [args.sample]
    ).fetchall()
    texts = [r[0] for r in rows]
    question = Question(kind="noul", instructions=args.question)

    def run(pack: int) -> tuple[list, Stats]:
        backend = make_backend(demo=False, model=args.model)
        stats = Stats()
        scorer = Scorer(backend, stats, None, pack=pack, concurrency=args.concurrency, rpm=args.rpm)
        try:
            values = scorer.score_many(texts, question)
        finally:
            scorer.close()
        return values, stats

    values1, stats1 = run(1)
    valuesk, statsk = run(args.eval_pack)

    pairs = [(a, b) for a, b in zip(values1, valuesk) if a is not None and b is not None]
    diffs = [abs(a - b) for a, b in pairs]
    mean_abs_diff = sum(diffs) / len(diffs) if diffs else 0.0
    max_diff = max(diffs) if diffs else 0.0

    def flip_rate(threshold: float) -> float:
        if not pairs:
            return 0.0
        flips = sum(1 for a, b in pairs if (a >= threshold) != (b >= threshold))
        return flips / len(pairs)

    snap1, snapk = stats1.snapshot(), statsk.snapshot()
    table = Table(title=f"pack=1 vs pack={args.eval_pack} agreement (n={len(pairs)})")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("mean abs diff", f"{mean_abs_diff:.4f}")
    table.add_row("max diff", f"{max_diff:.4f}")
    table.add_row("flip rate @0.5", f"{flip_rate(0.5):.2%}")
    table.add_row("flip rate @0.8", f"{flip_rate(0.8):.2%}")
    table.add_row("pack=1 requests / cost", f"{snap1.requests} / ${snap1.cost_usd:.4f}")
    table.add_row(f"pack={args.eval_pack} requests / cost", f"{snapk.requests} / ${snapk.cost_usd:.4f}")
    console.print(table)
    return 0


def _handle_dot_command(
    command: str,
    con: duckdb.DuckDBPyConnection,
    stats: Stats,
    backend: Backend,
    cache: Cache | None,
    rubrics: dict[str, Question],
    console: Console,
) -> None:
    if command == ".help":
        console.print(HELP_TEXT)
    elif command == ".tables":
        run_sql(con, "SHOW TABLES;", stats, backend, console)
    elif command == ".rubrics":
        for name, question in sorted(rubrics.items()):
            console.print(f"[bold]{name}[/bold]  {question.instructions}")
            for i, level in enumerate(question.levels):
                console.print(f"  {i}. {level}")
    elif command == ".stats":
        console.print(StatsPanel(stats, backend))
    elif command == ".cache clear":
        if cache is not None:
            cache.clear()
            console.print("cache cleared")
        else:
            console.print("caching is disabled (--no-cache)")
    else:
        console.print(f"unknown dot command: {command}. Try .help")


def repl(
    con: duckdb.DuckDBPyConnection,
    db_path: str,
    stats: Stats,
    backend: Backend,
    cache: Cache | None,
    rubrics: dict[str, Question],
    console: Console,
) -> int:
    """Multi-line prompt_toolkit REPL: statements run once the buffer ends in `;`."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory

    backend_line = f"backend: {backend.name}"
    if backend.simulated:
        backend_line += f"  [{SIMULATED_BADGE}]"
    console.print("semsql — semantic SQL over DuckDB, powered by TypeSafe Jev")
    console.print(backend_line)
    console.print(f"db: {db_path}  ·  type .help for commands")

    session: PromptSession = PromptSession(history=FileHistory(".semsql_history"))
    buffer = ""
    while True:
        try:
            line = session.prompt("   ...> " if buffer else "semsql> ")
        except KeyboardInterrupt:
            buffer = ""
            continue
        except EOFError:
            break

        stripped = line.strip()
        if not buffer and stripped.startswith("."):
            if stripped in (".quit", ".exit"):
                break
            _handle_dot_command(stripped, con, stats, backend, cache, rubrics, console)
            continue

        buffer = f"{buffer}\n{line}" if buffer else line
        if buffer.rstrip().endswith(";"):
            run_sql(con, buffer, stats, backend, console)
            buffer = ""
    return 0


def load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE lines from `path` into os.environ without overriding existing variables."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key and not key.startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main(argv: list[str] | None = None, console: Console | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    console = console or Console()
    load_dotenv()

    if args.live and not os.environ.get("TYPESAFE_API_KEY"):
        console.print("[red]--live requires TYPESAFE_API_KEY to be set.[/red]")
        return 2

    demo = True if args.demo else (False if args.live else None)

    from semsql import udf
    from semsql.backend import make_backend
    from semsql.cache import Cache
    from semsql.engine import Scorer
    from semsql.questions import load_rubrics
    from semsql.stats import Stats

    backend = make_backend(demo=demo, model=args.model)
    stats = Stats()
    cache = None if args.no_cache else Cache(args.cache_path)
    scorer = Scorer(backend, stats, cache, pack=args.pack, concurrency=args.concurrency, rpm=args.rpm)
    con = duckdb.connect(args.db)
    rubrics = load_rubrics()
    udf.register(con, scorer, rubrics)

    try:
        if args.subcommand == "gen":
            return cmd_gen(con, args, console)
        if args.subcommand == "eval-pack":
            return cmd_eval_pack(con, args, console)
        if args.command:
            return 0 if run_sql(con, args.command, stats, backend, console) else 1
        return repl(con, args.db, stats, backend, cache, rubrics, console)
    finally:
        scorer.close()
        con.close()
