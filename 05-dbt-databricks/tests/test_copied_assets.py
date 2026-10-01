"""The yardstick must be demo 04's, byte for byte: same seeds, same golden key, same pools."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DEMO4 = Path.home() / "Projects" / "jev-demo-4"

needs_demo4 = pytest.mark.skipif(not DEMO4.exists(), reason="demo 04 checkout not present")


def _make_seeds():
    spec = importlib.util.spec_from_file_location("make_seeds", ROOT / "scripts" / "make_seeds.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_regenerated_seeds_equal_committed(tmp_path):
    ms = _make_seeds()
    ms.write(ms.generate(42), tmp_path / "seeds", tmp_path / "golden.csv")
    for f in (ROOT / "jaffle_shop" / "seeds").glob("*.csv"):
        assert (tmp_path / "seeds" / f.name).read_bytes() == f.read_bytes(), f.name
    golden_expected = (ROOT / "eval" / "golden_defects.csv").read_bytes()
    assert (tmp_path / "golden.csv").read_bytes() == golden_expected


@needs_demo4
@pytest.mark.parametrize(
    "rel",
    ["eval/golden_defects.csv", "scripts/make_seeds.py"]
    + [f"jaffle_shop/seeds/{p.name}" for p in (DEMO4 / "jaffle_shop/seeds").glob("*.csv")]
    + [f"scripts/pools/{p.name}" for p in (DEMO4 / "scripts/pools").glob("*.toml")],
)
def test_identical_to_demo04(rel):
    assert (ROOT / rel).read_bytes() == (DEMO4 / rel).read_bytes()
