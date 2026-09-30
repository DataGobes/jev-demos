"""Sample 100 flagged production reviews for hand-labelling (precision audit).

Reads the ids Jev flagged from
jev_demo.jaffle_shop_dbt_test__audit.product_reviews_body_matches_stars, drops the planted flips
(eval/production_flips.csv: their label is known), samples 100 with seed 42 and writes
data/production_audit.csv with id, stars, body and an empty label. The model's score
(jev_p) is deliberately left out so the labeller is not anchored by it, and so are the
provenance columns (jev_mode, jev_invocation_id). The table must hold rows of one LIVE
invocation: a SIMULATED (demo-mode) table is never audited.

    uv run python scripts/audit_sample.py

Label each row in data/production_audit.csv: `real` = the text and the stars genuinely disagree,
`ok` = they don't. Then run score.py, which commits only eval/production_audit_labels.csv
(id,label).
"""

import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = "jev_demo.jaffle_shop_dbt_test__audit.product_reviews_body_matches_stars"


def pick_audit(flagged: set[int], planted: set[int], n: int, seed: int) -> list[int]:
    """Sorted ids: `n` drawn (seeded) from the flagged ids that were not planted; all if fewer."""
    candidates = sorted(flagged - planted)
    if len(candidates) <= n:
        return candidates
    return sorted(random.Random(seed).sample(candidates, n))


def flagged_query(table: str) -> str:
    """Judged LIVE failures only (unjudged rows have jev_p NULL); jev_p and the provenance columns
    are not selected (blind audit)."""
    return (f"select review_id, stars, body from {table} "
            "where jev_p is not null and jev_mode = 'live'")


def provenance_query(table: str) -> str:
    """Rows not written in live mode, and how many dbt invocations wrote the table."""
    return (f"select count_if(jev_mode is distinct from 'live'), "
            f"count(distinct jev_invocation_id) from {table}")


def provenance_problem(not_live: int, invocations: int) -> str | None:
    if not_live:
        return (f"{not_live:,} stored rows are not LIVE (SIMULATED demo mode): "
                "never audit a SIMULATED run")
    if invocations > 1:
        return f"the table mixes rows of {invocations} invocations: rebuild it"
    return None


def main(n: int = 100, seed: int = 42) -> int:
    from jevdbx.databricks import Sql

    with open(ROOT / "eval/production_flips.csv", newline="") as f:
        planted = {int(r["id"]) for r in csv.DictReader(f)}
    sql = Sql()
    prov = sql.run(provenance_query(TABLE))
    if prov.state != "SUCCEEDED":
        print(f"could not read {TABLE}: {prov.error}", file=sys.stderr)
        return 1
    problem = provenance_problem(int(prov.rows[0][0]), int(prov.rows[0][1]))
    if problem:
        print(f"refusing to sample {TABLE}: {problem}", file=sys.stderr)
        return 1
    res = sql.run(flagged_query(TABLE))
    if res.state != "SUCCEEDED":
        print(f"could not read {TABLE}: {res.error}", file=sys.stderr)
        return 1
    by_id = {int(r[0]): (r[1], r[2]) for r in res.rows}
    ids = pick_audit(set(by_id), planted, n, seed)
    out = ROOT / "data/production_audit.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "stars", "body", "label"])
        for i in ids:
            stars, body = by_id[i]
            w.writerow([i, stars, body, ""])
    planted_flagged = len(by_id.keys() & planted)
    print(f"{len(by_id):,} flagged, {planted_flagged:,} planted; wrote {len(ids)} to {out}")
    print("Label each row: real = the text and the stars genuinely disagree, ok = they don't.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
