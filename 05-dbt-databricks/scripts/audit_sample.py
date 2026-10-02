"""Blind audit files for the production run: the precision audit and the key audit.

Precision audit: reads the ids Jev flagged from
jev_demo.jaffle_shop_dbt_test__audit.product_reviews_body_matches_stars, drops the planted flips
(eval/production_flips.csv: their label is known), samples 100 with seed 42 and writes
data/production_audit.csv with id, stars, body and an empty label.

Key audit: samples N (default 100, seed 42) of the planted flips that are loaded in
jev_demo.jaffle_shop.stg_product_reviews, whether or not Jev flagged them, and writes
data/production_flip_audit.csv (id, stars, body, empty label) with the PLANTED stars as loaded.
It answers "is the planted key itself right?": a flip such as 4 -> 2 may not contradict the text.

The model's score (jev_p) and whether Jev flagged a row are deliberately left out of every file, so
the labeller is not anchored by them, and so are the provenance columns (jev_mode,
jev_invocation_id). The flagged table must hold rows of one LIVE invocation: a SIMULATED
(demo-mode) table is never audited.

    uv run python scripts/audit_sample.py [--flips 100] [--labeller-copies DIR]

--labeller-copies DIR also writes, per audit file, one shuffled copy per labeller
(`<name>.labeller_a.csv`, `.labeller_b.csv`; shuffle seeds 43 and 44) with the columns id, stars,
body only. Labels are `real` (the review's overall sentiment clearly contradicts its star rating)
or `ok` (anything else). The two labellers' results are merged by scripts/audit_merge.py, which
commits only id,label files under eval/.
"""

import argparse
import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = "jev_demo.jaffle_shop_dbt_test__audit.product_reviews_body_matches_stars"
MODEL = "jev_demo.jaffle_shop.stg_product_reviews"
LABELLER_SEEDS = (43, 44)  # the shuffle of labeller_a's and labeller_b's copy


def pick_audit(flagged: set[int], planted: set[int], n: int, seed: int) -> list[int]:
    """Sorted ids: `n` drawn (seeded) from the flagged ids that were not planted; all if fewer."""
    candidates = sorted(flagged - planted)
    if len(candidates) <= n:
        return candidates
    return sorted(random.Random(seed).sample(candidates, n))


def pick_flip_audit(planted_loaded: set[int], n: int, seed: int) -> list[int]:
    """Sorted ids: `n` drawn (seeded) from the planted flips that are loaded; all if fewer. The
    draw ignores whether Jev flagged a row."""
    candidates = sorted(planted_loaded)
    if len(candidates) <= n:
        return candidates
    return sorted(random.Random(seed).sample(candidates, n))


def flip_rows_query(ids: set[int]) -> str:
    """The loaded rows among the planted ids, as they sit in the production model (the planted
    stars). No score, no flag, no provenance."""
    listed = ", ".join(str(i) for i in sorted(ids))
    return f"select review_id, stars, body from {MODEL} where review_id in ({listed})"


def shuffled_copy(rows: list[tuple], seed: int) -> list[tuple]:
    """The rows in a seeded random order (the input is left alone)."""
    out = list(rows)
    random.Random(seed).shuffle(out)
    return out


def write_audit_file(path: Path, rows: list[tuple]) -> None:
    """id, stars, body and an empty label, sorted by id."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "stars", "body", "label"])
        for i, stars, body in sorted(rows, key=lambda r: r[0]):
            w.writerow([i, stars, body, ""])


def write_labeller_copies(directory: Path, name: str, rows: list[tuple]) -> list[Path]:
    """`<name>.labeller_a.csv` and `<name>.labeller_b.csv`: the same rows, shuffled with seeds 43
    and 44, columns id, stars, body only (no label column, nothing else)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for tag, seed in zip("ab", LABELLER_SEEDS, strict=True):
        path = directory / f"{name}.labeller_{tag}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["id", "stars", "body"])
            w.writerows(shuffled_copy(rows, seed))
        paths.append(path)
    return paths


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


def _read(sql, statement: str, what: str):
    res = sql.run(statement)
    if res.state != "SUCCEEDED":
        print(f"could not read {what}: {res.error}", file=sys.stderr)
        return None
    return res


def main(argv: list[str] | None = None) -> int:
    from jevdbx.databricks import Sql

    parser = argparse.ArgumentParser(description="Blind audit files for the production run")
    parser.add_argument("--n", type=int, default=100, help="precision audit size (default 100)")
    parser.add_argument("--flips", type=int, default=100,
                        help="key audit size: planted flips from the loaded rows (default 100)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--labeller-copies", type=Path, metavar="DIR", default=None,
                        help="also write shuffled id,stars,body copies for the two labellers")
    args = parser.parse_args(argv)

    with open(ROOT / "eval/production_flips.csv", newline="") as f:
        planted = {int(r["id"]) for r in csv.DictReader(f)}
    sql = Sql()
    prov = _read(sql, provenance_query(TABLE), TABLE)
    if prov is None:
        return 1
    problem = provenance_problem(int(prov.rows[0][0]), int(prov.rows[0][1]))
    if problem:
        print(f"refusing to sample {TABLE}: {problem}", file=sys.stderr)
        return 1
    res = _read(sql, flagged_query(TABLE), TABLE)
    flips = _read(sql, flip_rows_query(planted), MODEL)
    if res is None or flips is None:
        return 1
    by_id = {int(r[0]): (r[1], r[2]) for r in res.rows}
    flip_by_id = {int(r[0]): (r[1], r[2]) for r in flips.rows}

    out_dir = ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    audits = {
        "production_audit": (by_id, pick_audit(set(by_id), planted, args.n, args.seed)),
        "production_flip_audit": (
            flip_by_id, pick_flip_audit(set(flip_by_id), args.flips, args.seed)),
    }
    for name, (source, ids) in audits.items():
        rows = [(i, *source[i]) for i in ids]
        write_audit_file(out_dir / f"{name}.csv", rows)
        print(f"wrote {len(rows)} rows to {out_dir / (name + '.csv')}")
        if args.labeller_copies:
            for p in write_labeller_copies(args.labeller_copies, name, rows):
                print(f"wrote {len(rows)} rows to {p}")
    print(f"precision audit: {len(by_id):,} flagged, {len(by_id.keys() & planted):,} planted")
    print(f"key audit: {len(flip_by_id):,} of {len(planted):,} planted flips are loaded")
    print("Labels: real = the overall sentiment clearly contradicts the stars, ok = anything else.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
