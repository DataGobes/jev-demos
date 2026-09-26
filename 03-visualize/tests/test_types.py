import pytest

from jevviz.types import Column, Profile, Question


def col(name, kind, distinct=5, position=0):
    return Column(name=name, kind=kind, distinct=distinct, null_share=0.0,
                  min=None, max=None, samples=("a",), evenly_spaced=False, position=position)


def test_question_key_is_stable_and_distinguishes_levels():
    a = Question("score", "how well", ("bad", "good"))
    b = Question("score", "how well", ("bad", "great"))
    assert a.key() == Question("score", "how well", ("bad", "good")).key()
    assert a.key() != b.key()


def test_score_needs_two_levels():
    with pytest.raises(ValueError):
        Question("score", "x", ("only",))


def test_profile_hash_deterministic_and_order_sensitive():
    p1 = Profile((col("a", ("nominal",)), col("b", ("quantitative",), position=1)), 10)
    p2 = Profile((col("a", ("nominal",)), col("b", ("quantitative",), position=1)), 10)
    p3 = Profile((col("a", ("nominal",)),), 10)
    assert p1.hash() == p2.hash()
    assert p1.hash() != p3.hash()


def test_by_kind_includes_dual_tagged_columns():
    rating = col("rating", ("nominal", "quantitative"))
    p = Profile((rating,), 5)
    assert p.by_kind("nominal") == [rating]
    assert p.by_kind("quantitative") == [rating]
