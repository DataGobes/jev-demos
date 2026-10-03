import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIX = ROOT / "tests" / "fixtures"
spec = importlib.util.spec_from_file_location("fetch_data", ROOT / "scripts" / "fetch_data.py")
fd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fd)


def test_banking_rows_get_stable_ids():
    rows = fd.banking_rows((FIX / "banking_test.csv").read_text(), "test")
    assert [r["query_id"] for r in rows] == ["test-00000", "test-00001", "test-00002"]
    assert rows[0] == {"query_id": "test-00000", "split": "test",
                       "query": "I am still waiting on my card?", "intent": "card_arrival"}


def test_abt_pairs_render_both_records_without_labels():
    pairs = fd.abt_pairs((FIX / "abt_tableA.csv").read_text(),
                         (FIX / "abt_tableB.csv").read_text(),
                         (FIX / "abt_test.csv").read_text(), "test")
    assert pairs[0]["pair_id"] == "test-1-10"
    expected = "Sony Bravia 40in LCD TV | Sony Bravia KDL-40 40-inch LCD HDTV | 899.99"
    assert pairs[0]["left_record"] == expected
    assert pairs[1]["left_record"].endswith("| Canon 8MP digital camera, pink")
    assert "label" not in pairs[0]


def test_download_and_upload_need_explicit_flags():
    assert fd.parse_args([]).download is False and fd.parse_args([]).upload is False
