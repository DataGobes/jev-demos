"""List every table and column in a dbt information schema directory, with row counts, and show
the fields a description judge needs.

    uv run python probes/inventory.py project/target/info_schema/v1
"""

import sys
from pathlib import Path

import duckdb


def main(info_schema_dir: str) -> None:
    root = Path(info_schema_dir)
    con = duckdb.connect()
    for f in sorted(root.glob("*.parquet")):
        n = con.execute("select count(*) from read_parquet(?)", [str(f)]).fetchone()[0]
        cols = [r[0] for r in con.execute("select name from parquet_schema(?) where name <> 'duckdb_schema'", [str(f)]).fetchall()]
        print(f"{f.stem:<32} rows={n:<4} cols={len(cols):<3} {', '.join(cols)}")

    print("\n-- what the judge needs, per model column (first 40 chars of SQL):")
    rows = con.execute(
        """
        select m.name as model, c.column_name, c.data_type_declared, c.data_type_inferred, c.data_type,
               c.description, left(replace(m.compiled_code, chr(10), ' '), 40) as compiled_code
        from read_parquet(?) c join read_parquet(?) m on m.unique_id = c.node_unique_id
        order by 1, 2
        """,
        [str(root / "dbt.node_columns.parquet"), str(root / "dbt.models.parquet")],
    )
    print(" | ".join(d[0] for d in rows.description))
    for r in rows.fetchall():
        print(" | ".join("NULL" if v is None else str(v) for v in r))

    lineage = root / "dbt.column_lineage.parquet"
    if lineage.exists():
        print("\n-- column_lineage:")
        for r in con.execute("select * exclude (ingested_at) from read_parquet(?) order by all", [str(lineage)]).fetchall():
            print(r)


if __name__ == "__main__":
    main(sys.argv[1])
