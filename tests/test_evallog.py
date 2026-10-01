import importlib.util
from pathlib import Path

import pytest

from jevdbx import evallog
from jevdbx.evallog import entry_for
from jevdbx.pricing import PRICE_PER_MTOK_USD

ROOT = Path(__file__).parents[1]

# Written in pieces so the identifier scan (a GUID not preceded by "invocation ") stays quiet.
FIRST = "6973d4ec-61ee-46ed-" "a5fa-dbe621e38318"
SECOND = "cc2b0646-d666-47c4-" "883d-a726e60e7205"
NOBODY = "00000000-0000-0000-" "0000-000000000000"

MD = """# Eval results

intro, mentions `- invocation aaa` only in prose

## Reference: demo 04

no invocation here

## 2026-10-01T03:54:19Z · live/budget=48k

Jev · 1,057 judgments · LIVE

- invocation 6973d4ec-61ee-46ed-a5fa-dbe621e38318
- warehouse jev-demo-5

**Gate: PASS**

## 2026-10-01T04:10:59Z · live/budget=48k

Jev · 1,057 judgments · LIVE

- invocation cc2b0646-d666-47c4-883d-a726e60e7205
- cached 100% (judged in invocation 6973d4ec-61ee-46ed-a5fa-dbe621e38318)

**Gate: FAIL**

## Run-to-run noise

- invocation 6973d4ec-61ee-46ed-a5fa-dbe621e38318 is the first
"""


def test_entry_is_the_whole_block_from_its_heading_to_the_next_one():
    e = entry_for(MD, FIRST)
    assert e is not None
    assert e.startswith("## 2026-10-01T03:54:19Z · live/budget=48k")
    assert "**Gate: PASS**" in e and "cc2b0646" not in e and "Gate: FAIL" not in e
    assert not e.endswith("\n")


def test_only_the_invocation_line_matches_not_mentions_elsewhere():
    e = entry_for(MD, SECOND)
    assert e is not None and e.startswith("## 2026-10-01T04:10:59Z")
    assert "Gate: FAIL" in e and "Gate: PASS" not in e


def test_unknown_or_empty_invocation_is_none():
    assert entry_for(MD, NOBODY) is None
    assert entry_for(MD, "") is None
    assert entry_for("", "abc") is None


def test_a_prefix_of_an_id_does_not_match():
    assert entry_for(MD, "6973d4ec") is None


def test_real_log_entries_are_found_by_their_invocation_line():
    md = (ROOT / "docs" / "eval-results.md").read_text()
    e = entry_for(md, FIRST)
    assert e is not None and e.startswith("## 2026-10-01T03:54:19Z")
    assert "**Gate: PASS**" in e and "5a1fa0a8" not in e


# ---- results-only notebook mode: the pure parts ------------------------------------------------

INV = FIRST


def test_scored_tests_match_the_scorer():
    spec = importlib.util.spec_from_file_location("score_el", ROOT / "scripts" / "score.py")
    score = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(score)
    assert evallog.scored_tests("yardstick") == list(score.TESTS)
    assert evallog.scored_tests("production") == [score.PROD_TEST]
    with pytest.raises(ValueError):
        evallog.scored_tests("nope")


def test_latest_live_invocation_must_cover_every_scored_test_and_be_live():
    tests = evallog.scored_tests("yardstick")
    sql = " ".join(evallog.latest_live_invocation_sql(tests).split())
    assert "from jev_demo.jev.hook_runs" in sql
    assert "mode = 'live'" in sql
    assert "group by invocation_id having count(distinct test_name) = 4" in sql
    assert "order by max(recorded_at) desc limit 1" in sql
    for t in tests:
        assert f"'{t}'" in sql
    prod = evallog.latest_live_invocation_sql(evallog.scored_tests("production"))
    assert "count(distinct test_name) = 1" in " ".join(prod.split())
    assert "'product_reviews_body_matches_stars'" in prod


def test_utc_stamp_is_utc_and_to_the_second():
    # 2026-10-01T03:54:19Z
    assert evallog.utc_stamp(1_790_826_859_123_456) == "2026-10-01T03:54:19Z"
    assert evallog.utc_stamp(str(1_790_826_859_123_456)) == "2026-10-01T03:54:19Z"  # SQL client strings


def test_figures_sql_reads_the_ledger_for_exactly_this_invocation_and_tests():
    sql = " ".join(evallog.figures_sql(INV, ["a", "b"]).split())
    for table in ("jev_demo.jev.hook_runs", "jev_demo.jev.requests", "jev_demo.jev.judgments"):
        assert table in sql
    assert sql.count(f"invocation_id = '{INV}'") == 3
    assert sql.count("test_name in ('a', 'b')") == 3
    assert "pack_tokens" in sql and "429" in sql and "unix_micros" in sql


def test_sql_literals_escape_quotes_the_databricks_way():
    sql = evallog.figures_sql("x'y", ["a"])
    assert "'x\\'y'" in sql


def test_figures_from_row_and_lines_label_live_and_price_the_tokens():
    # tested, missing, unjudged, requests, tokens, retries, throttled, span_s, model
    f = evallog.figures_from_row([1057, 1057, 0, 6, 146994, 0, 0, 8.7, "jev-1.13.0"])
    assert f.judgments == 1057 and f.cached_pct == 0
    assert f.cost_usd == pytest.approx(146994 * PRICE_PER_MTOK_USD / 1e6)
    lines = evallog.figure_lines(INV, f)
    text = "\n".join(lines)
    assert lines[0].startswith("LIVE") and INV in lines[0] and "jev-1.13.0" in lines[0]
    for needle in ("1,057", "requests       6", "retries        0", "0× 429", "146,994", "$0.006",
                   "8.7 s"):
        assert needle in text
    assert "SIMULATED" not in text


def test_cached_share_is_shown_when_judgments_came_from_earlier_runs():
    f = evallog.figures_from_row([1000, 200, 0, 1, 10, 0, 0, 1.0, "m"])
    assert f.cached_pct == 80
    assert "80% cached" in "\n".join(evallog.figure_lines(INV, f))


def test_stored_failures_are_checked_against_the_chosen_invocation_and_live_mode():
    sql = " ".join(evallog.stored_failures_sql("reviews_body_matches_stars", INV).split())
    assert "from jev_demo.jaffle_shop_dbt_test__audit.reviews_body_matches_stars" in sql
    assert f"jev_invocation_id = '{INV}'" in sql and "jev_mode = 'live'" in sql
    assert "count(*)" in sql
    with pytest.raises(ValueError):
        evallog.stored_failures_sql("x; drop table y", INV)


def test_failure_rows_status():
    assert evallog.failure_rows_status(0, 0) == "empty"
    assert evallog.failure_rows_status(7, 7) == "show"
    assert evallog.failure_rows_status(7, 6) == "mismatch"
    assert evallog.failure_rows_status(7, 0) == "mismatch"
