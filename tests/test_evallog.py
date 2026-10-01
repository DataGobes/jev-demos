from pathlib import Path

from jevdbx.evallog import entry_for

ROOT = Path(__file__).parents[1]

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
    e = entry_for(MD, "6973d4ec-61ee-46ed-a5fa-dbe621e38318")
    assert e is not None
    assert e.startswith("## 2026-10-01T03:54:19Z · live/budget=48k")
    assert "**Gate: PASS**" in e and "cc2b0646" not in e and "Gate: FAIL" not in e
    assert not e.endswith("\n")


def test_only_the_invocation_line_matches_not_mentions_elsewhere():
    e = entry_for(MD, "cc2b0646-d666-47c4-883d-a726e60e7205")
    assert e is not None and e.startswith("## 2026-10-01T04:10:59Z")
    assert "Gate: FAIL" in e and "Gate: PASS" not in e


def test_unknown_or_empty_invocation_is_none():
    assert entry_for(MD, "00000000-0000-0000-0000-000000000000") is None
    assert entry_for(MD, "") is None
    assert entry_for("", "abc") is None


def test_a_prefix_of_an_id_does_not_match():
    assert entry_for(MD, "6973d4ec") is None


def test_real_log_entries_are_found_by_their_invocation_line():
    md = (ROOT / "docs" / "eval-results.md").read_text()
    e = entry_for(md, "6973d4ec-61ee-46ed-a5fa-dbe621e38318")
    assert e is not None and e.startswith("## 2026-10-01T03:54:19Z")
    assert "**Gate: PASS**" in e and "5a1fa0a8" not in e
