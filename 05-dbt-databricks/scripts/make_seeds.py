"""Deterministic seed CSV + golden-key generator for the jaffle_shop demo.

Given a seed, fills the authored text pools (scripts/pools/*.toml) into
CSV seed tables plus a hidden golden-answer key of which rows are planted
defects or hard negatives. All randomness flows through a single
random.Random(seed) instance so output is byte-identical across runs.
"""

from __future__ import annotations

import csv
import random
import re
import string
import tomllib
import unicodedata
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOLS = Path(__file__).resolve().parent / "pools"

FOOD_PRODUCTS = [
    "cheese & tomato jaffle",
    "ham & cheese jaffle",
    "banana nutella jaffle",
    "vegan chili jaffle",
    "apple cinnamon jaffle",
    "pulled jackfruit jaffle",
]
STREETS = [
    "Kerkstraat",
    "Dorpsweg",
    "Lindenlaan",
    "Prinsengracht",
    "Molenweg",
    "Stationsplein",
]
CITIES = ["Utrecht", "Amsterdam", "Rotterdam", "Den Haag", "Eindhoven", "Groningen"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
IBAN_BANKS = ["ABNA", "INGB", "RABO", "TRIO"]
EMAIL_DOMAINS = ["gmail.com", "outlook.com", "hotmail.nl"]
STORE_ADDRESS = "Jaffle Shop, Oudegracht 118, Utrecht"

ORDER_STATUS_WEIGHTS = {"placed": 5, "shipped": 10, "completed": 80, "return_pending": 5}
ORDER_STATUSES = list(ORDER_STATUS_WEIGHTS)
_ORDER_STATUS_WEIGHT_VALUES = list(ORDER_STATUS_WEIGHTS.values())

SLOT_RE = re.compile(r"\{(\w+)\}")


def _fold(text: str) -> str:
    """Ascii-fold, lowercase, spaces -> dots, drop anything outside [a-z0-9.]."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    folded = folded.lower().replace(" ", ".")
    return re.sub(r"[^a-z0-9.]", "", folded)


def make_email(first_name: str, last_name: str, customer_id: int) -> str:
    folded = _fold(f"{first_name}.{last_name}")
    if not folded:
        return f"customer{customer_id}@example.com"
    return f"{folded}{customer_id}@example.com"


class Filler:
    """Fills `{slot}` placeholders in pool text using a shared rng."""

    def __init__(self, rng: random.Random, first_names: list[str], last_names: list[str]):
        self.rng = rng
        self.first_names = first_names
        self.last_names = last_names

    def product(self) -> str:
        return self.rng.choice(FOOD_PRODUCTS)

    def minutes(self) -> str:
        return str(self.rng.randint(35, 150))

    def day(self) -> str:
        return self.rng.choice(WEEKDAYS)

    def first_name(self) -> str:
        return self.rng.choice(self.first_names)

    def order_no(self) -> str:
        return "#" + "".join(str(self.rng.randint(0, 9)) for _ in range(5))

    def store_address(self) -> str:
        return STORE_ADDRESS

    def street(self) -> str:
        return self.rng.choice(STREETS)

    def house_no(self) -> str:
        number = self.rng.randint(1, 220)
        if self.rng.random() < 0.3:
            return f"{number}{self.rng.choice('abcde')}"
        return str(number)

    def postcode(self) -> str:
        digits = "".join(str(self.rng.randint(0, 9)) for _ in range(4))
        letters = "".join(self.rng.choice(string.ascii_uppercase) for _ in range(2))
        return f"{digits} {letters}"

    def city(self) -> str:
        return self.rng.choice(CITIES)

    def phone(self) -> str:
        digits = "".join(str(self.rng.randint(0, 9)) for _ in range(8))
        variant = self.rng.randint(0, 2)
        if variant == 0:
            return f"06-{digits}"
        if variant == 1:
            return f"06 {digits[:4]} {digits[4:]}"
        return f"+31 6 {digits}"

    def iban(self) -> str:
        check = "".join(str(self.rng.randint(0, 9)) for _ in range(2))
        bank = self.rng.choice(IBAN_BANKS)
        digits = "".join(str(self.rng.randint(0, 9)) for _ in range(10))
        raw = f"NL{check}{bank}{digits}"
        if self.rng.random() < 0.5:
            return " ".join(raw[i : i + 4] for i in range(0, len(raw), 4))
        return raw

    def personal_email(self) -> str:
        first = self.rng.choice(self.first_names)
        last = self.rng.choice(self.last_names)
        domain = self.rng.choice(EMAIL_DOMAINS)
        folded = _fold(f"{first}.{last}") or "customer"
        return f"{folded}@{domain}"

    def fill(self, text: str) -> str:
        return SLOT_RE.sub(lambda m: str(getattr(self, m.group(1))()), text)


def load_pools(pools_dir: Path) -> dict:
    return {
        name: tomllib.loads((pools_dir / f"{name}.toml").read_text())
        for name in ("customers", "returns", "reviews", "tickets")
    }


def _labelled(pool: dict, n: int, rng: random.Random) -> list[tuple[dict, str]]:
    """Every defect + hard_negative once, remainder rng.choice(clean), shuffled."""
    entries = [(e, "defect") for e in pool["defect"]]
    entries += [(e, "hard_negative") for e in pool["hard_negative"]]
    remainder = n - len(entries)
    entries += [(rng.choice(pool["clean"]), "clean") for _ in range(remainder)]
    rng.shuffle(entries)
    return entries


def _build_customers(pool: dict, rng: random.Random, n: int = 500) -> tuple[list[dict], list[dict]]:
    entries = [(e, "defect") for e in pool["junk"]]
    entries += [(e, "hard_negative") for e in pool["hard_negative"]]
    remainder = n - len(entries)
    for _ in range(remainder):
        clean = {
            "first_name": rng.choice(pool["first_names"]),
            "last_name": rng.choice(pool["last_names"]),
        }
        entries.append((clean, "clean"))
    rng.shuffle(entries)

    rows: list[dict] = []
    golden: list[dict] = []
    for customer_id, (entry, label) in enumerate(entries, start=1):
        first_name = entry["first_name"]
        last_name = entry["last_name"]
        rows.append(
            {
                "id": customer_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": make_email(first_name, last_name, customer_id),
            }
        )
        if label != "clean":
            golden.append(
                {
                    "test_name": "customers_full_name_is_a_person",
                    "id": customer_id,
                    "label": label,
                    "note": entry["note"],
                }
            )
    return rows, golden


def _build_orders(customers: list[dict], rng: random.Random, n: int = 1500) -> list[dict]:
    customer_ids = [c["id"] for c in customers]
    start = date(2026, 1, 1)
    span = (date(2026, 8, 31) - start).days

    rows = [
        {
            "id": order_id,
            "user_id": rng.choice(customer_ids),
            "order_date": (start + timedelta(days=rng.randint(0, span))).isoformat(),
        }
        for order_id in range(1, n + 1)
    ]

    returned_ids = set(rng.sample(range(1, n + 1), 200))
    for row in rows:
        if row["id"] in returned_ids:
            row["status"] = "returned"
        else:
            row["status"] = rng.choices(ORDER_STATUSES, weights=_ORDER_STATUS_WEIGHT_VALUES)[0]
    return rows


def _build_returns(
    pool: dict, orders: list[dict], rng: random.Random, filler: Filler, n: int = 200
) -> tuple[list[dict], list[dict]]:
    entries = _labelled(pool, n, rng)
    returned_order_ids = [o["id"] for o in orders if o["status"] == "returned"]
    rng.shuffle(returned_order_ids)

    rows: list[dict] = []
    golden: list[dict] = []
    paired = zip(entries, returned_order_ids, strict=True)
    for return_id, ((entry, label), order_id) in enumerate(paired, start=1):
        rows.append(
            {
                "id": return_id,
                "order_id": order_id,
                "reason_code": entry["code"],
                "comment": filler.fill(entry["text"]),
            }
        )
        if label != "clean":
            golden.append(
                {
                    "test_name": "returns_comment_matches_reason_code",
                    "id": return_id,
                    "label": label,
                    "note": entry["note"],
                }
            )
    return rows, golden


def _build_reviews(
    pool: dict, orders: list[dict], rng: random.Random, filler: Filler, n: int = 400
) -> tuple[list[dict], list[dict]]:
    entries = _labelled(pool, n, rng)
    eligible_order_ids = [o["id"] for o in orders if o["status"] in ("completed", "returned")]
    order_ids = rng.sample(eligible_order_ids, n)

    rows: list[dict] = []
    golden: list[dict] = []
    paired = zip(entries, order_ids, strict=True)
    for review_id, ((entry, label), order_id) in enumerate(paired, start=1):
        rows.append(
            {
                "id": review_id,
                "order_id": order_id,
                "stars": entry["stars"],
                "body": filler.fill(entry["text"]),
            }
        )
        if label != "clean":
            golden.append(
                {
                    "test_name": "reviews_body_matches_stars",
                    "id": review_id,
                    "label": label,
                    "note": entry["note"],
                }
            )
    return rows, golden


def _build_tickets(
    pool: dict, customers: list[dict], rng: random.Random, filler: Filler, n: int = 200
) -> tuple[list[dict], list[dict]]:
    entries = _labelled(pool, n, rng)
    customer_ids = [c["id"] for c in customers]

    rows: list[dict] = []
    golden: list[dict] = []
    for ticket_id, (entry, label) in enumerate(entries, start=1):
        rows.append(
            {
                "id": ticket_id,
                "customer_id": rng.choice(customer_ids),
                "subject": entry["subject"],
                "body": filler.fill(entry["text"]),
            }
        )
        if label != "clean":
            golden.append(
                {
                    "test_name": "tickets_body_has_no_pii",
                    "id": ticket_id,
                    "label": label,
                    "note": entry["note"],
                }
            )
    return rows, golden


def generate(seed: int = 42, pools_dir: Path = POOLS) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    pools = load_pools(pools_dir)
    filler = Filler(rng, pools["customers"]["first_names"], pools["customers"]["last_names"])

    customers, customers_golden = _build_customers(pools["customers"], rng)
    orders = _build_orders(customers, rng)
    returns, returns_golden = _build_returns(pools["returns"], orders, rng, filler)
    reviews, reviews_golden = _build_reviews(pools["reviews"], orders, rng, filler)
    tickets, tickets_golden = _build_tickets(pools["tickets"], customers, rng, filler)

    golden = customers_golden + returns_golden + reviews_golden + tickets_golden
    return {
        "raw_customers": customers,
        "raw_orders": orders,
        "raw_returns": returns,
        "raw_reviews": reviews,
        "raw_tickets": tickets,
        "golden": golden,
    }


_SEED_COLUMNS = {
    "raw_customers": ["id", "first_name", "last_name", "email"],
    "raw_orders": ["id", "user_id", "order_date", "status"],
    "raw_returns": ["id", "order_id", "reason_code", "comment"],
    "raw_reviews": ["id", "order_id", "stars", "body"],
    "raw_tickets": ["id", "customer_id", "subject", "body"],
}
_GOLDEN_COLUMNS = ["test_name", "id", "label", "note"]


def write(tables: dict[str, list[dict]], seeds_dir: Path, golden_path: Path) -> None:
    seeds_dir.mkdir(parents=True, exist_ok=True)
    golden_path.parent.mkdir(parents=True, exist_ok=True)

    for name, columns in _SEED_COLUMNS.items():
        with (seeds_dir / f"{name}.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(tables[name])

    with golden_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_GOLDEN_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(tables["golden"])


def main() -> None:
    tables = generate()
    write(tables, ROOT / "jaffle_shop" / "seeds", ROOT / "eval" / "golden_defects.csv")


if __name__ == "__main__":
    main()
