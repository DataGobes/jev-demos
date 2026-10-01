import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("audit_sample", ROOT / "scripts/audit_sample.py")
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)


def test_pick_audit_excludes_planted_is_sorted_and_deterministic():
    flagged = set(range(1, 501))
    planted = set(range(1, 101))
    a = au.pick_audit(flagged, planted, 100, 42)
    assert a == au.pick_audit(flagged, planted, 100, 42)
    assert len(a) == 100 and a == sorted(a)
    assert not set(a) & planted and set(a) <= flagged


def test_pick_audit_returns_everything_when_short():
    assert au.pick_audit({5, 3, 9}, {9}, 100, 42) == [3, 5]
    assert au.pick_audit(set(), set(), 10, 42) == []


def test_pick_audit_does_not_depend_on_set_iteration_order():
    flagged = set(range(1000, 0, -1))
    assert au.pick_audit(flagged, set(), 50, 7) == au.pick_audit(set(sorted(flagged)), set(), 50, 7)


def test_flagged_query_skips_unjudged_rows_and_never_selects_the_score():
    sql = au.flagged_query("cat.sch.tbl").lower()
    select_list, _, rest = sql.partition(" from ")
    assert "jev_p" not in select_list and "jev_p is not null" in rest
    assert rest.startswith("cat.sch.tbl") and "review_id" in select_list


def test_flagged_query_reads_live_rows_only_and_never_exports_provenance():
    sql = au.flagged_query("cat.sch.tbl").lower()
    select_list, _, rest = sql.partition(" from ")
    assert "jev_mode = 'live'" in rest
    for col in ("jev_p", "jev_mode", "jev_invocation_id"):
        assert col not in select_list


def test_provenance_query_counts_rows_that_are_not_live():
    q = au.provenance_query("cat.sch.tbl").lower()
    assert "from cat.sch.tbl" in q and "jev_mode is distinct from 'live'" in q
    assert "count(distinct jev_invocation_id)" in q


def test_refuses_a_table_with_simulated_or_mixed_rows():
    assert au.provenance_problem(0, 1) is None
    assert "SIMULATED" in au.provenance_problem(3, 1)
    assert "invocations" in au.provenance_problem(0, 2)


# -- key audit: random planted flips among the loaded rows --------------------------------------


def test_pick_flip_audit_is_sorted_seeded_and_a_subset():
    loaded = set(range(1, 1304))
    a = au.pick_flip_audit(loaded, 100, 42)
    assert a == au.pick_flip_audit(loaded, 100, 42)
    assert len(a) == 100 and a == sorted(a) and set(a) <= loaded
    assert a != au.pick_flip_audit(loaded, 100, 43)


def test_pick_flip_audit_returns_everything_when_short_and_ignores_set_order():
    assert au.pick_flip_audit({5, 3, 9}, 100, 42) == [3, 5, 9]
    assert au.pick_flip_audit(set(), 10, 42) == []
    big = set(range(1000, 0, -1))
    assert au.pick_flip_audit(big, 50, 7) == au.pick_flip_audit(set(sorted(big)), 50, 7)


def test_flip_rows_query_reads_only_the_listed_ids_of_the_production_model():
    q = au.flip_rows_query({3, 1, 2}).lower()
    select_list, _, rest = q.partition(" from ")
    assert select_list.split() == ["select", "review_id,", "stars,", "body"]
    assert rest.startswith("jev_demo.jaffle_shop.stg_product_reviews")
    assert "review_id in (1, 2, 3)" in rest


def test_flip_rows_query_never_selects_the_score_or_the_original_stars():
    select_list = au.flip_rows_query({1}).lower().partition(" from ")[0]
    for col in ("jev_p", "jev_mode", "original_stars", "planted_stars"):
        assert col not in select_list


# -- labeller copies: id, stars, body only, shuffled differently ---------------------------------

ROWS = [(i, 1 + i % 5, f"text {i}") for i in range(1, 41)]


