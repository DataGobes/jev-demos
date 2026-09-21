import pytest

from jevviz.data import generate
from jevviz.db import QueryError, open_db, run_query


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    path = tmp_path_factory.mktemp("d") / "t.duckdb"
    generate(path, n_orders=8_000)
    return open_db(path)


def test_runs_and_caps_rows(con):
    r = run_query(con, "SELECT order_id, revenue FROM orders", row_cap=100)
    assert r.columns == ["order_id", "revenue"] and len(r.rows) == 100
    assert r.truncated is True and r.row_count > 100


def test_writes_are_rejected(con):
    with pytest.raises(QueryError):
        run_query(con, "DELETE FROM orders")


def test_external_access_is_blocked(con):
    with pytest.raises(QueryError):
        run_query(con, "SELECT * FROM read_csv('/etc/passwd')")


def test_sql_error_is_wrapped(con):
    with pytest.raises(QueryError):
        run_query(con, "SELEKT 1")


def test_query_times_out(con):
    with pytest.raises(QueryError) as excinfo:
        run_query(
            con,
            "SELECT count(*) FROM range(100000000) a, range(1000) b",
            timeout_s=0.2,
        )
    assert "timed out after 0.2" in str(excinfo.value)
