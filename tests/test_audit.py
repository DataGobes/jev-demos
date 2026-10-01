import pytest

from jevdbx import audit


def test_merge_agreeing_labels_keeps_them():
    a = {1: "real", 2: "ok", 3: "ok"}
    merged, agreement, kappa, disagreements = audit.merge_labels(a, dict(a), tie="ok")
    assert merged == a and agreement == 1.0 and kappa == 1.0 and disagreements == []


def test_merge_resolves_disagreements_with_the_tie_label():
    a = {1: "real", 2: "ok", 3: "real", 4: "ok"}
    b = {1: "real", 2: "real", 3: "ok", 4: "ok"}
    merged, agreement, _, disagreements = audit.merge_labels(a, b, tie="ok")
    assert merged == {1: "real", 2: "ok", 3: "ok", 4: "ok"}
    assert disagreements == [2, 3] and agreement == 0.5
    merged, _, _, _ = audit.merge_labels(a, b, tie="real")
    assert merged == {1: "real", 2: "real", 3: "real", 4: "ok"}


def test_kappa_matches_the_textbook_value():
    # 20 items: both real 10, both ok 5, a real/b ok 3, a ok/b real 2
    a = {i: "real" for i in range(13)} | {i: "ok" for i in range(13, 20)}
    b = ({i: "real" for i in range(10)} | {i: "ok" for i in range(10, 13)}
         | {13: "real", 14: "real"} | {i: "ok" for i in range(15, 20)})
    _, agreement, kappa, _ = audit.merge_labels(a, b, tie="ok")
    assert agreement == pytest.approx(15 / 20)
    # pe = (13/20)(12/20) + (7/20)(8/20) = 0.39 + 0.14 = 0.53 ; kappa = (0.75-0.53)/(1-0.53)
    assert kappa == pytest.approx((0.75 - 0.53) / 0.47)


def test_kappa_when_both_labellers_use_one_label_everywhere():
    a = {1: "ok", 2: "ok"}
    assert audit.merge_labels(a, dict(a), tie="ok")[2] == 1.0  # degenerate: chance agreement is 1


def test_kappa_is_zero_or_negative_for_systematic_disagreement():
    a = {1: "real", 2: "real", 3: "ok", 4: "ok"}
    b = {1: "ok", 2: "ok", 3: "real", 4: "real"}
    _, agreement, kappa, _ = audit.merge_labels(a, b, tie="ok")
    assert agreement == 0.0 and kappa == pytest.approx(-1.0)


def test_labels_must_be_real_or_ok():
    with pytest.raises(ValueError, match="real"):
        audit.merge_labels({1: "maybe"}, {1: "ok"}, tie="ok")
    with pytest.raises(ValueError, match="real"):
        audit.merge_labels({1: "ok"}, {1: ""}, tie="ok")


def test_ids_must_match_exactly():
    with pytest.raises(ValueError, match="ids"):
        audit.merge_labels({1: "ok", 2: "ok"}, {1: "ok"}, tie="ok")
    with pytest.raises(ValueError, match="ids"):
        audit.merge_labels({1: "ok"}, {2: "ok"}, tie="ok")


def test_tie_must_be_a_label_and_the_input_is_not_empty():
    with pytest.raises(ValueError, match="tie"):
        audit.merge_labels({1: "ok"}, {1: "ok"}, tie="maybe")
    with pytest.raises(ValueError, match="empty"):
        audit.merge_labels({}, {}, tie="ok")


def test_read_and_write_label_files_roundtrip(tmp_path):
    p = tmp_path / "labels.csv"
    audit.write_labels({3: "ok", 1: "real"}, p)
    assert p.read_text() == "id,label\n1,real\n3,ok\n"
    assert audit.read_labels(p) == {1: "real", 3: "ok"}


def test_read_labels_rejects_duplicates_and_extra_columns(tmp_path):
    p = tmp_path / "labels.csv"
    p.write_text("id,label\n1,real\n1,ok\n")
    with pytest.raises(ValueError, match="duplicate"):
        audit.read_labels(p)
    p.write_text("id,label\n1,real\n2,\n")
    with pytest.raises(ValueError, match="real"):
        audit.read_labels(p)
    p.write_text("id,label,jev_p\n1,real,0.9\n")
    with pytest.raises(ValueError, match="columns"):
        audit.read_labels(p)
