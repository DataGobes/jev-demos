"""Blind audit labels: merging two independent labellers and reading/writing the label files.

Pure and offline. A label is `real` (the review's overall sentiment clearly contradicts its star
rating) or `ok` (anything else). Two labellers each label the same ids; where they disagree, the
pre-registered tie label decides (Ruling R26): `ok` for the precision audit, `real` for the key
audit, both conservative against Jev.
"""

import csv
from pathlib import Path

LABELS = ("real", "ok")


def _check(name: str, labels: dict[int, str]) -> None:
    bad = sorted({v for v in labels.values() if v not in LABELS})
    if bad:
        raise ValueError(f"labeller {name}: label must be 'real' or 'ok', got {bad}")


def cohens_kappa(a: dict[int, str], b: dict[int, str]) -> float:
    """Cohen's kappa of two labellers over the same ids. When chance agreement is 1 (both used a
    single label throughout) kappa is undefined; it is reported as 1.0 if they agreed, else 0.0."""
    n = len(a)
    observed = sum(1 for i in a if a[i] == b[i]) / n
    chance = sum((sum(1 for v in a.values() if v == lab) / n)
                 * (sum(1 for v in b.values() if v == lab) / n) for lab in LABELS)
    if chance == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - chance) / (1 - chance)


def merge_labels(
    a: dict[int, str], b: dict[int, str], tie: str
) -> tuple[dict[int, str], float, float, list[int]]:
    """Merge two labellers' labels. Returns (merged, raw agreement, Cohen's kappa, sorted ids on
    which they disagreed). Disagreements take the `tie` label. Raises ValueError for a label other
    than real/ok, an unknown `tie`, an empty input or ids that are not exactly the same."""
    if tie not in LABELS:
        raise ValueError(f"tie must be 'real' or 'ok', got {tie!r}")
    _check("a", a)
    _check("b", b)
    if set(a) != set(b):
        only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
        raise ValueError(f"the labellers' ids differ: {len(only_a)} only in a {only_a[:5]}, "
                         f"{len(only_b)} only in b {only_b[:5]}")
    if not a:
        raise ValueError("no labels to merge (empty input)")
    disagreements = sorted(i for i in a if a[i] != b[i])
    merged = {i: (a[i] if a[i] == b[i] else tie) for i in sorted(a)}
    agreement = 1 - len(disagreements) / len(a)
    return merged, agreement, cohens_kappa(a, b), disagreements


def read_labels(path: Path) -> dict[int, str]:
    """A labeller's result file (or a merged labels file): exactly the columns id,label; every
    label real|ok; no duplicate ids."""
    labels: dict[int, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["id", "label"]:
            raise ValueError(f"{path}: columns must be exactly id,label, got {reader.fieldnames}")
        for row in reader:
            i = int(row["id"])
            if i in labels:
                raise ValueError(f"{path}: duplicate id {i}")
            labels[i] = (row["label"] or "").strip()
    _check(str(path), labels)
    return labels


def write_labels(labels: dict[int, str], path: Path) -> None:
    """id,label only (no review text), sorted by id."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "label"])
        for i in sorted(labels):
            w.writerow([i, labels[i]])
