"""Ground-truth construction for demo 06. Pure functions, stdlib only; seeds make every key
reproducible. Never edit a committed key to make a judge win."""

import hashlib
import random
import re
from collections.abc import Iterable
from dataclasses import dataclass


def intent_family(intent: str) -> str:
    parts = intent.split("_")
    return "_".join(parts[:2]) if parts[0] == "top" and len(parts) > 1 else parts[0]


def families(intents: Iterable[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for i in sorted(set(intents)):
        out.setdefault(intent_family(i), []).append(i)
    return out


@dataclass(frozen=True)
class Swap:
    query_id: str
    in_sample: bool
    original_intent: str
    labelled_intent: str
    swap_type: str  # random | near_miss


def choose_sample(test_ids: list[str], n: int, seed: int) -> list[str]:
    return sorted(random.Random(seed).sample(sorted(test_ids), n))


def _swap(rng, qid, intent, kind, fam, all_intents, in_sample) -> Swap | None:
    if kind == "near_miss":
        options = [i for i in fam[intent_family(intent)] if i != intent]
    else:
        options = [i for i in all_intents if intent_family(i) != intent_family(intent)]
    if not options:
        return None
    return Swap(qid, in_sample, intent, rng.choice(options), kind)


def plan_swaps(rows: list[tuple[str, str]], sample: set[str], seed: int, n_random: int,
               n_near: int, full_rate: float) -> list[Swap]:
    rng = random.Random(seed)
    all_intents = sorted({i for _, i in rows})
    fam = families(all_intents)
    has_sibling = {i for members in fam.values() if len(members) > 1 for i in members}
    rows = sorted(rows)
    swaps: list[Swap] = []
    in_s = [r for r in rows if r[0] in sample]
    rng.shuffle(in_s)
    near_pool = [r for r in in_s if r[1] in has_sibling]
    near = near_pool[:n_near]
    taken = {q for q, _ in near}
    rand = [r for r in in_s if r[0] not in taken][:n_random]
    for qid, intent in near:
        swaps.append(_swap(rng, qid, intent, "near_miss", fam, all_intents, True))
    for qid, intent in rand:
        swaps.append(_swap(rng, qid, intent, "random", fam, all_intents, True))
    for qid, intent in [r for r in rows if r[0] not in sample]:
        u = rng.random()
        if u < full_rate / 2 and intent in has_sibling:
            swaps.append(_swap(rng, qid, intent, "near_miss", fam, all_intents, False))
        elif full_rate / 2 <= u < full_rate:
            swaps.append(_swap(rng, qid, intent, "random", fam, all_intents, False))
    return sorted((s for s in swaps if s), key=lambda s: s.query_id)


_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower().replace("-", "")))


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def fit_jaccard_threshold(pairs: list[tuple[str, str, int]]) -> float:
    """The threshold in (0, 1] that maximises F1 of `jaccard >= t` on labelled pairs."""
    scored = [(jaccard(a, b), y) for a, b, y in pairs]
    best_t, best_f1 = 1.0, -1.0
    for t in sorted({s for s, _ in scored if s > 0}):
        tp = sum(1 for s, y in scored if s >= t and y)
        fp = sum(1 for s, y in scored if s >= t and not y)
        fn = sum(1 for s, y in scored if s < t and y)
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        if f1 > best_f1:
            best_t, best_f1 = t, f1
    return round(best_t, 4)


def comment_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def state_id(comment: str, rating: float) -> str:
    return hashlib.sha256(f"{comment}|{rating:.1f}".encode()).hexdigest()


def contradiction(polarity: str, rating: float) -> bool:
    r = round(rating, 1)
    return (polarity == "negative" and r >= 4.0) or (polarity == "positive" and r <= 2.0)


RATING_GRID = [round(1.0 + 0.1 * i, 1) for i in range(41)]  # 1.0 .. 5.0


def rating_band(ratings: Iterable[float]) -> str:
    """A comment's natural rating band: low (all <= 2.4), high (all >= 4.0), else mid."""
    rs = [round(r, 1) for r in ratings]
    if max(rs) <= 2.4:
        return "low"
    if min(rs) >= 4.0:
        return "high"
    return "mid"


@dataclass(frozen=True)
class Flip:
    comment_sha256: str
    rating: float
    band: str  # the comment's natural band


def plan_flips(states: list[tuple[str, float]], seed: int, n_polar: int,
               n_mid: int) -> list[Flip]:
    """Seeded planted ratings (states = natural (comment_sha256, rating) pairs). A low-band
    comment gets n_polar ratings from 4.0-5.0, a high-band one n_polar from 1.0-2.0; a mid-band
    comment gets n_mid alternating from 1.0-2.0 and 4.0-5.0. Never a natural state. Whether a
    planted state is a contradiction is decided later by the polarity labels and the rule."""
    rng = random.Random(seed)
    by_comment: dict[str, set[float]] = {}
    for h, r in states:
        by_comment.setdefault(h, set()).add(round(r, 1))
    low = [r for r in RATING_GRID if r <= 2.0]
    high = [r for r in RATING_GRID if r >= 4.0]
    out: list[Flip] = []
    for h in sorted(by_comment):
        natural = by_comment[h]
        band = rating_band(natural)
        if band == "mid":
            picks: list[float] = []
            for i in range(n_mid):
                pool = [r for r in (low if i % 2 == 0 else high)
                        if r not in natural and r not in picks]
                picks.append(rng.choice(pool))
        else:
            picks = rng.sample([r for r in (high if band == "low" else low) if r not in natural],
                               n_polar)
        out += [Flip(h, r, band) for r in sorted(picks)]
    return out
