"""A synthetic information schema built from the example project, for tests that need no dbt.

Column names follow dbt-index-core/src/info_schema/schema.rs. The SQL is the model file as
written (refs unrendered), standing in for `compiled_code`.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import yaml

PROJECT = Path(__file__).parent.parent / "project"


def project_columns() -> list[dict]:
    spec = yaml.safe_load((PROJECT / "models/schema.yml").read_text())
    rows = []
    for model in spec["models"]:
        sql = next(PROJECT.glob(f"models/**/{model['name']}.sql")).read_text()
        for col in model["columns"]:
            rows.append({
                "model": model["name"],
                "unique_id": f"model.desc_checks.{model['name']}",
                "column_name": col["name"],
                "data_type": col.get("data_type"),
                "description": col.get("description"),
                "sql": sql,
            })
    return rows


def write_info_schema(dest: Path, rows: list[dict], *, compiled: bool = True) -> Path:
    """Write dbt.models.parquet + dbt.node_columns.parquet. `compiled=False` mimics a parse-only
    schema by leaving out compiled_code and the resolved data_type."""
    dest.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        "create table cols(node_unique_id varchar, column_name varchar, data_type_declared varchar,"
        " data_type varchar, description varchar)"
    )
    con.execute("create table models(unique_id varchar, name varchar, raw_code varchar, compiled_code varchar)")
    seen = set()
    for r in rows:
        con.execute(
            "insert into cols values (?, ?, ?, ?, ?)",
            [r["unique_id"], r["column_name"], r["data_type"], r["data_type"], r["description"]],
        )
        if r["unique_id"] not in seen:
            seen.add(r["unique_id"])
            con.execute("insert into models values (?, ?, ?, ?)", [r["unique_id"], r["model"], r["sql"], r["sql"]])
    col_sel = "*" if compiled else "* exclude (data_type)"
    model_sel = "*" if compiled else "* exclude (compiled_code)"
    con.execute(f"copy (select {col_sel} from cols) to '{dest / 'dbt.node_columns.parquet'}' (format parquet)")
    con.execute(f"copy (select {model_sel} from models) to '{dest / 'dbt.models.parquet'}' (format parquet)")
    return dest


@pytest.fixture
def rows() -> list[dict]:
    return project_columns()


@pytest.fixture
def info_schema(tmp_path: Path, rows: list[dict]) -> Path:
    return write_info_schema(tmp_path / "info_schema/v1", rows)
