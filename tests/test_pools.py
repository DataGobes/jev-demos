import re
import tomllib
from pathlib import Path

import pytest

POOLS = Path(__file__).parents[1] / "scripts" / "pools"
SLOTS = {"product", "minutes", "day", "first_name", "order_no", "store_address",
         "street", "house_no", "postcode", "city", "phone", "iban", "personal_email"}
PII_SLOTS = {"street", "house_no", "postcode", "city", "phone", "iban", "personal_email"}
CODES = {"damaged", "wrong_item", "late", "changed_mind", "other"}


def load(name):
    return tomllib.loads((POOLS / f"{name}.toml").read_text())


def slots(text):
    return set(re.findall(r"\{(\w+)\}", text))


def test_customers():
    p = load("customers")
    assert len(p["first_names"]) >= 120 and len(p["last_names"]) >= 120
    assert len(p["junk"]) == 25 and len(p["hard_negative"]) == 25
    assert all(e["note"] for e in p["junk"] + p["hard_negative"])


@pytest.mark.parametrize("name,defects,hard,clean_min", [
    ("returns", 12, 20, 110), ("reviews", 24, 30, 180), ("tickets", 14, 25, 110)])
def test_counts_and_slots(name, defects, hard, clean_min):
    p = load(name)
    assert len(p["defect"]) == defects and len(p["hard_negative"]) == hard
    assert len(p["clean"]) >= clean_min
    for group in ("clean", "defect", "hard_negative"):
        for e in p[group]:
            assert slots(e["text"]) <= SLOTS, e
            if group != "clean":
                assert e["note"], e
            if name != "tickets" or group != "defect":
                assert not (slots(e["text"]) & PII_SLOTS), e
    texts = [e["text"] for g in ("clean", "defect", "hard_negative") for e in p[g]]
    assert len(texts) == len(set(texts)), "duplicate texts"


def test_returns_codes():
    p = load("returns")
    assert {e["code"] for e in p["clean"]} == CODES
    assert all(e["code"] in CODES for g in ("defect", "hard_negative") for e in p[g])


def test_reviews_stars():
    p = load("reviews")
    assert {e["stars"] for e in p["clean"]} == {1, 2, 3, 4, 5}


def test_tickets_defects_all_carry_pii_slots_or_literal_pii():
    for e in load("tickets")["defect"]:
        assert slots(e["text"]) & PII_SLOTS or "@" in e["text"] or any(c.isdigit() for c in e["text"]), e
