"""Probe 5c/5d: can check-shaped SQL reach an external judge through a DuckDB extension?

Starts the mock judge (mock_judge_server.py) on 127.0.0.1, loads DuckDB's signed httpfs
extension from the `duckdb-extension-httpfs` wheel (the sandbox blocks extensions.duckdb.org),
and sends each probe as one ADBC execute on a fresh in-memory DuckDB 1.5.4, the way dbt v2
sends a check.

    uv run python probes/probe_ext.py
"""

import sys
import threading
from http.server import HTTPServer
from pathlib import Path

import duckdb_extension_httpfs
from adbc_driver_duckdb import dbapi
from mock_judge_server import CALLS, Handler


def httpfs_path() -> Path:
    root = Path(duckdb_extension_httpfs.__file__).parent
    return next(root.rglob("httpfs.duckdb_extension"))


def run(name: str, sql: str) -> None:
    with dbapi.connect(":memory:") as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql)
            print(f"[OK]    {name}: {cur.fetchall()}")
        except Exception as e:  # noqa: BLE001 - probe reports every failure verbatim
            print(f"[ERROR] {name}: {type(e).__name__}: {str(e).splitlines()[0][:220]}")


def main() -> None:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/judge"
    load = f"load '{httpfs_path()}';"

    run("load_httpfs_from_file", f"{load} select 1 as loaded")
    run(
        "constant_url_call",
        f"{load} select ok from read_json('{base}?name=order_total&description=customer%20email')",
    )
    run(
        "per_row_url_call",
        f"""{load}
        with cols(name, description) as (values ('order_total','customer email'), ('email','customer email'))
        select c.name, j.ok from cols c, read_json('{base}?name=' || c.name || '&description=' || c.description) j""",
    )
    run(
        "per_row_scalar_via_subquery",
        f"""{load}
        with cols(name, description) as (values ('order_total','customer email'))
        select name, (select ok from read_json('{base}?name=' || name)) as ok from cols""",
    )
    server.shutdown()
    print(f"mock judge received {len(CALLS)} request(s): {CALLS}", file=sys.stderr)


if __name__ == "__main__":
    main()
