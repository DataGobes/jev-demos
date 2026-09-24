import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("make_seeds", ROOT / "scripts" / "make_seeds.py")
make_seeds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_seeds)


def test_deterministic_and_written_files_match(tmp_path):
    a, b = make_seeds.generate(42), make_seeds.generate(42)
    assert a == b
    make_seeds.write(a, tmp_path / "seeds", tmp_path / "golden.csv")
    make_seeds.write(b, tmp_path / "seeds2", tmp_path / "golden2.csv")
    for f in (tmp_path / "seeds").iterdir():
        assert f.read_bytes() == (tmp_path / "seeds2" / f.name).read_bytes()


def test_shapes_and_structural_validity():
    t = make_seeds.generate(42)
    table_names = ("raw_customers", "raw_orders", "raw_returns", "raw_reviews", "raw_tickets")
    assert [len(t[k]) for k in table_names] == [500, 1500, 200, 400, 200]
    cust = {r["id"] for r in t["raw_customers"]}
    orders = {r["id"]: r for r in t["raw_orders"]}
    assert all(r["user_id"] in cust for r in t["raw_orders"])
    assert sum(r["status"] == "returned" for r in orders.values()) == 200
    assert all(orders[r["order_id"]]["status"] == "returned" for r in t["raw_returns"])
    assert len({r["order_id"] for r in t["raw_returns"]}) == 200
    assert len({r["order_id"] for r in t["raw_reviews"]}) == 400
    assert all(
        orders[r["order_id"]]["status"] in {"completed", "returned"} for r in t["raw_reviews"]
    )
    assert all(r["customer_id"] in cust for r in t["raw_tickets"])
    assert {r["reason_code"] for r in t["raw_returns"]} <= {
        "damaged", "wrong_item", "late", "changed_mind", "other",
    }
    assert {r["stars"] for r in t["raw_reviews"]} <= {1, 2, 3, 4, 5}
    for name in ("raw_returns", "raw_reviews", "raw_tickets"):
        for r in t[name]:
            text = r.get("comment") or r.get("body")
            assert text and "{" not in text, r


def test_golden_counts_and_ids_exist():
    t = make_seeds.generate(42)
    ids = {
        "customers_full_name_is_a_person": {r["id"] for r in t["raw_customers"]},
        "returns_comment_matches_reason_code": {r["id"] for r in t["raw_returns"]},
        "reviews_body_matches_stars": {r["id"] for r in t["raw_reviews"]},
        "tickets_body_has_no_pii": {r["id"] for r in t["raw_tickets"]},
    }
    counts = {}
    for g in t["golden"]:
        assert g["id"] in ids[g["test_name"]]
        counts[(g["test_name"], g["label"])] = counts.get((g["test_name"], g["label"]), 0) + 1
    assert counts == {
        ("customers_full_name_is_a_person", "defect"): 25,
        ("customers_full_name_is_a_person", "hard_negative"): 25,
        ("returns_comment_matches_reason_code", "defect"): 12,
        ("returns_comment_matches_reason_code", "hard_negative"): 20,
        ("reviews_body_matches_stars", "defect"): 24,
        ("reviews_body_matches_stars", "hard_negative"): 30,
        ("tickets_body_has_no_pii", "defect"): 14,
        ("tickets_body_has_no_pii", "hard_negative"): 25,
    }


def test_committed_files_are_current():
    seeds = ROOT / "jaffle_shop" / "seeds"
    with (seeds / "raw_returns.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 200
