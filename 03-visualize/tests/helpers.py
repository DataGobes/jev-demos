from jevviz.types import Column, Profile

_KINDS = {
    "t": ("temporal",), "q": ("quantitative",), "n": ("nominal",), "nq": ("nominal", "quantitative"),
    # "ty": temporal kind carried by bare year integers (e.g. `signup_year`), as opposed
    # to "t" which the tests otherwise leave without a min/max. Pass an explicit int
    # range, e.g. signup_year=("ty", 11, 2015, 2025), so col.min/col.max are ints.
    "ty": ("temporal",),
}


def make_profile(row_count=100, **cols) -> Profile:
    """make_profile(month=("t", 24), region=("n", 5), revenue=("q", 90, 0.0, 500.0))"""
    out = []
    for pos, (name, spec) in enumerate(cols.items()):
        kind, distinct, *rng = spec
        lo, hi = (rng + [None, None])[:2]
        out.append(Column(name, _KINDS[kind], distinct, 0.0, lo, hi, (), False, pos))
    return Profile(tuple(out), row_count)
