"""Read-only, sandboxed DuckDB access."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb


class QueryError(Exception):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    types: list[str]
    rows: list[tuple]
    row_count: int
    truncated: bool


def open_db(path: Path | str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path), read_only=True, config={"enable_external_access": "false"})
    con.execute("SET lock_configuration = true")
    return con


def _execute_with_timeout(cur: duckdb.DuckDBPyConnection, sql: str, timeout_s: float) -> None:
    timer = threading.Timer(timeout_s, cur.interrupt)
    timer.start()
    try:
        cur.execute(sql)
    except duckdb.Error as exc:
        if isinstance(exc, duckdb.InterruptException):
            raise QueryError(f"query timed out after {timeout_s} seconds") from exc
        raise
    finally:
        timer.cancel()


def run_query(con: duckdb.DuckDBPyConnection, sql: str, row_cap: int = 5000, timeout_s: float = 10.0) -> QueryResult:
    try:
        cur = con.cursor()
        _execute_with_timeout(cur, sql, timeout_s)
        if cur.description is None:
            raise QueryError("statement returned no result set")
        columns = [d[0] for d in cur.description]
        types = [str(d[1]) for d in cur.description]
        rows = cur.fetchmany(row_cap + 1)
        truncated = len(rows) > row_cap
        rows = rows[:row_cap]
        row_count = len(rows)
        if truncated:
            count_cur = con.cursor()
            _execute_with_timeout(
                count_cur, f"SELECT count(*) FROM ({sql.rstrip().rstrip(';')})", timeout_s
            )
            row_count = count_cur.fetchone()[0]
        return QueryResult(columns, types, rows, row_count, truncated)
    except duckdb.Error as exc:
        raise QueryError(str(exc)) from exc
