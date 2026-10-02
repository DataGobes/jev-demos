"""Seeds must load on Databricks as they do in demo 04 (dbt-duckdb): only an empty cell is NULL."""

import pytest
from dbt_common.clients import agate_helper

from jevdbx import dbt_cli
from tests.dbt_helpers import JAFFLE

CUSTOMERS = JAFFLE / "seeds" / "raw_customers.csv"


def _last_names(ids):
    table = agate_helper.from_csv(str(CUSTOMERS), [])
    return {int(r["id"]): r["last_name"] for r in table.rows if int(r["id"]) in ids}


@pytest.fixture
def restore(monkeypatch):
    monkeypatch.setattr(agate_helper, "build_type_tester", agate_helper.build_type_tester)


def test_plain_dbt_turns_the_surname_null_into_sql_null(restore):
    # What dbt-core does unpatched (measured on the dev warehouse: 477 loaded as 'Sofie', NULL).
    # If this starts failing, dbt stopped doing it and jevdbx.dbt_cli can go.
    assert _last_names({477}) == {477: None}


def test_patched_seed_reader_keeps_null_text_and_empty_cells_null(restore):
    dbt_cli.patch_seed_nulls()
    assert _last_names({477, 113, 122}) == {477: "Null", 113: None, 122: None}


def test_dbtw_runs_the_patched_cli():
    from tests.test_databricks_client import dbtw

    assert dbtw.dbt_executable()[1:] == ["-m", "jevdbx.dbt_cli"]
