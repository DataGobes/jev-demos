from jevdbt.cache import Cache
from jevdbt.questions import Question


def test_roundtrip_and_isolation(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    q1, q2 = Question("a"), Question("b")
    c.put_many("m", q1, {'{"x":1}': 0.9, '{"x":2}': 0.1})
    result = c.get_many("m", q1, ['{"x":1}', '{"x":2}', '{"x":3}'])
    assert result == {'{"x":1}': 0.9, '{"x":2}': 0.1}
    assert c.get_many("m", q2, ['{"x":1}']) == {}
    assert c.get_many("other", q1, ['{"x":1}']) == {}


def test_many_keys_over_sqlite_variable_limit(tmp_path):
    c = Cache(tmp_path / "c.sqlite")
    q = Question("a")
    items = {f'{{"i":{i}}}': i / 3000 for i in range(2500)}
    c.put_many("m", q, items)
    assert c.get_many("m", q, list(items)) == items
