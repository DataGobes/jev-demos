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


def _dedupe_columns(names: list[str]) -> list[str]:
    """Make column names unique: the first occurrence of a name keeps it; each
    later duplicate gets an incrementing `_2`, `_3`, ... suffix, skipping any
    suffix that would itself collide with another column name."""
    used = set(names)
    counts: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        counts[name] = counts.get(name, 0) + 1
        if counts[name] == 1:
            out.append(name)
            continue
        n = counts[name]
        candidate = f"{name}_{n}"
        while candidate in used:
            n += 1
            candidate = f"{name}_{n}"
        used.add(candidate)
        out.append(candidate)
    return out


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
        columns = _dedupe_columns([d[0] for d in cur.description])
        types = [str(d[1]) for d in cur.description]
        rows = cur.fetchmany(row_cap + 1)
        truncated = len(rows) > row_cap
        rows = rows[:row_cap]
        row_count = len(rows)
        if truncated:
            count_cur = con.cursor()
            inner = sql.rstrip().rstrip(";")
            # The inner SQL must be on its own line: if it ends in a `--` comment,
            # a closing paren placed right after it on the same line would itself
            # be commented out, breaking the wrapping SELECT with no `result`
            # event ever reaching the client (F2).
            count_sql = f"SELECT count(*) FROM (\n{inner}\n) AS _jevviz_count"
            _execute_with_timeout(count_cur, count_sql, timeout_s)
            row_count = count_cur.fetchone()[0]
        return QueryResult(columns, types, rows, row_count, truncated)
    except duckdb.Error as exc:
        raise QueryError(str(exc)) from exc