def test_shuffled_copy_is_a_seeded_permutation_of_the_rows():
    a = au.shuffled_copy(ROWS, 43)
    assert a == au.shuffled_copy(ROWS, 43)
    assert sorted(a) == sorted(ROWS) and a != ROWS
    assert a != au.shuffled_copy(ROWS, 44)
    assert ROWS == sorted(ROWS)  # the input is not reordered in place


def test_write_labeller_copies_writes_only_id_stars_body(tmp_path):
    paths = au.write_labeller_copies(tmp_path, "production_audit", ROWS)
    assert [p.name for p in paths] == ["production_audit.labeller_a.csv",
                                       "production_audit.labeller_b.csv"]
    import csv

    orders = []
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            rd = csv.reader(f)
            assert next(rd) == ["id", "stars", "body"]
            body = [(int(i), int(s), t) for i, s, t in rd]
        assert sorted(body) == ROWS
        orders.append([r[0] for r in body])
    assert orders[0] != orders[1] and orders[0] != sorted(orders[0])


def test_labeller_copies_use_seeds_43_and_44():
    assert au.LABELLER_SEEDS == (43, 44)


def test_write_audit_file_has_an_empty_label_column_and_sorted_ids(tmp_path):
    import csv

    p = tmp_path / "x.csv"
    au.write_audit_file(p, list(reversed(ROWS)))
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["id", "stars", "body", "label"]
    assert [int(r[0]) for r in rows[1:]] == sorted(r[0] for r in ROWS)
    assert all(r[3] == "" for r in rows[1:])


def test_multiline_bodies_survive_a_copy_roundtrip(tmp_path):
    import csv

    rows = [(1, 2, 'line one\nline "two", with comma')]
    (p,) = au.write_labeller_copies(tmp_path, "n", rows)[:1]
    with open(p, newline="", encoding="utf-8") as f:
        assert list(csv.reader(f))[1] == ["1", "2", rows[0][2]]


# -- main: both audits, from a fake warehouse ------------------------------------------------------


class FakeSql:
    def __init__(self):
        self.seen = []

    def run(self, statement, timeout_s=900):
        from jevdbx.databricks import Result

        self.seen.append(statement)
        low = statement.lower()
        if "count_if" in low:
            return Result("SUCCEEDED", rows=[["0", "1"]])
        if "jev_p is not null" in low:  # flagged-but-judged rows: 1..30 are flagged
            return Result("SUCCEEDED", rows=[[str(i), "3", f"flagged {i}"] for i in range(1, 31)])
        return Result("SUCCEEDED", rows=[[str(i), "1", f"loaded {i}"] for i in range(1, 21)])


def test_main_writes_both_audit_files_and_the_labeller_copies(tmp_path, monkeypatch):
    import csv

    import jevdbx.databricks as dbx

    fake = FakeSql()
    monkeypatch.setattr(dbx, "Sql", lambda *a, **k: fake)
    monkeypatch.setattr(au, "ROOT", tmp_path)
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval/production_flips.csv").write_text(
        "id,original_stars,planted_stars\n" + "".join(f"{i},5,1\n" for i in range(1, 11)))
    assert au.main(["--n", "5", "--flips", "4", "--labeller-copies", str(tmp_path / "copies")]) == 0

    def read(p):
        with open(p, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    prec = read(tmp_path / "data/production_audit.csv")
    flip = read(tmp_path / "data/production_flip_audit.csv")
    assert prec[0] == flip[0] == ["id", "stars", "body", "label"]
    assert len(prec) == 6 and len(flip) == 5
    assert all(int(r[0]) > 10 for r in prec[1:])  # flagged-but-unplanted only
    assert all(int(r[0]) <= 10 for r in flip[1:])  # planted flips only
    for name, n in (("production_audit", 5), ("production_flip_audit", 4)):
        for tag in "ab":
            copy = read(tmp_path / f"copies/{name}.labeller_{tag}.csv")
            assert copy[0] == ["id", "stars", "body"] and len(copy) == n + 1
    assert not any("jev_p," in q.lower() for q in fake.seen)
