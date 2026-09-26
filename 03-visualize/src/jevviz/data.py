"""Seeded synthetic retailer with planted patterns and column-type traps."""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb


def _sql_literal(value: object) -> str:
    """Render a Python value as a DuckDB SQL literal for bulk-VALUES inserts.

    Values here are always generator-controlled (fixed vocab, rounded floats,
    ISO dates) — never external input — so string interpolation is safe and
    much faster than `executemany`'s per-row parameter binding.
    """
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, date):
        return "'" + value.isoformat() + "'"
    return str(value)


def _bulk_insert(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple]) -> None:
    if not rows:
        return
    values = ",".join("(" + ",".join(_sql_literal(v) for v in row) + ")" for row in rows)
    con.execute(f"INSERT INTO {table} VALUES {values}")


REGIONS = ["EMEA", "APAC", "LATAM", "NA", "ANZ"]
CHANNELS = ["web", "store", "partner"]
SEGMENTS = ["consumer", "smb", "enterprise"]
COUNTRIES = ["NL", "DE", "US", "BR", "AU", "JP", "GB", "FR"]
CATEGORIES = {"Electronics": (400, 0.04), "Home": (120, 0.22), "Garden": (80, 0.25), "Toys": (35, 0.30), "Books": (18, 0.35)}
START, DAYS = date(2024, 1, 1), 730
_MAX_PRICE = max(base for base, _ in CATEGORIES.values()) * 1.8   # global price ceiling, for cross-category quality


def generate(path: Path | str, seed: int = 7, n_orders: int = 50_000) -> None:
    rng = random.Random(seed)
    path = Path(path)
    path.unlink(missing_ok=True)

    products = []
    for pid in range(1, 201):
        cat = rng.choice(list(CATEGORIES))
        base, _ = CATEGORIES[cat]
        price = round(base * rng.uniform(0.5, 1.8), 2)
        quality = price / _MAX_PRICE                            # planted: price correlates with rating
        rating = max(1, min(5, round(1 + 4 * (0.7 * quality + 0.3 * rng.random()))))
        products.append((pid, cat, price, rating))

    customers = [(cid, rng.choice(SEGMENTS), rng.randint(2015, 2025), rng.randint(10000, 99999), rng.choice(COUNTRIES))
                 for cid in range(1, 5001)]

    weights = [5 if CATEGORIES[p[1]][0] >= 400 else 2 for p in products]   # planted: Electronics dominates revenue
    orders = []
    for oid in range(1, n_orders + 1):
        day = rng.randrange(DAYS)
        d = START + timedelta(days=day)
        if d.month in (11, 12) or rng.random() < 0.55:                   # planted: Nov/Dec spike
            region = rng.choice(REGIONS)
            if region == "LATAM" and rng.random() < day / DAYS * 0.85:   # planted: LATAM declines
                region = rng.choice(["EMEA", "APAC", "NA"])
            pid, cat, price, _ = rng.choices(products, weights)[0]
            qty = rng.randint(1, 4)
            revenue = round(price * qty, 2)
            margin = CATEGORIES[cat][1] + rng.uniform(-0.12, 0.08)       # can go negative
            orders.append((oid, d, region, rng.choice(CHANNELS), revenue, round(revenue * margin, 2),
                           rng.randint(1, 5000), pid))

    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE products (product_id INTEGER, category VARCHAR, price DOUBLE, rating INTEGER)")
    con.execute("CREATE TABLE customers (customer_id INTEGER, segment VARCHAR, signup_year INTEGER, zip INTEGER, country VARCHAR)")
    con.execute("CREATE TABLE orders (order_id INTEGER, order_date DATE, region VARCHAR, channel VARCHAR, "
                "revenue DOUBLE, profit DOUBLE, customer_id INTEGER, product_id INTEGER)")
    _bulk_insert(con, "products", products)
    _bulk_insert(con, "customers", customers)
    _bulk_insert(con, "orders", orders)
    con.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "jevviz.duckdb"
    generate(target)
    print(f"wrote {target}")
