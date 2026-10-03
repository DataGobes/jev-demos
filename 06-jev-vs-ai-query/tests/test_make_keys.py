import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("make_keys", ROOT / "scripts" / "make_keys.py")
mk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mk)


def test_relabel_seed_contains_only_swapped_rows(tmp_path):
    rows = [{"query_id": f"test-{i:05d}", "split": "test", "query": "q",
             "intent": ["card_arrival", "card_linking", "exchange_rate"][i % 3]} for i in range(60)]
    mk.write_banking_keys(rows, out_eval=tmp_path / "eval", out_seeds=tmp_path / "seeds",
                          sample_n=30, n_random=3, n_near=3, full_rate=0.1, seed=42)
    relabel = list(csv.DictReader((tmp_path / "seeds" / "banking77_relabel.csv").open()))
    swaps = list(csv.DictReader((tmp_path / "eval" / "banking77_swaps.csv").open()))
    assert len(relabel) == len(swaps) > 0
    assert set(relabel[0]) == {"query_id", "labelled_intent"}   # no ground truth in the seed
    sample = list(csv.DictReader((tmp_path / "seeds" / "banking77_sample.csv").open()))
    assert len(sample) == 30


def test_flips_are_written_as_hashes_never_text(tmp_path):
    states = [("Awful stay", "1.0"), ("Awful stay", "2.0"), ("Perfect", "4.5"), ("Okay", "3.0")]
    mk.write_wanderbricks_flips(states, out_eval=tmp_path / "eval", out_seeds=tmp_path / "seeds")
    seed_file = tmp_path / "seeds" / "wanderbricks_flips.csv"
    rows = list(csv.DictReader(seed_file.open()))
    assert set(rows[0]) == {"comment_sha256", "rating"} and len(rows) == 3 + 3 + 2
    text = seed_file.read_text() + (tmp_path / "eval" / "wanderbricks_flips.csv").read_text()
    assert "Awful" not in text and "Perfect" not in text and "Okay" not in text
