from jevviz.rank import PanelChoice, Ranked
from jevviz.spec import assemble_spec, panel_payload
from jevviz.types import Candidate

LINE = Candidate("c01", "line", ("month", "revenue"), ("revenue",), "Revenue over Month", "d", {"mark": "line"})
KPI = Candidate("c00", "kpi", ("total",), ("total",), "Total", "d", {"field": "total"})
TABLE = Candidate("c09", "table", ("month", "revenue"), (), "Result table", "d", {"columns": ["month", "revenue"]})
ALLOWED = {"Grid", "Panel", "Chart", "Kpi", "Table"}


def test_flat_spec_uses_only_catalog_types_and_resolves_children():
    panels = [PanelChoice("trend", Ranked(LINE, 0.82), [Ranked(KPI, 0.4)], "strong"),
              PanelChoice("none", Ranked(TABLE, 0.0), [], "none")]
    spec = assemble_spec(panels)
    els = spec["elements"]
    assert spec["root"] == "grid" and els["grid"]["type"] == "Grid" and els["grid"]["props"]["columns"] == 2
    assert {e["type"] for e in els.values()} <= ALLOWED
    assert all(child in els for e in els.values() for child in e["children"])
    p0 = els[els["grid"]["children"][0]]
    assert p0["props"] == {"title": "Revenue over Month", "intent": "trend", "p": 0.82, "match": "strong", "panelIndex": 0}
    assert els[p0["children"][0]] == {"type": "Chart", "props": {"vega": {"mark": "line"}}, "children": []}


def test_single_panel_grid_is_one_column_and_payload_carries_full_alternate_elements():
    panels = [PanelChoice("trend", Ranked(LINE, 0.82), [Ranked(KPI, 0.4)], "strong")]
    assert assemble_spec(panels)["elements"]["grid"]["props"]["columns"] == 1
    [p] = panel_payload(panels)
    assert p["chosen"]["id"] == "c01" and p["match"] == "strong"
    alt = p["alternates"][0]
    assert alt["kind"] == "kpi" and alt["p"] == 0.4 and alt["element"]["type"] == "Kpi"
    assert alt["element"]["props"] == {"label": "Total", "field": "total"}
