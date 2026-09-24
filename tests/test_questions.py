import json

import pytest

from jevdbt.questions import Question


def test_from_json_instructions_only():
    q = Question.from_json(json.dumps({"instructions": "Contains PII"}))
    assert q == Question("Contains PII")


def test_from_json_with_criteria():
    raw = json.dumps({"instructions": "x", "criteria": {"true": "yes-case", "false": "no-case"}})
    q = Question.from_json(raw)
    assert (q.criteria_true, q.criteria_false) == ("yes-case", "no-case")


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        '{"criteria": {}}',
        '{"instructions": "  "}',
        '{"instructions": "x", "criteria": {"maybe": "y"}}',
    ],
)
def test_from_json_rejects_bad_input(raw):
    with pytest.raises(ValueError):
        Question.from_json(raw)


def test_key_is_stable_and_distinguishes_criteria():
    assert Question("a").key() == Question("a").key()
    assert Question("a").key() != Question("a", "t").key()


def test_for_packed_row_prefixes_and_rewrites_column_refs():
    q = Question(
        "The comment contradicts `reason_code`", criteria_true="unlike `reason_code`"
    )
    packed = q.for_packed_row("r003")
    expected_start = "Judge ONLY the record in `rows.r003`, ignoring all other rows. "
    assert packed.instructions.startswith(expected_start)
    assert "`rows.r003.reason_code`" in packed.instructions
    assert packed.criteria_true == "unlike `rows.r003.reason_code`"
    assert packed.criteria_false is None
