import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("audit_merge", ROOT / "scripts/audit_merge.py")
am = importlib.util.module_from_spec(spec)
spec.loader.exec_module(am)


def labels_file(path, pairs):
    path.write_text("id,label\n" + "".join(f"{i},{v}\n" for i, v in pairs))
    return path


def sample_file(path, ids):
    path.write_text("id,stars,body,label\n" + "".join(f"{i},1,x,\n" for i in ids))
    return path


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "eval").mkdir()
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(am, "ROOT", tmp_path)
    return tmp_path


def test_pre_registered_tie_rules():
    assert am.TIES == {"precision": "ok", "flip": "real"}


def test_precision_audit_disagreements_become_ok(repo):
    a = labels_file(repo / "a.csv", [(1, "real"), (2, "real"), (3, "ok"), (4, "real")])
    b = labels_file(repo / "b.csv", [(1, "real"), (2, "ok"), (3, "ok"), (4, "ok")])
    assert am.main(["--precision", str(a), str(b)]) == 0
    assert (repo / "eval/production_audit_labels.csv").read_text() == (
        "id,label\n1,real\n2,ok\n3,ok\n4,ok\n")
    agreement = json.loads((repo / "eval/production_audit_agreement.json").read_text())
    assert agreement["precision_audit"] == {
        "n": 4, "agreement": 0.5, "kappa": pytest.approx(0.2), "tie": "ok",
        "disagreements": [2, 4]}
    assert "key_audit" not in agreement
    assert not (repo / "eval/production_flip_audit_labels.csv").exists()


def test_key_audit_disagreements_become_real(repo):
    a = labels_file(repo / "a.csv", [(1, "ok"), (2, "ok"), (3, "real")])
    b = labels_file(repo / "b.csv", [(1, "ok"), (2, "real"), (3, "real")])
    assert am.main(["--flip", str(a), str(b)]) == 0
    assert (repo / "eval/production_flip_audit_labels.csv").read_text() == (
        "id,label\n1,ok\n2,real\n3,real\n")
    entry = json.loads((repo / "eval/production_audit_agreement.json").read_text())["key_audit"]
    assert entry["tie"] == "real" and entry["disagreements"] == [2]
    assert entry["agreement"] == pytest.approx(2 / 3, abs=1e-3)


def test_both_audits_in_one_run_and_the_second_run_keeps_the_first(repo):
    a = labels_file(repo / "a.csv", [(1, "ok")])
    am.main(["--precision", str(a), str(a)])
    am.main(["--flip", str(a), str(a)])
    agreement = json.loads((repo / "eval/production_audit_agreement.json").read_text())
    assert set(agreement) == {"precision_audit", "key_audit"}


def test_mismatched_ids_or_bad_labels_write_nothing(repo):
    a = labels_file(repo / "a.csv", [(1, "ok"), (2, "ok")])
    b = labels_file(repo / "b.csv", [(1, "ok")])
    with pytest.raises(ValueError, match="ids"):
        am.main(["--precision", str(a), str(b)])
    c = labels_file(repo / "c.csv", [(1, "ok"), (2, "maybe")])
    with pytest.raises(ValueError, match="real"):
        am.main(["--precision", str(a), str(c)])
    assert list((repo / "eval").iterdir()) == []


def test_ids_must_match_the_audit_sample_when_it_exists(repo):
    a = labels_file(repo / "a.csv", [(1, "ok"), (2, "ok")])
    sample_file(repo / "data/production_flip_audit.csv", [1, 2, 3])
    with pytest.raises(ValueError, match="audit file"):
        am.main(["--flip", str(a), str(a)])
    assert list((repo / "eval").iterdir()) == []
    sample_file(repo / "data/production_flip_audit.csv", [2, 1])
    assert am.main(["--flip", str(a), str(a)]) == 0


def test_an_atomic_failure_in_the_second_audit_writes_nothing_for_the_first(repo):
    good = labels_file(repo / "g.csv", [(1, "ok")])
    bad_b = labels_file(repo / "bb.csv", [(2, "ok")])
    with pytest.raises(ValueError):
        am.main(["--precision", str(good), str(good), "--flip", str(good), str(bad_b)])
    assert list((repo / "eval").iterdir()) == []


def test_needs_at_least_one_audit(repo, capsys):
    with pytest.raises(SystemExit) as e:
        am.main([])
    assert e.value.code == 2


def test_the_committed_files_have_no_review_text(repo):
    a = labels_file(repo / "a.csv", [(1, "ok")])
    am.main(["--precision", str(a), str(a)])
    assert (repo / "eval/production_audit_labels.csv").read_text().splitlines()[0] == "id,label"


def test_a_single_label_audit_records_kappa_as_null(repo, capsys):
    a = labels_file(repo / "a.csv", [(1, "ok"), (2, "ok")])
    assert am.main(["--precision", str(a), str(a)]) == 0
    entry = json.loads((repo / "eval/production_audit_agreement.json").read_text())
    assert entry["precision_audit"]["kappa"] is None
    assert "kappa n/a (one label only)" in capsys.readouterr().out
