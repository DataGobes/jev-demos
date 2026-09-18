"""Tests for semsql.cli.

Pure helpers (parsing, formatting) are tested against `semsql.cli` alone so they
pass even while sibling modules (data/engine/backend/...) are still being built.
The end-to-end test is skipped until those modules exist.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pytest
from rich.console import Console
from rich.text import Text

from semsql.cli import (
    build_parser,
    format_bar,
    is_probability_column,
    render_result,
    run_sql,
    truncate,
)


def _siblings_available() -> bool:
    try:
        import semsql.backend
        import semsql.cache
        import semsql.data
        import semsql.engine
        import semsql.questions
        import semsql.stats
        import semsql.udf  # noqa: F401
    except ImportError:
        return False
    return True


# --- argument parsing ------------------------------------------------------


def test_parser_defaults():
    args = build_parser().parse_args([])
    assert args.db == "semsql.duckdb"
    assert args.pack == 1
    assert args.concurrency == 32
    assert args.rpm == 1200
    assert args.demo is False
    assert args.live is False
    assert args.no_cache is False
    assert args.cache_path == ".semsql_cache.sqlite"
    assert args.model == "jev-latest"
    assert args.command is None
    assert args.subcommand is None


def test_demo_and_live_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--demo", "--live"])


def test_gen_subcommand_defaults():
    args = build_parser().parse_args(["gen"])
    assert args.subcommand == "gen"
    assert args.rows == 10_000
    assert args.seed == 7


def test_eval_pack_subcommand_pack_is_a_separate_namespace_field():
    # top-level --pack (Scorer pack size) must not collide with eval-pack's own
    # --pack (the K to compare against 1).
    args = build_parser().parse_args(["--pack", "4", "eval-pack", "--pack", "16"])
    assert args.pack == 4
    assert args.eval_pack == 16
    assert args.sample == 200
    assert args.question == "The customer is asking for their money back"


def test_command_flag():
    args = build_parser().parse_args(["-c", "SELECT 1"])
    assert args.command == "SELECT 1"


# --- pure formatting helpers -------------------------------------------------


def test_truncate_short_string_unchanged():
    assert truncate("short") == "short"


def test_truncate_long_string_gets_ellipsis():
    text = "x" * 100
    result = truncate(text, width=80)
    assert len(result) == 80
    assert result.endswith("…")
    assert result[:-1] == "x" * 79


def test_format_bar_high_value_is_green_and_mostly_full():
    bar = format_bar(0.83)
    assert isinstance(bar, Text)
    plain = bar.plain
    assert "0.83" in plain
    assert plain.count("█") == 8
    assert bar.style == "green"


def test_format_bar_mid_value_is_yellow():
    bar = format_bar(0.55)
    assert bar.style == "yellow"


def test_format_bar_low_value_is_dim():
    bar = format_bar(0.1)
    assert bar.style == "dim"
    assert bar.plain.count("█") == 1


def test_format_bar_boundaries():
    assert format_bar(0.0).plain.count("█") == 0
    assert format_bar(1.0).plain.count("█") == 10


def test_is_probability_column_true_for_probabilities_with_nulls():
    assert is_probability_column([0.1, None, 0.9, 0.5]) is True


def test_is_probability_column_false_for_ints():
    assert is_probability_column([0, 1, 0]) is False


def test_is_probability_column_false_for_out_of_range_floats():
    assert is_probability_column([0.1, 1.5]) is False


def test_is_probability_column_false_when_all_null():
    assert is_probability_column([None, None]) is False


def test_is_probability_column_false_for_strings():
    assert is_probability_column(["0.1", "0.9"]) is False


# --- render_result ------------------------------------------------------


def test_render_result_columns_and_null_and_bar():
    columns = ["id", "score", "note"]
    rows = [(1, 0.83, "ok"), (2, None, "x" * 100)]
    table = render_result(columns, rows)
    assert [c.header for c in table.columns] == columns
    assert table.row_count == 2
    # score column is all-probability (ignoring the None) -> bar formatting
    score_cell = table.columns[1]._cells[0]
    assert isinstance(score_cell, Text)
    assert "0.83" in score_cell.plain
    # NULL rendered dim
    null_cell = table.columns[1]._cells[1]
    assert isinstance(null_cell, Text)
    assert null_cell.plain == "NULL"
    # long string truncated
    note_cell = table.columns[2]._cells[1]
    assert len(note_cell) == 80


def test_render_result_caption_for_more_than_20_rows():
    columns = ["n"]
    rows = [(i,) for i in range(25)]
    table = render_result(columns, rows)
    assert table.row_count == 20
    assert table.caption == "… 5 more rows"


def test_render_result_plain_float_two_decimals():
    columns = ["price"]
    rows = [(1.23456,), (9.0,)]
    table = render_result(columns, rows)
    assert table.columns[0]._cells[0] == "1.23"
    assert table.columns[0]._cells[1] == "9.00"


# --- run_sql (fake stats/backend so no sibling modules are required) -------


@dataclass
class _FakeSnapshot:
    rows: int = 0
    cache_hits: int = 0
    requests: int = 0
    input_tokens: int = 0
    errors: int = 0
    elapsed_s: float = 0.01

    @property
    def rows_per_s(self) -> float:
        return self.rows / self.elapsed_s if self.elapsed_s else 0.0

    @property
    def cost_usd(self) -> float:
        return self.input_tokens / 1_000_000 * 0.042


class _FakeStats:
    def __init__(self) -> None:
        self._snap = _FakeSnapshot()

    def reset(self) -> None:
        self._snap = _FakeSnapshot()

    def snapshot(self) -> _FakeSnapshot:
        return self._snap


class _FakeBackend:
    name = "demo"
    simulated = True


def test_run_sql_plain_select():
    con = duckdb.connect(":memory:")
    console = Console(record=True, width=120)
    ok = run_sql(con, "SELECT 42 AS answer", _FakeStats(), _FakeBackend(), console)
    assert ok is True
    out = console.export_text()
    assert "42" in out
    assert "1 rows" in out


def test_run_sql_ddl_prints_ok():
    con = duckdb.connect(":memory:")
    console = Console(record=True, width=120)
    ok = run_sql(
        con, "CREATE TABLE t(x INTEGER)", _FakeStats(), _FakeBackend(), console
    )
    assert ok is True
    assert "OK" in console.export_text()


def test_run_sql_error_returns_false_and_prints_message():
    con = duckdb.connect(":memory:")
    console = Console(record=True, width=120)
    ok = run_sql(con, "SELEC 1", _FakeStats(), _FakeBackend(), console)
    assert ok is False
    assert "error" in console.export_text().lower()


def test_run_sql_no_jev_omits_cost_footer():
    con = duckdb.connect(":memory:")
    console = Console(record=True, width=120)
    run_sql(con, "SELECT 1", _FakeStats(), _FakeBackend(), console)
    assert "requests" not in console.export_text()


# --- --live without an API key: must not require sibling modules -----------


def test_live_without_api_key_errors_with_exit_code_2(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # keep the project's real .env out of the test
    from semsql.cli import main

    console = Console(record=True, width=120)
    rc = main(["--live", "-c", "SELECT 1"], console=console)
    assert rc == 2
    assert "TYPESAFE_API_KEY" in console.export_text()


# --- end-to-end (needs data.py/engine.py/... to exist) ----------------------


@pytest.mark.skipif(
    not _siblings_available(),
    reason="sibling modules (data/engine/backend/cache/stats/questions/udf) not yet implemented",
)
def test_end_to_end_demo_mode(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    from semsql.cli import main

    db_path = str(tmp_path / "semsql.duckdb")
    cache_path = str(tmp_path / "cache.sqlite")

    rc = main(
        ["--db", db_path, "--demo", "--cache-path", cache_path, "gen", "--rows", "200"]
    )
    assert rc == 0

    rc = main(
        [
            "--db",
            db_path,
            "--demo",
            "--cache-path",
            cache_path,
            "-c",
            "SELECT count(*) FROM reviews WHERE jev_noul(body, 'asks for money back') > 0.5",
        ]
    )
    assert rc == 0


def test_load_dotenv_sets_missing_and_keeps_existing(tmp_path, monkeypatch):
    from semsql.cli import load_dotenv

    env = tmp_path / ".env"
    env.write_text(
        "# comment\nexport SEMSQL_T_A='abc'\nSEMSQL_T_B=from_file\nSEMSQL_T_EMPTY=\n"
    )
    monkeypatch.delenv("SEMSQL_T_A", raising=False)
    monkeypatch.setenv("SEMSQL_T_B", "from_env")
    monkeypatch.delenv("SEMSQL_T_EMPTY", raising=False)
    load_dotenv(str(env))
    import os

    assert os.environ["SEMSQL_T_A"] == "abc"
    assert os.environ["SEMSQL_T_B"] == "from_env"
    assert "SEMSQL_T_EMPTY" not in os.environ
    monkeypatch.delenv("SEMSQL_T_A")


def test_load_script_splits_statements_and_drops_comments(tmp_path):
    from semsql.cli import load_script

    path = tmp_path / "demo.sql"
    path.write_text("-- intro\nSELECT 1;\n\nSELECT a,\n  b\nFROM t;\n")
    assert load_script(path) == ["SELECT 1;", "SELECT a,\n  b\nFROM t;"]
    assert load_script(tmp_path / "missing.sql") == []


def test_shipped_demo_script_statements_run_in_demo_mode(tmp_path):
    from pathlib import Path

    from semsql.cli import load_script, main

    statements = load_script(Path(__file__).parent.parent / "demo.sql")
    assert len(statements) == 3
    base = [
        "--db",
        str(tmp_path / "t.duckdb"),
        "--demo",
        "--cache-path",
        str(tmp_path / "c.sqlite"),
        "--rpm",
        "0",
    ]
    assert main([*base, "gen", "--rows", "150"]) == 0
    for statement in statements:
        assert (
            main([*base, "-c", statement], console=Console(record=True, width=120)) == 0
        )
