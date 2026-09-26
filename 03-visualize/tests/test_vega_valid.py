import json
from pathlib import Path

import jsonschema
from helpers import make_profile

from jevviz.rules import enumerate_candidates

SCHEMA = json.loads((Path(__file__).parent / "fixtures" / "vega-lite-v6.json").read_text())
PROFILES = [
    make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 9.0)),
    make_profile(row_count=15, region=("n", 5), channel=("n", 3), revenue=("q", 15, 0.0, 9.0)),
    make_profile(row_count=200, price=("q", 150, 1.0, 9.0), rating=("nq", 5, 1, 5), category=("n", 5)),
    make_profile(row_count=500, revenue=("q", 400, 0.0, 9.0)),
    # F1: an integer-year temporal column (ordinal x encoding) must still emit a valid spec.
    make_profile(signup_year=("ty", 11, 2015, 2025), customers=("q", 11, 1.0, 50.0)),
]


def test_every_chart_spec_is_valid_vega_lite():
    validator = jsonschema.Draft7Validator(SCHEMA)
    checked = 0
    for p in PROFILES:
        for c in enumerate_candidates(p)[0]:
            if c.kind in ("table", "kpi"):
                continue
            errors = list(validator.iter_errors(c.vega))
            assert not errors, f"{c.kind}: {errors[0].message}"
            # F5: web/package.json installs vega-lite ^6, so every emitted spec must
            # declare the matching v6 schema URL (a v5 declaration makes vega-embed
            # warn on every chart it compiles with the installed v6 compiler).
            assert c.vega["$schema"] == "https://vega.github.io/schema/vega-lite/v6.json", c.vega["$schema"]
            checked += 1
    assert checked >= 12


# `scatter` is the one rule that is row-level on purpose - its description says
# "one point per row", and aggregating it would destroy the correlation it exists
# to show. Every other rule answers a question about categories or periods.
ROW_LEVEL_BY_DESIGN = {"scatter"}


def test_every_measure_is_aggregated_or_binned():
    """Guards the defect that shipped in `pie`, `bar` and `grouped_bar`: a
    continuous measure left unaggregated makes Vega-Lite stack it and emit one
    mark *per row*, which merely groups by the discrete channel. Totals stay
    correct, so it is invisible until a 2000-row result renders each bar as
    thousands of hairline segments, or a stroke turns a 3-slice pie into a
    starburst. A measure must therefore be summarised - aggregated or binned -
    by any rule that is not row-level by design."""
    offenders = []
    for p in PROFILES:
        for c in enumerate_candidates(p)[0]:
            if c.kind in ("table", "kpi") or c.kind in ROW_LEVEL_BY_DESIGN:
                continue
            for channel, e in c.vega["encoding"].items():
                if isinstance(e, dict) and e.get("type") == "quantitative" and not (e.get("aggregate") or e.get("bin")):
                    offenders.append(f"{c.kind}.{channel} ({e.get('field')})")
    assert not offenders, f"unaggregated measures emit one mark per row: {sorted(set(offenders))}"
