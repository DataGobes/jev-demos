"""Production dataset: Amazon Fine Food Reviews (SNAP, McAuley & Leskovec, WWW 2013).

Keeps only id, score, summary and text (drops user ids and profile names; `<br />` becomes a
newline and HTML entities are unescaped), samples 50,000 with seed 42, plants star flips across
the pole (1<->5, 2<->4) on 3% of the non-3-star rows, writes two Parquet files (47,500 + 2,500,
for the incremental proof) and eval/production_flips.csv.

    uv run python scripts/fetch_reviews.py --source data/finefoods.txt.gz --out data/
    uv run python scripts/fetch_reviews.py --source data/finefoods.txt.gz --out data/ --upload
    uv run python scripts/fetch_reviews.py --out data/ --upload-part2   # the incremental step

Downloading is a separate, explicit step (`--download`), done only after the user said yes.
"""

import argparse
import csv
import gzip
import html
import random
import re
import sys
import urllib.request
from collections.abc import Iterable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://snap.stanford.edu/data/finefoods.txt.gz"
FLIPS = {1: 5, 5: 1, 2: 4, 4: 2}
VOLUME = "/Volumes/jev_demo/production/raw"
PART1 = "reviews_part1.parquet"
PART2 = "reviews_part2.parquet"
_BR = re.compile(r"<br\s*/?\s*>", re.I)


def clean_markup(s: str) -> str:
    """`<br />` (any case or spacing) becomes a newline and HTML entities are unescaped: they are
    markup artifacts of the source, not review content (Ruling R21), and would reach Jev and the
    regex baseline alike. Entities are unescaped after the line breaks, so an escaped `&lt;br /&gt;`
    stays text."""
    return html.unescape(_BR.sub("\n", s))


def _record(n: int, rec: dict) -> dict:
    return {"id": n, "score": int(float(rec["review/score"])),
            "summary": clean_markup(rec.get("review/summary", "")),
            "text": clean_markup(rec.get("review/text", ""))}


def parse_snap(lines: Iterable[str]) -> Iterator[dict]:
    """Blocks of `key: value` lines separated by blank lines; ids are 1-based block numbers.
    Only score, summary and text are kept: user ids and profile names are dropped here."""
    rec: dict = {}
    n = 0
    for line in lines:
        line = line.rstrip("\r\n")
        if not line.strip():
            if rec:
                n += 1
                yield _record(n, rec)
                rec = {}
            continue
        key, _, value = line.partition(":")  # keys hold no colon; values may
        rec[key] = value.removeprefix(" ")
    if rec:
        n += 1
        yield _record(n, rec)


def parse_kaggle_csv(path: Path) -> Iterator[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            yield {"id": int(r["Id"]), "score": int(r["Score"]),
                   "summary": clean_markup(r["Summary"]), "text": clean_markup(r["Text"])}


def sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    ordered = sorted(rows, key=lambda r: r["id"])  # the draw must not depend on input order
    picked = random.Random(seed).sample(ordered, n)
    return sorted(picked, key=lambda r: r["id"])


def plant_flips(rows: list[dict], rate: float, seed: int) -> tuple[list[dict], list[dict]]:
    """Flip `rate` of the eligible (non-3-star) rows across the pole; 3 stars are never touched."""
    rng = random.Random(seed)
    eligible = [r["id"] for r in rows if r["score"] in FLIPS]
    chosen = set(rng.sample(eligible, round(len(eligible) * rate)))
    out, flips = [], []
    for r in rows:
        stars = r["score"]
        if r["id"] in chosen:
            stars = FLIPS[r["score"]]
            flips.append({"id": r["id"], "original_stars": r["score"], "planted_stars": stars})
        out.append({**r, "stars": stars})
    return out, flips


def split(rows: list, first: int) -> tuple[list, list]:
    return rows[:first], rows[first:]


def _read_source(path: Path) -> list[dict]:
    if path.suffix == ".csv":
        return list(parse_kaggle_csv(path))
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="latin-1") as f:
        return list(parse_snap(f))


def _write_parquet(rows: list[dict], path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({
        "id": [r["id"] for r in rows],
        "stars": [r["stars"] for r in rows],
        "summary": [r["summary"] for r in rows],
        "text": [r["text"] for r in rows],
    })
    pq.write_table(table, path)


def download(url: str, dest: Path) -> None:
    """Stream `url` to `dest` via `dest.part`, printing URL, destination and size first."""
    part = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(url) as resp:
            length = resp.headers.get("Content-Length")
            size = f"{int(length):,} bytes" if length else "size unknown"
            print(f"downloading {url} -> {dest} ({size})")
            with open(part, "wb") as fh:
                while chunk := resp.read(1 << 20):
                    fh.write(chunk)
        part.replace(dest)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def _upload(out: Path, names: tuple[str, ...]) -> None:
    from jevdbx.databricks import _client

    files = _client(None).files
    for name in names:
        with open(out / name, "rb") as fh:
            files.upload(f"{VOLUME}/{name}", fh, overwrite=True)
        print(f"uploaded {VOLUME}/{name}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=Path, help="finefoods.txt.gz (SNAP) or Kaggle Reviews.csv")
    ap.add_argument("--download", action="store_true",
                    help=f"fetch {URL} into --out (only after the user's go-ahead)")
    ap.add_argument("--out", type=Path, default=ROOT / "data")
    ap.add_argument("--n", type=int, default=50_000)
    ap.add_argument("--first", type=int, default=47_500)
    ap.add_argument("--rate", type=float, default=0.03)
    ap.add_argument("--upload", action="store_true", help=f"upload part 1 to {VOLUME}/")
    ap.add_argument("--upload-part2", action="store_true",
                    help="upload part 2 (the incremental step); needs no --source")
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.upload_part2 and not (args.source or args.download):
        _upload(args.out, (PART2,))
        return 0
    if args.download:
        args.source = args.out / "finefoods.txt.gz"
        download(URL, args.source)
    if not args.source:
        ap.error("--source or --download required")
    rows = _read_source(args.source)
    planted, flips = plant_flips(sample(rows, args.n, 42), args.rate, 42)
    a, b = split(planted, args.first)
    _write_parquet(a, args.out / PART1)
    _write_parquet(b, args.out / PART2)
    (ROOT / "eval").mkdir(parents=True, exist_ok=True)
    with open(ROOT / "eval/production_flips.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["id", "original_stars", "planted_stars"], lineterminator="\n")
        w.writeheader()
        w.writerows(flips)
    print(f"{len(rows):,} source rows -> {len(planted):,} sampled ({len(a):,} + {len(b):,}), "
          f"{len(flips):,} planted flips")
    if args.upload:
        _upload(args.out, (PART1,))  # part 2 is uploaded later: the incremental proof
    if args.upload_part2:
        _upload(args.out, (PART2,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
