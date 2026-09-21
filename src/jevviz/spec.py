"""Assemble the flat json-render spec in code. Jev never writes JSON."""

from __future__ import annotations

from jevviz.rank import PanelChoice, Ranked


def _leaf(r: Ranked) -> dict:
    c = r.candidate
    if c.kind == "table":
        return {"type": "Table", "props": {"columns": c.vega["columns"], "maxRows": 200}, "children": []}
    if c.kind == "kpi":
        return {"type": "Kpi", "props": {"label": c.title, "field": c.vega["field"]}, "children": []}
    return {"type": "Chart", "props": {"vega": c.vega}, "children": []}


def _entry(r: Ranked) -> dict:
    c = r.candidate
    return {"id": c.id, "kind": c.kind, "title": c.title, "p": round(r.p, 4), "element": _leaf(r)}


def element_for(r: Ranked, intent: str, match: str) -> dict:
    """A `Panel` element wrapping one inline child descriptor (its chosen leaf)."""
    return {
        "type": "Panel",
        "props": {"title": r.candidate.title, "intent": intent, "p": round(r.p, 4), "match": match},
        "children": [_leaf(r)],
    }


def assemble_spec(panels: list[PanelChoice]) -> dict:
    elements: dict[str, dict] = {}
    children = []
    for i, p in enumerate(panels):
        elements[f"leaf-{i}"] = _leaf(p.chosen)
        elements[f"panel-{i}"] = {
            "type": "Panel",
            "props": {"title": p.chosen.candidate.title, "intent": p.intent, "p": round(p.chosen.p, 4),
                      "match": p.match, "panelIndex": i},
            "children": [f"leaf-{i}"],
        }
        children.append(f"panel-{i}")
    elements["grid"] = {"type": "Grid", "props": {"columns": 1 if len(panels) == 1 else 2}, "children": children}
    return {"root": "grid", "elements": elements}


def panel_payload(panels: list[PanelChoice]) -> list[dict]:
    return [{"intent": p.intent, "chosen": _entry(p.chosen), "alternates": [_entry(a) for a in p.alternates],
             "match": p.match} for p in panels]
