import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("fetch_reviews", ROOT / "scripts/fetch_reviews.py")
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)
FIX = ROOT / "tests/fixtures/finefoods_sample.txt"


def rows():
    return list(fr.parse_snap(FIX.read_text(encoding="utf-8").splitlines(keepends=True)))


def test_parse_keeps_only_safe_fields_with_1_based_ids():
    rs = rows()
    assert len(rs) == 12 and [r["id"] for r in rs] == list(range(1, 13))
    assert set(rs[0]) == {"id", "score", "summary", "text"}
    assert rs[0]["score"] == 5 and rs[0]["summary"] == "Good Quality Dog Food"


def test_fixture_covers_all_scores_and_non_ascii():
    rs = rows()
    assert {r["score"] for r in rs} == {1, 2, 3, 4, 5}
    assert any(not (r["summary"] + r["text"]).isascii() for r in rs)


def test_sample_is_deterministic_and_sorted():
    many = [{"id": i, "score": 5, "summary": "", "text": ""} for i in range(1, 1001)]
    a, b = fr.sample(many, 100, 42), fr.sample(many, 100, 42)
    assert a == b and len(a) == 100 and [r["id"] for r in a] == sorted(r["id"] for r in a)


def test_flips_cross_the_pole_and_never_touch_three_stars():
    many = [{"id": i, "score": (i % 5) + 1, "summary": "", "text": ""} for i in range(1, 10001)]
    out, flips = fr.plant_flips(many, 0.03, 42)
    by_id = {r["id"]: r for r in out}
    assert len(flips) == round(0.03 * 8000)  # the rate applies to the 8,000 non-3-star rows
    for f in flips:
        assert (f["original_stars"], f["planted_stars"]) in {(1, 5), (5, 1), (2, 4), (4, 2)}
        assert by_id[f["id"]]["stars"] == f["planted_stars"]
    flipped = {f["id"] for f in flips}
    assert all(r["stars"] == r["score"] for r in out if r["id"] not in flipped)
    assert all(r["score"] != 3 for r in out if r["id"] in flipped)
    assert fr.plant_flips(many, 0.03, 42) == (out, flips)


def test_split():
    a, b = fr.split(list(range(10)), 7)
    assert a == list(range(7)) and b == [7, 8, 9]


def test_parquet_drops_score_and_keeps_four_columns(tmp_path):
    import pyarrow.parquet as pq

    planted, _ = fr.plant_flips(rows(), 0.5, 42)
    fr._write_parquet(planted, tmp_path / "x.parquet")
    table = pq.read_table(tmp_path / "x.parquet")
    assert table.column_names == ["id", "stars", "summary", "text"]
    assert table.num_rows == 12
