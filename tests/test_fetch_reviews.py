import importlib.util
import io
import random
from pathlib import Path

import pytest

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


def test_sample_does_not_depend_on_input_order():
    many = [{"id": i, "score": 5, "summary": "", "text": ""} for i in range(1, 1001)]
    shuffled = many[:]
    random.Random(1).shuffle(shuffled)
    assert fr.sample(shuffled, 100, 42) == fr.sample(many, 100, 42)


def _snap(*blocks, eol="\n"):
    return [ln + eol for b in blocks for ln in b.split("\n")]


def test_parse_edge_cases():
    text = _snap(
        "review/score: 4.0\nreview/summary: Ratio: 2:1\nreview/text: Note: it was fine: really.",
        "",
        "review/score: 1.0\nreview/summary: \nreview/text: Empty summary above.",
        "",
        "review/score: 2.0\nreview/summary: Last\nreview/text: No trailing blank line.",
    )
    text[-1] = text[-1].rstrip("\n")
    rs = list(fr.parse_snap(text))
    assert [r["id"] for r in rs] == [1, 2, 3]
    assert rs[0]["summary"] == "Ratio: 2:1" and rs[0]["text"] == "Note: it was fine: really."
    assert rs[1]["summary"] == "" and rs[1]["text"] == "Empty summary above."
    assert rs[2]["text"] == "No trailing blank line."


def test_parse_empty_value_without_trailing_space():
    rs = list(fr.parse_snap(["review/score: 3.0\n", "review/summary:\n", "review/text: ok\n"]))
    assert rs == [{"id": 1, "score": 3, "summary": "", "text": "ok"}]


def test_parse_handles_crlf_line_endings():
    crlf = FIX.read_text(encoding="utf-8").replace("\n", "\r\n").splitlines(keepends=True)
    assert list(fr.parse_snap(crlf)) == rows()


class _Resp:
    def __init__(self, body: bytes, length: str | None):
        self._body, self.headers = io.BytesIO(body), ({"Content-Length": length} if length else {})

    def read(self, n=-1):
        return self._body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_prints_size_writes_part_then_renames(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(fr.urllib.request, "urlopen",
                        lambda url: calls.append(url) or _Resp(b"abc" * 10, "30"))
    dest = tmp_path / "finefoods.txt.gz"
    fr.download("https://example.test/f.gz", dest)
    out = capsys.readouterr().out
    assert calls == ["https://example.test/f.gz"]
    assert "https://example.test/f.gz" in out and str(dest) in out and "30 bytes" in out
    assert dest.read_bytes() == b"abc" * 10 and not dest.with_name(dest.name + ".part").exists()


def test_download_without_content_length_and_failure_leaves_no_dest(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fr.urllib.request, "urlopen", lambda url: _Resp(b"x", None))
    dest = tmp_path / "a.gz"
    fr.download("https://example.test/a.gz", dest)
    assert "size unknown" in capsys.readouterr().out and dest.read_bytes() == b"x"

    class Boom(_Resp):
        def read(self, n=-1):
            raise OSError("connection reset")

    monkeypatch.setattr(fr.urllib.request, "urlopen", lambda url: Boom(b"", "5"))
    dest2 = tmp_path / "b.gz"
    with pytest.raises(OSError):
        fr.download("https://example.test/b.gz", dest2)
    assert not dest2.exists() and not dest2.with_name("b.gz.part").exists()


def test_main_creates_eval_dir_for_the_flips_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "ROOT", tmp_path)
    many = "\n".join(
        f"review/score: {(i % 5) + 1}.0\nreview/summary: s{i}\nreview/text: t{i}\n"
        for i in range(40))
    src = tmp_path / "src.txt"
    src.write_text(many)
    assert not (tmp_path / "eval").exists()
    assert fr.main(["--source", str(src), "--out", str(tmp_path / "out"),
                    "--n", "20", "--first", "15"]) == 0
    assert (tmp_path / "eval/production_flips.csv").exists()
