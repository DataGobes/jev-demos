"""What the production run's missed flips have in common: a breakdown of the stored live run.

Reads, for every planted flip in eval/production_flips.csv, the review as loaded
(jev_demo.jaffle_shop.stg_product_reviews), its stored LIVE judgment (jev_demo.jev.judgments,
matched by the test's state, `{"body", "stars"}`) and whether the stored-failure table flagged it.
No Jev call is made: it only reads what the logged production run stored.

Prints, per flip type (original -> planted stars): planted, missed, recall, share of the misses and
the median p of the misses; the misses by p band (how many sat just under the threshold); the
median length in words of caught vs missed flips; and the key-audit labels of the audited misses.

    uv run python scripts/miss_analysis.py            # print the section
    uv run python scripts/miss_analysis.py --append   # also append it to docs/eval-results.md

It refuses to print or append if a flip has no live judgment, a flip has more than one, or the
stored-failure table disagrees with `p >= threshold`.
"""

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLIPS_PATH = ROOT / "eval" / "production_flips.csv"
FLIP_LABELS_PATH = ROOT / "eval" / "production_flip_audit_labels.csv"
DOCS_PATH = ROOT / "docs" / "eval-results.md"
TEST = "product_reviews_body_matches_stars"
THRESHOLD = 0.8  # the test's threshold in jaffle_shop/models/production/schema.yml
FLIP_TYPES = [(4, 2), (5, 1), (2, 4), (1, 5)]
# p bands for the misses (all below THRESHOLD); the last one is "just under the threshold"
BANDS = [(0.0, 0.2), (0.2, 0.5), (0.5, 0.7), (0.7, THRESHOLD)]


@dataclass(frozen=True)
class Flip:
    review_id: int
    original: int
    planted: int
    p: float
    flagged: bool
    words: int


def query(ids: list[int]) -> str:
    return f"""
select s.review_id, s.stars, size(split(trim(s.body), '\\\\s+')) as words, j.p,
       (f.review_id is not null) as flagged
from jev_demo.jaffle_shop.stg_product_reviews s
left join jev_demo.jev.judgments j
  on j.test_name = '{TEST}' and j.mode = 'live'
 and j.state = to_json(named_struct('body', s.body, 'stars', s.stars))
left join jev_demo.jaffle_shop_dbt_test__audit.{TEST} f
  on f.review_id = s.review_id and f.jev_p is not null
where s.review_id in ({", ".join(map(str, ids))})
"""


def to_flips(rows: list[tuple], planted: dict[int, tuple[int, int]]) -> list[Flip]:
    """Validated flips: one live judgment each, loaded with the planted stars, and flagged exactly
    when p >= THRESHOLD. Raises ValueError otherwise."""
    seen: dict[int, Flip] = {}
    for review_id, stars, words, p, flagged in rows:
        rid = int(review_id)
        original, want = planted[rid]
        if rid in seen:
            raise ValueError(f"review {rid}: more than one live judgment")
        if p is None:
            raise ValueError(f"review {rid}: no live judgment")
        if int(stars) != want:
            raise ValueError(f"review {rid}: loaded with {stars} stars, planted {want}")
        flagged = flagged in (True, "true", "True")
        if flagged != (float(p) >= THRESHOLD):
            raise ValueError(f"review {rid}: flagged={flagged} but p={p}")
        seen[rid] = Flip(rid, original, want, float(p), flagged, int(words))
    missing = set(planted) - set(seen)
    if missing:
        raise ValueError(f"{len(missing)} planted flips not loaded, e.g. {min(missing)}")
    return sorted(seen.values(), key=lambda f: f.review_id)


def band_of(p: float) -> str:
    for lo, hi in BANDS:
        if lo <= p < hi:
            return f"{lo:.1f}–{hi:.1f}"
    raise ValueError(f"p={p} is not a miss")


def section(flips: list[Flip], flip_audit: dict[int, str] | None, stamp: str) -> str:
    misses = [f for f in flips if not f.flagged]
    caught = len(flips) - len(misses)
    out = [
        f"## Production misses ({stamp})",
        "",
        "What the missed planted flips have in common. Read from the stored LIVE judgments of the",
        "production run above (no Jev call; `scripts/miss_analysis.py`). A miss is a planted flip "
        f"with p < {THRESHOLD}.",
        "",
        f"{len(flips):,} planted flips · {caught:,} caught · {len(misses)} missed · "
        f"recall {caught / len(flips):.2f}",
        "",
        "| flip | planted | missed | recall | share of misses | median p of misses |",
        "|---|---|---|---|---|---|",
    ]
    for orig, new in FLIP_TYPES:
        group = [f for f in flips if (f.original, f.planted) == (orig, new)]
        if not group:
            continue
        m = [f for f in group if not f.flagged]
        med = f"{statistics.median(f.p for f in m):.2f}" if m else "–"
        out.append(f"| {orig} → {new} | {len(group)} | {len(m)} | "
                   f"{1 - len(m) / len(group):.2f} | {len(m) / len(misses):.0%} | {med} |")
    out += ["", "Misses by p band:", ""]
    out += ["| flip | " + " | ".join(band_of(lo) for lo, _ in BANDS) + " |",
            "|---|" + "---|" * len(BANDS)]
    for kind in FLIP_TYPES + [None]:
        m = [f for f in misses if kind is None or (f.original, f.planted) == kind]
        if kind is not None and not any((f.original, f.planted) == kind for f in flips):
            continue
        counts = [sum(1 for f in m if band_of(f.p) == band_of(lo)) for lo, _ in BANDS]
        name = "all" if kind is None else f"{kind[0]} → {kind[1]}"
        out.append(f"| {name} | " + " | ".join(map(str, counts)) + " |")
    near = sum(1 for f in misses if f.p >= BANDS[-1][0])
    out += [
        "",
        f"- Just under the threshold (p {BANDS[-1][0]}–{THRESHOLD}): {near} of {len(misses)} "
        "misses; the rest were not close.",
        f"- Length: median {statistics.median(f.words for f in flips if f.flagged):g} words "
        f"for caught flips, {statistics.median(f.words for f in misses):g} for missed ones.",
    ]
    if flip_audit:
        audited = [flip_audit[f.review_id] for f in misses if f.review_id in flip_audit]
        out.append(f"- Key audit: {len(audited)} of the 100 audited planted flips are misses; "
                   f"{audited.count('real')} labelled real, {audited.count('ok')} ok.")
    return "\n".join(out) + "\n"


def read_planted() -> dict[int, tuple[int, int]]:
    with open(FLIPS_PATH, newline="") as f:
        return {int(r["id"]): (int(r["original_stars"]), int(r["planted_stars"]))
                for r in csv.DictReader(f)}


def read_flip_audit() -> dict[int, str] | None:
    if not FLIP_LABELS_PATH.exists():
        return None
    with open(FLIP_LABELS_PATH, newline="") as f:
        return {int(r["id"]): r["label"] for r in csv.DictReader(f)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--append", action="store_true", help="append to docs/eval-results.md")
    args = ap.parse_args()

    from jevdbx.databricks import Sql

    planted = read_planted()
    res = Sql().run(query(sorted(planted)))
    if res.state != "SUCCEEDED":
        raise SystemExit(f"could not read the stored judgments: {res.error or res.state}")
    try:
        flips = to_flips(res.rows, planted)
    except ValueError as e:
        raise SystemExit(f"miss_analysis: {e}") from None
    text = section(flips, read_flip_audit(), datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    print(text)
    if args.append:
        with DOCS_PATH.open("a") as f:
            f.write("\n" + text)
        print(f"appended to {DOCS_PATH.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
