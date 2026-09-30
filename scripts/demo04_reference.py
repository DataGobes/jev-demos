"""Print demo 04's stored baseline failures for one test as a JSON id list (read-only)."""

import json
import sys
from pathlib import Path

import duckdb

DB = Path.home() / "Projects/jev-demo-4/jaffle_shop/jaffle_shop.duckdb"
ID = {"customers_full_name_is_a_person": "customer_id",
      "returns_comment_matches_reason_code": "return_id",
      "reviews_body_matches_stars": "review_id", "tickets_body_has_no_pii": "ticket_id"}


def main(name: str) -> int:
    con = duckdb.connect(str(DB), read_only=True)
    table = f"main_dbt_test__audit.baseline_{name}"
    try:
        ids = sorted(int(r[0]) for r in con.execute(f"select {ID[name]} from {table}").fetchall())
    except duckdb.CatalogException:
        print(f"demo 04 has no {table}")
        return 2
    print(json.dumps(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
