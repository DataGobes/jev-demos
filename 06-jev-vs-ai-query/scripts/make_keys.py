"""Write the committed ground truth (eval/) and the dbt seeds (bench/seeds/) from data/.

    uv run python scripts/make_keys.py banking          # swaps, sample, families, seeds
    uv run python scripts/make_keys.py abt              # pair labels, Jaccard threshold
    uv run python scripts/make_keys.py wanderbricks-template   # data/wanderbricks_label_me.csv
    uv run python scripts/make_keys.py wanderbricks-commit     # eval/wanderbricks_polarity.csv
    uv run python scripts/make_keys.py wanderbricks-flips      # planted ratings (eval/ + seed)
"""

import csv
import sys
from pathlib import Path

from jevdbx import keys

ROOT = Path(__file__).resolve().parents[1]
DATA, EVAL, SEEDS = ROOT / "data", ROOT / "eval", ROOT / "bench" / "seeds"
SEED, SAMPLE_N, N_RANDOM, N_NEAR, FULL_RATE = 42, 2000, 75, 75, 0.075
N_FLIPS_POLAR, N_FLIPS_MID = 3, 2


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_banking_keys(rows, out_eval=EVAL, out_seeds=SEEDS, sample_n=SAMPLE_N,
                       n_random=N_RANDOM, n_near=N_NEAR, full_rate=FULL_RATE, seed=SEED) -> None:
    test_ids = [r["query_id"] for r in rows if r["split"] == "test"]
    sample = keys.choose_sample(test_ids, sample_n, seed)
    swaps = keys.plan_swaps([(r["query_id"], r["intent"]) for r in rows], set(sample), seed,
                            n_random, n_near, full_rate)
    _write(out_eval / "banking77_swaps.csv",
           ["query_id", "in_sample", "original_intent", "labelled_intent", "swap_type"],
           [s.__dict__ for s in swaps])
    _write(out_eval / "banking77_sample.csv", ["query_id"], [{"query_id": q} for q in sample])
    fam = keys.families(r["intent"] for r in rows)
    _write(out_eval / "intent_families.csv", ["intent", "family"],
           [{"intent": i, "family": f} for f, members in fam.items() for i in members])
    _write(out_seeds / "banking77_relabel.csv", ["query_id", "labelled_intent"],
           [{"query_id": s.query_id, "labelled_intent": s.labelled_intent} for s in swaps])
    _write(out_seeds / "banking77_sample.csv", ["query_id"], [{"query_id": q} for q in sample])


def _banking_rows() -> list[dict]:
    import pyarrow.parquet as pq
    return pq.read_table(DATA / "banking77.parquet").to_pylist()


def write_abt_keys() -> None:
    import pyarrow.parquet as pq
    labels = list(csv.DictReader((DATA / "abt_buy_labels.csv").open()))
    _write(EVAL / "abt_buy_pairs.csv", ["pair_id", "split", "label"], labels)
    pairs = {p["pair_id"]: p for p in pq.read_table(DATA / "abt_buy_pairs.parquet").to_pylist()}
    train = [(pairs[r["pair_id"]]["left_record"], pairs[r["pair_id"]]["right_record"],
              int(r["label"])) for r in labels if r["split"] == "train"]
    t = keys.fit_jaccard_threshold(train)
    (EVAL / "abt_buy_jaccard.txt").write_text(f"{t}\n")
    _write(SEEDS / "baseline_params.csv", ["name", "value"],
           [{"name": "abt_jaccard_threshold", "value": t}])
    print(f"abt: {len(labels)} labelled pairs · Jaccard threshold {t} (fit on train)")


def wanderbricks_template() -> None:
    from jevdbx.databricks import Sql
    r = Sql().run("select distinct comment from samples.wanderbricks.reviews "
                  "where comment is not null order by comment")
    _write(DATA / "wanderbricks_label_me.csv", ["comment", "polarity"],
           [{"comment": c, "polarity": ""} for (c,) in r.rows])
    print(f"wrote data/wanderbricks_label_me.csv ({len(r.rows)} comments): fill polarity with "
          "positive | negative | neutral, then run wanderbricks-commit")


def wanderbricks_commit() -> None:
    rows = list(csv.DictReader((DATA / "wanderbricks_label_me.csv").open()))
    bad = [r["comment"] for r in rows if r["polarity"] not in ("positive", "negative", "neutral")]
    if bad:
        sys.exit(f"unlabelled or invalid polarity for {len(bad)} comments")
    _write(EVAL / "wanderbricks_polarity.csv", ["comment_sha256", "polarity"],
           [{"comment_sha256": keys.comment_hash(r["comment"]), "polarity": r["polarity"]}
            for r in rows])


def write_wanderbricks_flips(states, out_eval=EVAL, out_seeds=SEEDS, seed=SEED) -> None:
    """states: natural (comment, rating) rows. Only comment hashes are written."""
    flips = keys.plan_flips([(keys.comment_hash(c), float(r)) for c, r in states], seed,
                            N_FLIPS_POLAR, N_FLIPS_MID)
    _write(out_eval / "wanderbricks_flips.csv", ["comment_sha256", "rating", "band"],
           [f.__dict__ for f in flips])
    _write(out_seeds / "wanderbricks_flips.csv", ["comment_sha256", "rating"],
           [{"comment_sha256": f.comment_sha256, "rating": f.rating} for f in flips])
    print(f"wanderbricks: {len(flips)} planted ratings over {len({c for c, _ in states})} comments")


def wanderbricks_flips() -> None:
    from jevdbx.databricks import Sql
    r = Sql().run("select distinct comment, round(rating, 1) from samples.wanderbricks.reviews "
                  "where comment is not null and rating is not null")
    write_wanderbricks_flips(r.rows)


def main(argv=None) -> None:
    cmd = (argv or sys.argv[1:] or [""])[0]
    {"banking": lambda: write_banking_keys(_banking_rows()), "abt": write_abt_keys,
     "wanderbricks-template": wanderbricks_template,
     "wanderbricks-commit": wanderbricks_commit,
     "wanderbricks-flips": wanderbricks_flips}.get(
        cmd, lambda: sys.exit(f"unknown command {cmd!r}"))()


if __name__ == "__main__":
    main()
