from __future__ import annotations

import pytest

from semsql.questions import Question, load_rubrics


def test_noul_question_valid() -> None:
    q = Question(kind="noul", instructions="Is this about a refund?")
    assert q.kind == "noul"


def test_noul_requires_instructions() -> None:
    with pytest.raises(ValueError):
        Question(kind="noul", instructions="")
    with pytest.raises(ValueError):
        Question(kind="noul", instructions="   ")


def test_score_requires_two_levels() -> None:
    with pytest.raises(ValueError):
        Question(kind="score", instructions="x", levels=("only one",))
    Question(kind="score", instructions="x", levels=("a", "b"))


def test_choice_requires_two_to_255_options() -> None:
    with pytest.raises(ValueError):
        Question(kind="choice", instructions="x", options=("only one",))
    with pytest.raises(ValueError):
        Question(
            kind="choice", instructions="x", options=tuple(f"o{i}" for i in range(256))
        )
    Question(kind="choice", instructions="x", options=("a", "b"))
    Question(
        kind="choice", instructions="x", options=tuple(f"o{i}" for i in range(255))
    )


def test_key_is_stable_and_distinguishes_fields() -> None:
    q1 = Question(kind="noul", instructions="Is this angry?")
    q2 = Question(kind="noul", instructions="Is this angry?")
    assert q1.key() == q2.key()

    q3 = Question(kind="score", instructions="x", levels=("a", "b"))
    q4 = Question(kind="score", instructions="x", levels=("a", "c"))
    assert q3.key() != q4.key()

    q5 = Question(kind="choice", instructions="x", options=("a", "b"))
    q6 = Question(kind="noul", instructions="x")
    assert q5.key() != q6.key()


def test_key_distinguishes_option_order() -> None:
    q1 = Question(kind="choice", instructions="x", options=("a", "b"))
    q2 = Question(kind="choice", instructions="x", options=("b", "a"))
    assert q1.key() != q2.key()


def test_load_rubrics_default_ships_expected_names() -> None:
    rubrics = load_rubrics()
    for name in ("anger", "urgency", "churn_risk", "review_quality"):
        assert name in rubrics
        question = rubrics[name]
        assert question.kind == "score"
        assert len(question.levels) >= 3
        assert question.instructions.strip()
        for level in question.levels:
            assert level.strip()


def test_load_rubrics_from_explicit_path(tmp_path) -> None:
    path = tmp_path / "custom.toml"
    path.write_text(
        """
        [demo]
        instructions = "Is the writer happy?"
        levels = ["Unhappy", "Neutral", "Happy"]

        [ask]
        instructions = "Is this a question?"
        """
    )
    rubrics = load_rubrics(path)
    assert rubrics["demo"].kind == "score"
    assert rubrics["demo"].levels == ("Unhappy", "Neutral", "Happy")
    assert rubrics["ask"].kind == "noul"


def test_load_rubrics_choice_variant(tmp_path) -> None:
    path = tmp_path / "custom.toml"
    path.write_text(
        """
        [pick]
        instructions = "Which fruit?"
        options = ["apple", "pear"]
        """
    )
    rubrics = load_rubrics(path)
    assert rubrics["pick"].kind == "choice"
    assert rubrics["pick"].options == ("apple", "pear")


def test_load_rubrics_missing_instructions_raises(tmp_path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text('[bad]\nlevels = ["a", "b"]\n')
    with pytest.raises(ValueError):
        load_rubrics(path)
