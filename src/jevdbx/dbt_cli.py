"""The dbt CLI, with seed CSVs read the way dbt-duckdb (demo 04) reads them.

dbt-core parses seed CSVs with agate and turns a text cell spelled "null" (any case) into SQL
NULL. dbt-duckdb loads CSVs with DuckDB, where only an empty cell is NULL. The yardstick has a
real surname "Null" (customer 477, a golden hard negative): on Databricks it silently became
NULL and "Sofie Null" became "Sofie". This keeps "null" text as text; empty cells stay NULL.

    python -m jevdbx.dbt_cli seed --profiles-dir . --target dev   # same arguments as `dbt`
"""

from dbt_common.clients import agate_helper

_build_type_tester = agate_helper.build_type_tester


def _only_empty_is_null(text_columns, string_null_values=("",)):
    return _build_type_tester(text_columns, string_null_values=string_null_values)


def patch_seed_nulls() -> None:
    """Make agate_helper.from_csv (dbt's seed reader) treat only an empty text cell as NULL."""
    agate_helper.build_type_tester = _only_empty_is_null


def main() -> None:
    patch_seed_nulls()
    from dbt.cli.main import cli

    cli()


if __name__ == "__main__":
    main()
