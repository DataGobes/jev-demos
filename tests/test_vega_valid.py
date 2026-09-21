import json
from pathlib import Path

import jsonschema
from helpers import make_profile

from jevviz.rules import enumerate_candidates

SCHEMA = json.loads((Path(__file__).parent / "fixtures" / "vega-lite-v5.json").read_text())
PROFILES = [
    make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 9.0)),
    make_profile(row_count=15, region=("n", 5), channel=("n", 3), revenue=("q", 15, 0.0, 9.0)),
    make_profile(row_count=200, price=("q", 150, 1.0, 9.0), rating=("nq", 5, 1, 5), category=("n", 5)),
    make_profile(row_count=500, revenue=("q", 400, 0.0, 9.0)),
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
            checked += 1
    assert checked >= 12
