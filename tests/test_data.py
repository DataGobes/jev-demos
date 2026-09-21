import duckdb
import pytest

from jevviz.data import generate


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    path = tmp_path_factory.mktemp("d") / "t.duckdb"
    generate(path, seed=7, n_orders=20_000)
    return duckdb.connect(str(path), read_only=True)


def test_tables_and_trap_columns(con):
    cols = {r[0]: r[1] for r in con.execute("DESCRIBE orders").fetchall()}
    assert {"order_date", "region", "channel", "revenue", "profit", "customer_id", "product_id"} <= set(cols)
    assert con.execute("SELECT typeof(signup_year) FROM customers LIMIT 1").fetchone()[0] in ("INTEGER", "BIGINT")
    assert con.execute("SELECT min(profit) FROM orders").fetchone()[0] < 0


def test_one_region_declines(con):
    first, last = con.execute("""
        SELECT sum(revenue) FILTER (WHERE order_date < DATE '2024-07-01'),
               sum(revenue) FILTER (WHERE order_date >= DATE '2025-07-01')
        FROM orders WHERE region = 'LATAM'""").fetchone()
    assert last < first * 0.7


def test_seasonal_spike_in_november_december(con):
    peak, base = con.execute("""
        SELECT avg(r) FILTER (WHERE m IN (11, 12)), avg(r) FILTER (WHERE m NOT IN (11, 12))
        FROM (SELECT month(order_date) m, sum(revenue) r FROM orders GROUP BY ALL)""").fetchone()
    assert peak > base * 1.4


def test_high_revenue_low_profit_category(con):
    rows = con.execute("""
        SELECT p.category, sum(o.revenue) rev, sum(o.profit) / sum(o.revenue) margin
        FROM orders o JOIN products p USING (product_id) GROUP BY ALL ORDER BY rev DESC""").fetchall()
    assert rows[0][0] == "Electronics" and rows[0][2] == min(r[2] for r in rows)


def test_price_rating_correlation(con):
    assert con.execute("SELECT corr(price, rating) FROM products").fetchone()[0] > 0.4


def test_deterministic(tmp_path):
    a, b = tmp_path / "a.duckdb", tmp_path / "b.duckdb"
    generate(a, seed=7, n_orders=2_000); generate(b, seed=7, n_orders=2_000)
    q = "SELECT sum(revenue), count(*) FROM orders"
    assert duckdb.connect(str(a)).execute(q).fetchone() == duckdb.connect(str(b)).execute(q).fetchone()
