"""Read column facts from a dbt v2 information schema (`target/info_schema/v1/`).

The information schema is flat Parquet, one file per table (`dbt.models.parquet`,
`dbt.node_columns.parquet`, ...): dbt-index-core/src/info_schema/mod.rs:1-8. Column names
follow dbt-index-core/src/info_schema/schema.rs (`node_columns`, `node_cols!`).
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from .judges import ColumnFacts


def _columns(con: duckdb.DuckDBPyConnection, path: Path) -> set[str]:
    rows = con.execute("select name from parquet_schema(?)", [str(path)]).fetchall()
    return {r[0] for r in rows}


def _first(available: set[str], alias: str, *candidates: str) -> str:
    present = [f"{alias}.{c}" for c in candidates if c in available]
    if not present:
        return "null"
    return present[0] if len(present) == 1 else f"coalesce({', '.join(present)})"


def load_column_facts(info_schema_dir: Path) -> list[ColumnFacts]:
    """Every documented-or-not column of every model, with the model's SQL.

    `data_type` and `compiled_code` are only filled once dbt has compiled the project: an
    information schema written from `parse` lacks compiled code, column types and lineage
    (dbt CHANGELOG, InfoSchemaIncomplete / dbt1658). Declared types and `raw_code` are the
    fallbacks, so a parse-only schema still works, with less for the judge to go on.
    """
    cols_path = info_schema_dir / "dbt.node_columns.parquet"
    models_path = info_schema_dir / "dbt.models.parquet"
    for p in (cols_path, models_path):
        if not p.exists():
            raise FileNotFoundError(
                f"{p} not found. Write the information schema first, e.g. "
                "`dbt compile --generate-info-schema`."
            )

    con = duckdb.connect()
    c_cols, m_cols = _columns(con, cols_path), _columns(con, models_path)
    data_type = _first(c_cols, "c", "data_type", "data_type_inferred", "data_type_declared")
    sql = _first(m_cols, "m", "compiled_code", "raw_code")
    rows = con.execute(
        f"""
        select c.node_unique_id, c.column_name, {data_type}, coalesce(c.description, ''), {sql}
        from read_parquet(?) as c
        join read_parquet(?) as m on m.unique_id = c.node_unique_id
        order by c.node_unique_id, c.column_name
        """,
        [str(cols_path), str(models_path)],
    ).fetchall()
    return [ColumnFacts(*r) for r in rows]
