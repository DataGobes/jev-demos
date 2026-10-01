"""Download the two public datasets (confirm-first), write parquet to data/, upload to the
volume (confirm-first). Labels never go into the parquet files.

    uv run python scripts/fetch_data.py --download      # Banking77 + entity-matching files
    uv run python scripts/fetch_data.py --upload        # data/*.parquet -> /Volumes/.../raw/
"""

import argparse
import csv
import io
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VOLUME = "/Volumes/jev_demo/bench/raw"


def banking_rows(csv_text: str, split: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    return [{"query_id": f"{split}-{i:05d}", "split": split, "query": r["text"],
             "intent": r["category"]} for i, r in enumerate(reader)]


def record_text(row: dict) -> str:
    parts = [row.get("name", ""), row.get("description", ""), row.get("price", "")]
    return " | ".join(p.strip() for p in parts if p and p.strip())


def abt_pairs(table_a: str, table_b: str, pairs_csv: str, split: str) -> list[dict]:
    a = {r["id"]: r for r in csv.DictReader(io.StringIO(table_a))}
    b = {r["id"]: r for r in csv.DictReader(io.StringIO(table_b))}
    out = []
    for p in csv.DictReader(io.StringIO(pairs_csv)):
        out.append({"pair_id": f"{split}-{p['ltable_id']}-{p['rtable_id']}", "split": split,
                    "left_record": record_text(a[p["ltable_id"]]),
                    "right_record": record_text(b[p["rtable_id"]])})
    return out


def abt_labels(pairs_csv: str, split: str) -> list[dict]:
    return [{"pair_id": f"{split}-{p['ltable_id']}-{p['rtable_id']}", "split": split,
             "label": int(p["label"])} for p in csv.DictReader(io.StringIO(pairs_csv))]


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def download(sources: dict) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    DATA.mkdir(exist_ok=True)
    bk = sources["banking77"]
    rows = banking_rows(_get(bk["train_url"]), "train") + banking_rows(_get(bk["test_url"]), "test")
    pq.write_table(pa.Table.from_pylist(rows), DATA / "banking77.parquet")
    ab = sources["abt_buy"]
    ta, tb = _get(ab["table_a_url"]), _get(ab["table_b_url"])
    pairs, labels = [], []
    for split in ("train", "valid", "test"):
        text = _get(ab[f"{split}_url"])
        pairs += abt_pairs(ta, tb, text, split)
        labels += abt_labels(text, split)
    pq.write_table(pa.Table.from_pylist(pairs), DATA / "abt_buy_pairs.parquet")
    with (DATA / "abt_buy_labels.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pair_id", "split", "label"])
        w.writeheader()
        w.writerows(labels)
    print(f"banking77: {len(rows)} rows · abt_buy: {len(pairs)} pairs "
          f"({sum(r['label'] for r in labels)} matches)")


def upload() -> None:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    for name in ("banking77.parquet", "abt_buy_pairs.parquet"):
        with (DATA / name).open("rb") as f:
            w.files.upload(f"{VOLUME}/{name}", f, overwrite=True)
        print(f"uploaded {name} -> {VOLUME}/{name}")


def parse_args(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--upload", action="store_true")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    a = parse_args(argv)
    if a.download:
        download(tomllib.loads((ROOT / "eval" / "sources.toml").read_text()))
    if a.upload:
        upload()
    if not (a.download or a.upload):
        print("nothing to do: pass --download and/or --upload (each needs the user's OK)")


if __name__ == "__main__":
    main()
