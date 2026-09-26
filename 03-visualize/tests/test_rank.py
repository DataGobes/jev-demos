from jevviz.rank import match_band, rank_key, rank_panels
from jevviz.types import Answer, Candidate


def cand(cid, kind, measures=("revenue",)):
    return Candidate(cid, kind, ("region", *measures), measures, f"T {cid}", f"D {cid}", {})


def score(p_hi, conf=0.5):
    return Answer("score", probabilities={0: (1 - p_hi) / 2, 1: (1 - p_hi) / 2, 2: p_hi / 2, 3: p_hi / 2}, confidence=conf)


TABLE = Candidate("c99", "table", ("region",), (), "Result table", "table", {})


def test_rank_key_is_mass_on_top_two_levels():
    assert abs(rank_key(score(0.8)) - 0.8) < 1e-9


def test_bands():
    assert (match_band(0.6), match_band(0.59), match_band(0.3), match_band(0.29)) == ("strong", "weak", "weak", "none")


def test_picks_best_and_diverse_alternates():
    cs = [cand("c00", "bar"), cand("c01", "bar"), cand("c02", "line"), cand("c03", "pie"), cand("c04", "heatmap"), TABLE]
    ans = {"i0.c00": score(0.9), "i0.c01": score(0.8), "i0.c02": score(0.7), "i0.c03": score(0.5), "i0.c04": score(0.4)}
    [panel] = rank_panels(cs, ["q"], ans)
    assert panel.chosen.candidate.id == "c00" and panel.match == "strong"
    assert [a.candidate.id for a in panel.alternates] == ["c02", "c03", "c04"]   # c01 skipped: second bar


def test_identifier_measures_are_dropped():
    cs = [cand("c00", "bar", ("customer_id",)), cand("c01", "bar"), TABLE]
    ans = {"i0.c00": score(0.95), "i0.c01": score(0.7), "id.customer_id": Answer("noul", noul=0.9),
           "id.revenue": Answer("noul", noul=0.05)}
    assert rank_panels(cs, ["q"], ans)[0].chosen.candidate.id == "c01"


def test_no_strong_match_falls_back_to_table():
    cs = [cand("c00", "bar"), TABLE]
    [panel] = rank_panels(cs, ["q"], {"i0.c00": score(0.1)})
    assert panel.chosen.candidate.kind == "table" and panel.match == "none"
    assert [a.candidate.id for a in panel.alternates] == ["c00"]


def test_dashboard_collision_takes_next_best():
    cs = [cand("c00", "bar"), cand("c01", "line"), TABLE]
    ans = {"i0.c00": score(0.9), "i0.c01": score(0.5), "i1.c00": score(0.8), "i1.c01": score(0.7)}
    panels = rank_panels(cs, ["a", "b"], ans)
    assert [p.chosen.candidate.id for p in panels] == ["c00", "c01"]


def test_missing_answers_fall_back_to_table():
    [panel] = rank_panels([cand("c00", "bar"), TABLE], ["q"], {})
    assert panel.chosen.candidate.kind == "table" and panel.match == "none"
