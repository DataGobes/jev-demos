from __future__ import annotations

import time
from collections import Counter
from datetime import datetime

import duckdb

from semsql.data import generate_labeled, generate_reviews, load_reviews


def test_determinism() -> None:
    a = generate_reviews(500, seed=1)
    b = generate_reviews(500, seed=1)
    assert a == b


def test_different_seed_differs() -> None:
    a = generate_reviews(500, seed=1)
    b = generate_reviews(500, seed=2)
    assert a != b


def test_row_count_and_schema() -> None:
    rows = generate_reviews(1000, seed=7)
    assert len(rows) == 1000
    ids = [r["id"] for r in rows]
    assert ids == list(range(1, 1001))
    for row in rows:
        assert row.keys() == {"id", "product", "stars", "body", "created_at"}
        assert isinstance(row["id"], int)
        assert isinstance(row["product"], str)
        assert isinstance(row["stars"], int)
        assert 1 <= row["stars"] <= 5
        assert row["body"] is None or isinstance(row["body"], str)
        assert isinstance(row["created_at"], datetime)


def test_created_at_within_last_12_months_of_anchor() -> None:
    rows = generate_reviews(2000, seed=7)
    anchor = datetime(2026, 9, 1)  # noqa: DTZ001 -- naive, matches ANCHOR_DATE / DuckDB TIMESTAMP
    one_year_before = datetime(2025, 9, 1)  # noqa: DTZ001
    for row in rows:
        assert one_year_before <= row["created_at"] <= anchor


def test_duplicate_rate_below_5_percent_at_10k() -> None:
    rows = generate_reviews(10_000, seed=7)
    bodies = [r["body"] for r in rows if r["body"]]
    counts = Counter(bodies)
    duplicate_rows = sum(c for c in counts.values() if c > 1)
    assert duplicate_rows / len(bodies) < 0.05


def test_null_or_empty_share_between_1_and_6_percent() -> None:
    rows = generate_reviews(10_000, seed=7)
    empty = sum(1 for r in rows if not r["body"])
    share = empty / len(rows)
    assert 0.01 <= share <= 0.06


def test_refund_intent_without_keyword() -> None:
    labeled = generate_labeled(10_000, seed=7)
    matches = [
        row
        for row, intent in labeled
        if intent == "refund_no_keyword"
        and row["body"]
        and "refund" not in row["body"].lower()
    ]
    assert len(matches) >= 300


def test_keyword_without_refund_intent() -> None:
    labeled = generate_labeled(10_000, seed=7)
    matches = [
        row
        for row, intent in labeled
        if row["body"]
        and "refund" in row["body"].lower()
        and intent != "refund_keyword"
    ]
    assert len(matches) >= 150


def test_load_reviews_creates_table_with_expected_schema() -> None:
    con = duckdb.connect(":memory:")
    try:
        load_reviews(con, n=1234, seed=3)
        count = con.execute("SELECT count(*) FROM reviews").fetchone()[0]
        assert count == 1234
        columns = con.execute("DESCRIBE reviews").fetchall()
        schema = {name: col_type for name, col_type, *_ in columns}
        assert schema["id"] == "INTEGER"
        assert schema["product"] == "VARCHAR"
        assert schema["stars"] == "INTEGER"
        assert schema["body"] == "VARCHAR"
        assert schema["created_at"] == "TIMESTAMP"
    finally:
        con.close()


def test_load_reviews_is_deterministic() -> None:
    con_a = duckdb.connect(":memory:")
    con_b = duckdb.connect(":memory:")
    try:
        load_reviews(con_a, n=500, seed=42)
        load_reviews(con_b, n=500, seed=42)
        rows_a = con_a.execute("SELECT * FROM reviews ORDER BY id").fetchall()
        rows_b = con_b.execute("SELECT * FROM reviews ORDER BY id").fetchall()
        assert rows_a == rows_b
    finally:
        con_a.close()
        con_b.close()


def test_load_reviews_is_fast() -> None:
    con = duckdb.connect(":memory:")
    try:
        start = time.perf_counter()
        load_reviews(con, n=10_000, seed=7)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0
    finally:
        con.close()
