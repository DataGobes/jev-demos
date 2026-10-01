from jevdbx import keys

INTENTS = ["card_arrival", "card_delivery_estimate", "card_linking", "top_up_failed",
           "top_up_limits", "exchange_rate", "age_limit"]


def test_families_group_by_leading_token():
    assert keys.intent_family("card_arrival") == "card"
    assert keys.intent_family("top_up_failed") == "top_up"
    fam = keys.families(INTENTS)
    assert fam["card"] == ["card_arrival", "card_delivery_estimate", "card_linking"]
    assert fam["exchange"] == ["exchange_rate"]


def test_sample_is_deterministic():
    ids = [f"test-{i:05d}" for i in range(100)]
    assert keys.choose_sample(ids, 10, seed=7) == keys.choose_sample(ids, 10, seed=7)
    assert len(set(keys.choose_sample(ids, 10, seed=7))) == 10


def test_plan_swaps_counts_types_and_targets():
    rows = [(f"q{i}", INTENTS[i % len(INTENTS)]) for i in range(400)]
    sample = {f"q{i}" for i in range(200)}
    # seed 7: expected out-of-sample count ~8.6 (sd ~2.9); seed 42 draws 5 by chance
    swaps = keys.plan_swaps(rows, sample, seed=7, n_random=10, n_near=10, full_rate=0.05)
    in_s = [s for s in swaps if s.in_sample]
    assert sum(s.swap_type == "random" for s in in_s) == 10
    assert sum(s.swap_type == "near_miss" for s in in_s) == 10
    for s in swaps:
        assert s.labelled_intent != s.original_intent
        same = keys.intent_family(s.labelled_intent) == keys.intent_family(s.original_intent)
        assert same == (s.swap_type == "near_miss")
    out = [s for s in swaps if not s.in_sample]
    assert 6 <= len(out) <= 14   # ~5% of 200, split between types
    assert swaps == keys.plan_swaps(rows, sample, 7, 10, 10, 0.05)


def test_near_miss_only_from_families_with_siblings():
    # q3 (outside the sample) gives card_arrival a sibling; exchange_rate has none
    rows = [("q1", "exchange_rate"), ("q2", "card_arrival"), ("q3", "card_linking")]
    swaps = keys.plan_swaps(rows, {"q1", "q2"}, seed=1, n_random=0, n_near=1, full_rate=0)
    assert [s.query_id for s in swaps] == ["q2"]


def test_jaccard_and_threshold():
    assert keys.jaccard("Sony TV 40in", "sony tv 40-in") == 1.0
    pairs = [("a b c", "a b c", 1), ("a b c", "a b d", 1), ("a b", "x y", 0), ("a b c d", "a x", 0)]
    t = keys.fit_jaccard_threshold(pairs)
    assert 0.2 < t <= 0.5


def test_wanderbricks_rule_and_ids():
    assert keys.contradiction("negative", 4.0) and keys.contradiction("positive", 2.0)
    assert not keys.contradiction("negative", 3.9) and not keys.contradiction("neutral", 1.0)
    assert keys.state_id("Nice", 4.0) == keys.state_id("Nice", 4.04)
    assert len(keys.comment_hash("Nice")) == 64


def test_rating_band():
    assert keys.rating_band([1.0, 2.4]) == "low"
    assert keys.rating_band([4.0, 5.0]) == "high"
    assert keys.rating_band([2.5, 3.9]) == "mid" and keys.rating_band([2.0, 4.5]) == "mid"


def test_plan_flips_are_seeded_opposite_band_and_never_natural():
    states = [("h_low", 1.0), ("h_low", 2.4), ("h_high", 4.0), ("h_high", 5.0),
              ("h_mid", 3.0), ("h_mid", 3.5)]
    flips = keys.plan_flips(states, seed=42, n_polar=3, n_mid=2)
    assert flips == keys.plan_flips(states, seed=42, n_polar=3, n_mid=2)
    by: dict[str, list] = {}
    for f in flips:
        by.setdefault(f.comment_sha256, []).append(f)
    assert len(by["h_low"]) == 3 and all(f.band == "low" and f.rating >= 4.0 for f in by["h_low"])
    assert len(by["h_high"]) == 3 and all(f.rating <= 2.0 for f in by["h_high"])
    mid = sorted(f.rating for f in by["h_mid"])
    assert len(mid) == 2 and mid[0] <= 2.0 and mid[1] >= 4.0
    assert not any((f.comment_sha256, f.rating) in set(states) for f in flips)
