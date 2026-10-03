"""Scoring math for demo 06. Stdlib only."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Scores:
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float


def score(flagged: set, positives: set, universe: set) -> Scores:
    flagged, positives = flagged & universe, positives & universe
    tp = len(flagged & positives)
    fp = len(flagged - positives)
    fn = len(positives - flagged)
    tn = len(universe) - tp - fp - fn
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return Scores(tp, fp, fn, tn, p, r, f1)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def brier(probs: list[float], labels: list[bool]) -> float:
    return sum((p - float(y)) ** 2 for p, y in zip(probs, labels, strict=True)) / len(probs)


def reliability(probs, labels, bins: int = 10):
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        rate = sum(labels[i] for i in idx) / len(idx) if idx else 0.0
        out.append((lo, hi, rate, len(idx)))
    return out


def agreement(flags: dict[str, set], positives: set) -> dict[str, int]:
    out = {"all": 0, "some": 0, "none": 0} | {f"only_{j}": 0 for j in flags}
    for x in positives:
        who = [j for j, f in flags.items() if x in f]
        if len(who) == len(flags):
            out["all"] += 1
        elif not who:
            out["none"] += 1
        elif len(who) == 1:
            out[f"only_{who[0]}"] += 1
        else:
            out["some"] += 1
    return out
