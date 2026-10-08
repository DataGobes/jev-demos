import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("miss_analysis", ROOT / "scripts/miss_analysis.py")
ma = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ma)

PLANTED = {1: (4, 2), 2: (4, 2), 3: (5, 1), 4: (5, 1), 5: (2, 4)}
# review_id, loaded stars, words, p, flagged
ROWS = [(1, 2, 40, 0.45, False), (2, 2, 60, 0.9, True), (3, 1, 20, 0.75, False),
        (4, 1, 30, 0.95, "true"), (5, 4, 50, 0.1, False)]


def test_to_flips_validates_and_sorts():
    flips = ma.to_flips(list(reversed(ROWS)), PLANTED)
    assert [f.review_id for f in flips] == [1, 2, 3, 4, 5]
    assert [f.flagged for f in flips] == [False, True, False, True, False]
    assert flips[0].original == 4 and flips[0].planted == 2


@pytest.mark.parametrize("rows, message", [
    (ROWS + [(1, 2, 40, 0.45, False)], "more than one"),
    ([(1, 2, 40, None, False)] + ROWS[1:], "no live judgment"),
    ([(1, 4, 40, 0.45, False)] + ROWS[1:], "planted 2"),
    ([(1, 2, 40, 0.85, False)] + ROWS[1:], "flagged=False"),
    (ROWS[1:], "not loaded"),
])
def test_to_flips_refuses_inconsistent_rows(rows, message):
    with pytest.raises(ValueError, match=message):
        ma.to_flips(rows, PLANTED)


def test_band_of_covers_misses_only():
    assert ma.band_of(0.0) == "0.0–0.2"
    assert ma.band_of(0.79) == "0.7–0.8"
    with pytest.raises(ValueError):
        ma.band_of(0.8)


def test_section_counts():
    text = ma.section(ma.to_flips(ROWS, PLANTED), {1: "real", 3: "ok", 2: "real"}, "STAMP")
    assert text.startswith("## Production misses (STAMP)")
    assert "5 planted flips · 2 caught · 3 missed · recall 0.40" in text
    assert "| 4 → 2 | 2 | 1 | 0.50 | 33% | 0.45 |" in text
    assert "| 5 → 1 | 2 | 1 | 0.50 | 33% | 0.75 |" in text
    assert "| 2 → 4 | 1 | 1 | 0.00 | 33% | 0.10 |" in text
    assert "1 → 5" not in text  # no flips of that type
    assert "| all | 1 | 1 | 0 | 1 |" in text
    assert "Just under the threshold (p 0.7–0.8): 1 of 3 misses" in text
    assert "median 45 words for caught flips, 40 for missed ones" in text
    assert "2 of the 100 audited planted flips are misses; 1 labelled real, 1 ok." in text
    assert "SIMULATED" not in text
