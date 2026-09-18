from __future__ import annotations

import duckdb
import pytest

from semsql.backend import DemoBackend
from semsql.cache import Cache
from semsql.engine import Scorer
from semsql.questions import load_rubrics
from semsql.stats import Stats
from semsql.udf import register


@pytest.fixture
def con():
    backend = DemoBackend(latency=0.0)
    stats = Stats()
    cache = Cache(":memory:")
    scorer = Scorer(backend, stats, cache, pack=4, concurrency=8, rpm=0)
    rubrics = load_rubrics()
    connection = duckdb.connect(":memory:")
    register(connection, scorer, rubrics)
    connection.execute(
        "CREATE TABLE reviews AS SELECT * FROM (VALUES "
        "(1, 'I want my money back, this is unacceptable!!'), "
        "(2, 'Love it, no need for a refund, works great'), "
        "(3, NULL)"
        ") t(id, body)"
    )
    yield connection
    connection.close()
    scorer.close()
    cache.close()


def test_jev_noul_basic(con) -> None:
    rows = con.execute(
        "SELECT id, jev_noul(body, 'The customer wants their money back') AS noul "
        "FROM reviews ORDER BY id"
    ).fetchall()
    assert rows[0][1] is not None and 0.0 <= rows[0][1] <= 1.0
    assert rows[1][1] is not None and 0.0 <= rows[1][1] <= 1.0
    assert rows[2][1] is None  # NULL body -> NULL


def test_jev_score_rubric(con) -> None:
    rows = con.execute("SELECT id, jev_score(body, 'anger') AS anger FROM reviews ORDER BY id").fetchall()
    assert rows[0][1] in (0.0, 1.0, 2.0, 3.0)
    assert rows[1][1] in (0.0, 1.0, 2.0, 3.0)
    assert rows[2][1] is None


def test_jev_score_unknown_rubric_raises(con) -> None:
    with pytest.raises(duckdb.InvalidInputException, match="unknown rubric"):
        con.execute("SELECT jev_score(body, 'not_a_real_rubric') FROM reviews").fetchall()


def test_jev_score_levels_ad_hoc(con) -> None:
    rows = con.execute(
        "SELECT id, jev_score_levels(body, 'how positive?', "
        "['negative', 'neutral', 'positive']) AS lvl FROM reviews ORDER BY id"
    ).fetchall()
    assert rows[0][1] in (0.0, 1.0, 2.0)
    assert rows[2][1] is None


def test_jev_choice(con) -> None:
    rows = con.execute(
        "SELECT id, jev_choice(body, 'sentiment', ['positive', 'negative']) AS choice "
        "FROM reviews ORDER BY id"
    ).fetchall()
    assert rows[0][1] in ("positive", "negative")
    assert rows[1][1] in ("positive", "negative")
    assert rows[2][1] is None


def test_where_and_order_by(con) -> None:
    rows = con.execute(
        "SELECT id FROM reviews "
        "WHERE jev_noul(body, 'The customer wants a refund') > 0.0 "
        "ORDER BY jev_score(body, 'anger') DESC"
    ).fetchall()
    ids = {r[0] for r in rows}
    assert 3 not in ids  # NULL body never satisfies > 0.0
    assert ids <= {1, 2}


def test_distinct_rubric_values_per_chunk_grouped_correctly(con) -> None:
    con.execute(
        "CREATE TABLE mixed AS SELECT * FROM (VALUES "
        "(1, 'text one', 'anger'), (2, 'text two', 'urgency'), (3, 'text three', 'anger')"
        ") t(id, body, rubric)"
    )
    rows = con.execute("SELECT id, jev_score(body, rubric) AS s FROM mixed ORDER BY id").fetchall()
    assert len(rows) == 3
    for _, value in rows:
        assert value in (0.0, 1.0, 2.0, 3.0)


def test_large_table_5000_rows(con) -> None:
    con.execute(
        "CREATE TABLE big AS SELECT i AS id, "
        "CASE WHEN i % 37 = 0 THEN NULL ELSE 'row number ' || i || ' says hello and asks for a refund' END AS body "
        "FROM range(5000) t(i)"
    )
    rows = con.execute(
        "SELECT count(*) FROM big WHERE jev_noul(body, 'is this asking for a refund?') > 0.0"
    ).fetchone()
    assert rows[0] > 0

    total = con.execute("SELECT count(*) FROM big").fetchone()[0]
    assert total == 5000

    scored = con.execute(
        "SELECT count(*) FILTER (WHERE anger IS NOT NULL) AS scored, "
        "count(*) FILTER (WHERE body IS NULL) AS nulls "
        "FROM (SELECT body, jev_score(body, 'anger') AS anger FROM big)"
    ).fetchone()
    scored_count, null_count = scored
    assert scored_count == 5000 - null_count
    assert null_count > 0
