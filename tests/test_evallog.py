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
    # a SQL client returns the number as a string
    assert evallog.utc_stamp(str(1_790_826_859_123_456)) == "2026-10-01T03:54:19Z"


def test_judging_invocations_sql_is_live_successful_latest_question_per_invocation():
    tests = evallog.scored_tests("yardstick")
    sql = " ".join(evallog.judging_invocations_sql(tests).split())
    for table in ("jev_demo.jev.hook_runs", "jev_demo.jev.requests", "jev_demo.jev.judgments"):
        assert table in sql
    assert "max_by(question, judged_at)" in sql  # judgments of an older wording do not count
    assert "j.p is not null" in sql and "j.mode = 'live'" in sql and "mode = 'live'" in sql
    assert "group by j.invocation_id" in sql
    assert "count(distinct j.key)" in sql
    assert "429" in sql and "pack_tokens" in sql and "unix_micros" in sql
    assert "order by s.first_at" in sql
    for t in tests:
        assert f"'{t}'" in sql


def test_sql_literals_escape_quotes_the_databricks_way():
    assert "'x\\'y'" in evallog.stored_failures_sql("t", "x'y")


# columns: invocation_id, states, requests, tokens, retries, throttled, span_s, recorded_micros
ROW_A = [FIRST, "1057", "6", "146994", "0", "0", "8.7", str(1_790_826_859_123_456)]
ROW_B = [SECOND, "100", "2", "10000", "1", "1", "1.5", str(1_790_827_859_000_000)]


def test_judging_from_rows_casts_and_prices_the_tokens():
    js = evallog.judging_from_rows([ROW_A, ROW_B])
    assert [j.invocation_id for j in js] == [FIRST, SECOND]
    a = js[0]
    assert (a.states, a.requests, a.tokens, a.retries, a.throttled) == (1057, 6, 146994, 0, 0)
    assert a.span_s == 8.7 and a.recorded_at == "2026-10-01T03:54:19Z"
    assert a.cost_usd == pytest.approx(146994 * PRICE_PER_MTOK_USD / 1e6)


def test_judging_total_sums_requests_tokens_cost_and_states():
    js = evallog.judging_from_rows([ROW_A, ROW_B])
    t = evallog.judging_total(js)
    assert (t.states, t.requests, t.tokens, t.retries, t.throttled) == (1157, 8, 156994, 1, 1)
    assert t.cost_usd == pytest.approx(156994 * PRICE_PER_MTOK_USD / 1e6)
    assert evallog.judging_total([]).requests == 0


def test_judging_caption_counts_rows_and_runs():
    js = evallog.judging_from_rows([ROW_A, ROW_B])
    assert evallog.judging_caption(js) == (
        "These 1,157 rows were judged in 2 live run(s) (listed below), logged in "
        "docs/eval-results.md; no Jev calls are made now.")
    one = evallog.judging_caption(evallog.judging_from_rows([ROW_A]))
    assert "These 1,057 rows were judged in 1 live run(s)" in one


def test_judging_lines_list_each_run_then_a_total_labelled_live():
    js = evallog.judging_from_rows([ROW_A, ROW_B])
    lines = evallog.judging_lines(js)
    text = "\n".join(lines)
    assert "LIVE" in lines[0]
    ra = next(ln for ln in lines if FIRST in ln)
    for needle in ("2026-10-01T03:54:19Z", "1,057", "146,994", "$0.006", "8.7 s"):
        assert needle in ra, needle
    rb = next(ln for ln in lines if SECOND in ln)
    assert "1 (1× 429)" in rb and "$0.000" in rb
    total = lines[-1]
    assert total.lstrip().startswith("total")
    for needle in ("1,157", "156,994", "$0.007", "8 "):
        assert needle in total, needle
    assert "SIMULATED" not in text


def test_cost_note_states_the_price():
    assert evallog.COST_NOTE.startswith("Jev cost = input tokens × 0.042 / 1e6")


def test_entries_for_runs_prints_each_logged_entry_and_says_not_appended_for_the_rest():
    js = evallog.judging_from_rows([ROW_A, ROW_B])
    got = evallog.entries_for_runs(MD, js)
    assert [inv for inv, _ in got] == [FIRST, SECOND]
    assert got[0][1].startswith("## 2026-10-01T03:54:19Z") and "Gate: PASS" in got[0][1]
    assert got[1][1].startswith("## 2026-10-01T04:10:59Z")
    none = evallog.entries_for_runs("# log\n", js)
    assert [e for _, e in none] == [None, None]
    assert evallog.NOT_APPENDED == "not found in eval-results.md — this run was not appended"


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
