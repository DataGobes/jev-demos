import math

from jevdbx import metrics


def test_score_counts_and_rates():
    s = metrics.score({1, 2, 3}, {2, 3, 4}, set(range(10)))
    assert (s.tp, s.fp, s.fn, s.tn) == (2, 1, 1, 6)
    assert math.isclose(s.precision, 2 / 3) and math.isclose(s.recall, 2 / 3)
    assert math.isclose(s.f1, 2 / 3)


def test_score_empty_flags_is_zero_not_nan():
    s = metrics.score(set(), {1}, {1, 2})
    assert s.precision == 0.0 and s.recall == 0.0 and s.f1 == 0.0


def test_wilson_matches_known_value():
    lo, hi = metrics.wilson(94, 100)
    assert round(lo, 3) == 0.875 and round(hi, 3) == 0.972
    assert metrics.wilson(0, 0) == (0.0, 1.0)


def test_brier_and_reliability():
    assert metrics.brier([1.0, 0.0], [True, False]) == 0.0
    bins = metrics.reliability([0.05, 0.95, 0.9], [False, True, True], bins=2)
    assert bins[0] == (0.0, 0.5, 0.0, 1) and bins[1] == (0.5, 1.0, 1.0, 2)


def test_agreement_on_positives():
    a = metrics.agreement({"jev": {1, 2}, "llm": {2, 3}}, positives={1, 2, 3, 4})
    assert a == {"all": 1, "none": 1, "only_jev": 1, "only_llm": 1}
