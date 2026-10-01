"""Merge the two labellers' results of each blind audit into the committed label files.

Each audit (see scripts/audit_sample.py --labeller-copies) is labelled by two independent LLM
labellers, one Claude Opus and one Claude Sonnet, who saw only id, stars and body. Each returns a
file with the columns id,label (real|ok). Pre-registered tie rule (Ruling R26), conservative
against Jev: where they disagree, the precision audit takes `ok` and the key audit takes `real`.

    uv run python scripts/audit_merge.py \\
        --precision <opus.csv> <sonnet.csv> --flip <opus.csv> <sonnet.csv>

Writes eval/production_audit_labels.csv and/or eval/production_flip_audit_labels.csv (id,label
only) and eval/production_audit_agreement.json (per audit: n, raw agreement, Cohen's kappa, the tie
label and the disagreeing ids). Either audit can be merged on its own; nothing is written if any
requested audit fails validation (labels real|ok, the two files hold exactly the same ids, and the
ids are those of data/production_*audit.csv when that file exists).
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from jevdbx.audit import merge_labels, read_labels, write_labels

ROOT = Path(__file__).resolve().parents[1]
TIES = {"precision": "ok", "flip": "real"}
# audit -> (labels file, key in the agreement json, audit file written by audit_sample.py)
OUTPUTS = {
    "precision": ("production_audit_labels.csv", "precision_audit", "production_audit.csv"),
    "flip": ("production_flip_audit_labels.csv", "key_audit", "production_flip_audit.csv"),
}


def merge_audit(kind: str, path_a: Path, path_b: Path) -> tuple[dict[int, str], dict]:
    """Merge one audit's two result files with its pre-registered tie. Returns (merged, entry for
    the agreement json). Raises ValueError for anything inconsistent."""
    tie = TIES[kind]
    merged, agreement, kappa, disagreements = merge_labels(
        read_labels(path_a), read_labels(path_b), tie=tie)
    sample = ROOT / "data" / OUTPUTS[kind][2]
    if sample.exists():
        with open(sample, newline="", encoding="utf-8") as f:
            expected = {int(r["id"]) for r in csv.DictReader(f)}
        if expected != set(merged):
            raise ValueError(
                f"{kind}: the labelled ids are not the ids of the audit file {sample.name} "
                f"({len(set(merged) ^ expected)} differ)")
    entry = {"n": len(merged), "agreement": round(agreement, 4), "kappa": round(kappa, 4),
             "tie": tie, "disagreements": disagreements}
    return merged, entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--precision", nargs=2, type=Path, metavar=("A", "B"),
                        help="the two labellers' id,label files for the precision audit")
    parser.add_argument("--flip", nargs=2, type=Path, metavar=("A", "B"),
                        help="the two labellers' id,label files for the key audit")
    args = parser.parse_args(argv)
    requested = {k: v for k, v in (("precision", args.precision), ("flip", args.flip)) if v}
    if not requested:
        parser.error("give at least one of --precision A B, --flip A B")

    results = {kind: merge_audit(kind, *paths) for kind, paths in requested.items()}  # validate all
    agreement_path = ROOT / "eval" / "production_audit_agreement.json"
    agreement = json.loads(agreement_path.read_text()) if agreement_path.exists() else {}
    for kind, (merged, entry) in results.items():
        labels_name, key, _ = OUTPUTS[kind]
        write_labels(merged, ROOT / "eval" / labels_name)
        agreement[key] = entry
        real = sum(1 for v in merged.values() if v == "real")
        print(f"{key}: {entry['n']} labels ({real} real), agreement {entry['agreement']:.0%}, "
              f"kappa {entry['kappa']:.2f}, {len(entry['disagreements'])} "
              f"disagreement(s) resolved to {entry['tie']}; wrote eval/{labels_name}")
    agreement_path.write_text(json.dumps(agreement, indent=2, sort_keys=True) + "\n")
    print("wrote eval/production_audit_agreement.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
