from __future__ import annotations

from semsql.cache import Cache
from semsql.questions import Question


def test_round_trip_float_and_str() -> None:
    cache = Cache(":memory:")
    q_score = Question(kind="score", instructions="anger?", levels=("a", "b", "c"))
    q_choice = Question(kind="choice", instructions="pick", options=("x", "y"))

    cache.put_many("demo", q_score, {"hello": 1.0, "world": 2.0})
    cache.put_many("demo", q_choice, {"hello": "x"})

    hits = cache.get_many("demo", q_score, ["hello", "world", "missing"])
    assert hits == {"hello": 1.0, "world": 2.0}
    assert isinstance(hits["hello"], float)

    hits2 = cache.get_many("demo", q_choice, ["hello"])
    assert hits2 == {"hello": "x"}
    assert isinstance(hits2["hello"], str)
    cache.close()


def test_missing_keys_absent_from_result() -> None:
    cache = Cache(":memory:")
    q = Question(kind="noul", instructions="q")
    cache.put_many("demo", q, {"a": 0.5})
    hits = cache.get_many("demo", q, ["a", "b", "c"])
    assert hits == {"a": 0.5}
    cache.close()


def test_clear_empties_cache() -> None:
    cache = Cache(":memory:")
    q = Question(kind="noul", instructions="q")
    cache.put_many("demo", q, {"a": 0.5})
    cache.clear()
    assert cache.get_many("demo", q, ["a"]) == {}
    cache.close()


def test_different_models_do_not_collide() -> None:
    cache = Cache(":memory:")
    q = Question(kind="noul", instructions="q")
    cache.put_many("model-a", q, {"text": 0.1})
    cache.put_many("model-b", q, {"text": 0.9})
    assert cache.get_many("model-a", q, ["text"]) == {"text": 0.1}
    assert cache.get_many("model-b", q, ["text"]) == {"text": 0.9}
    cache.close()


def test_different_questions_do_not_collide() -> None:
    cache = Cache(":memory:")
    q1 = Question(kind="noul", instructions="Is this angry?")
    q2 = Question(kind="noul", instructions="Is this urgent?")
    cache.put_many("demo", q1, {"text": 0.2})
    cache.put_many("demo", q2, {"text": 0.8})
    assert cache.get_many("demo", q1, ["text"]) == {"text": 0.2}
    assert cache.get_many("demo", q2, ["text"]) == {"text": 0.8}
    cache.close()


def test_put_many_upserts_existing_key() -> None:
    cache = Cache(":memory:")
    q = Question(kind="noul", instructions="q")
    cache.put_many("demo", q, {"text": 0.1})
    cache.put_many("demo", q, {"text": 0.7})
    assert cache.get_many("demo", q, ["text"]) == {"text": 0.7}
    cache.close()


def test_empty_inputs_are_noops() -> None:
    cache = Cache(":memory:")
    q = Question(kind="noul", instructions="q")
    cache.put_many("demo", q, {})
    assert cache.get_many("demo", q, []) == {}
    cache.close()


def test_persists_to_file(tmp_path) -> None:
    path = tmp_path / "cache.sqlite"
    q = Question(kind="noul", instructions="q")
    cache = Cache(path)
    cache.put_many("demo", q, {"a": 0.3})
    cache.close()

    cache2 = Cache(path)
    assert cache2.get_many("demo", q, ["a"]) == {"a": 0.3}
    cache2.close()


def test_get_many_large_batch_exceeds_sqlite_variable_limit() -> None:
    cache = Cache(":memory:")
    q = Question(kind="noul", instructions="q")
    texts = [f"text-{i}" for i in range(2500)]
    items = {t: float(i) for i, t in enumerate(texts)}
    cache.put_many("demo", q, items)
    hits = cache.get_many("demo", q, texts)
    assert hits == items
    cache.close()
