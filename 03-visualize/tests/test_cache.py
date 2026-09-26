from jevviz.cache import Cache
from jevviz.types import Answer, Question

Q = {"a": Question("noul", "is a?"), "b": Question("score", "how?", ("lo", "hi"))}


def test_roundtrip_and_miss(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    assert c.get_many("m", "h1", Q) == {}
    c.put_many("m", "h1", Q, {"a": Answer("noul", noul=0.8),
                              "b": Answer("score", probabilities={0: 0.25, 1: 0.75}, confidence=0.5)})
    got = c.get_many("m", "h1", Q)
    assert got["a"].noul == 0.8
    assert got["b"].probabilities == {0: 0.25, 1: 0.75}
    assert c.get_many("m", "other-hash", Q) == {}
    assert c.get_many("other-model", "h1", Q) == {}
    c.close()
