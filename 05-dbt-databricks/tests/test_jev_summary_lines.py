import json
import re

import pytest

from tests.dbt_helpers import dbt

BASE = dict(
    tested=1000, missing=400, inserted=400, oversized=0, unjudged=0, packs=3, tokens=150000,
    pack_rows=400, retries=2, throttled=1, error_packs=0, span=12.34, answered="jev-1.13.0",
    mode="live", dups=0, budget=48000, price=0.042,
)


def lines(**over):
    s = {**BASE, **over}
    out = dbt("run-operation", "jev_render_summary_lines", "--args", json.dumps({"s": s}))
    m = re.search(r"-- BEGIN\n(.*?)\n(.*?)\n(.*?)\n-- END", out.stdout, re.S)
    assert m, f"no output:\n{out.stdout}\n{out.stderr}"
    return m.group(1), m.group(2), m.group(3) == "True"


@pytest.mark.slow
def test_label_live_and_simulated_on_both_lines():
    l1, l2, _ = lines()
    assert "LIVE" in l1 and "LIVE" in l2 and "SIMULATED" not in l1 + l2
    l1, l2, _ = lines(mode="demo")
    assert "SIMULATED" in l1 and "SIMULATED" in l2 and "LIVE" not in l1 + l2


@pytest.mark.slow
def test_line1_numbers():
    l1, _, _ = lines()
    assert "1,000 judgments" in l1
    assert "60% cached" in l1
    assert "3 requests" in l1 and "2 retries (1× 429)" in l1
    assert "12.3 s Jev" in l1
    assert "$0.006" in l1  # 150000 * 0.042 / 1e6 = 0.0063
    assert "jev-1.13.0 budget=48k" in l1
    assert "unjudged" not in l1


@pytest.mark.slow
def test_judgments_excludes_unjudged_and_suffix_shows():
    l1, _, _ = lines(unjudged=30, error_packs=2)
    assert "970 judgments" in l1
    assert l1.endswith(" · 30 unjudged (2 failed requests)")


@pytest.mark.slow
def test_line2_ok_and_counts():
    _, l2, ok = lines(oversized=5, inserted=405, missing=405, pack_rows=400)
    assert ok
    assert l2.startswith("Jev · once-per-row OK · LIVE: ")
    assert "405 inserted = 405 missing" in l2
    assert "packs sum 400 (+5 too long)" in l2 and "0 duplicate keys" in l2


@pytest.mark.slow
@pytest.mark.parametrize("over", [
    dict(inserted=401),                 # inserted != missing
    dict(pack_rows=399),                # packs sum != inserted - oversized
    dict(oversized=1),                  # packs sum != inserted - oversized
    dict(dups=2),                       # duplicate keys
])
def test_violations(over):
    _, l2, ok = lines(**over)
    assert not ok
    assert "once-per-row VIOLATED" in l2


@pytest.mark.slow
def test_thousands_separators():
    l1, l2, _ = lines(tested=1234567, missing=1234567, inserted=1234567, pack_rows=1234567,
                      packs=12345)
    assert "1,234,567 judgments" in l1 and "12,345 requests" in l1
    assert "1,234,567 inserted = 1,234,567 missing" in l2
