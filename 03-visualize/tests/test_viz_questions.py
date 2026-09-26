from helpers import make_profile

from jevviz.parse import BARE_INTENT
from jevviz.rules import enumerate_candidates
from jevviz.viz_questions import LEVELS, build_questions, effective_intents, state_for

P = make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 9.0), customer_id=("q", 80, 1, 5000))


def test_one_score_per_intent_candidate_pair_excluding_table():
    cands, _ = enumerate_candidates(P)
    qs = build_questions(P, cands, ["trend by region", "top regions"])
    scored = [c for c in cands if c.kind != "table"]
    assert sum(k.startswith("i0.") for k in qs) == len(scored)
    assert sum(k.startswith("i1.") for k in qs) == len(scored)
    q = qs[f"i0.{scored[0].id}"]
    assert q.kind == "score" and q.levels == LEVELS
    assert '"trend by region"' in q.instructions and scored[0].description in q.instructions


def test_noul_only_for_numeric_looking_columns_used_as_measures():
    cands, _ = enumerate_candidates(P)
    qs = build_questions(P, cands, ["x"])
    assert "id.customer_id" in qs and "id.revenue" in qs
    assert "id.region" not in qs and "id.month" not in qs
    assert "`customer_id`" in qs["id.customer_id"].instructions


def test_state_is_compact_and_has_no_rows():
    s = state_for("SELECT 1", P)
    assert s["sql"] == "SELECT 1" and s["row_count"] == 100
    assert s["columns"]["region"] == {"kind": "nominal", "distinct": 5, "samples": []}
    assert "rows" not in s


def test_bare_clause_uses_pseudo_intent():
    assert effective_intents([]) == [BARE_INTENT] and effective_intents(["a"]) == ["a"]
