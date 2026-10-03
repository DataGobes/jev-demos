import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("dbtw", ROOT / "scripts" / "dbtw.py")
dbtw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbtw)


def test_adds_profiles_dir_and_target():
    assert dbtw.build_command(["build"]) == ["build", "--profiles-dir", ".", "--target", "dev"]


def test_keeps_explicit_target():
    assert dbtw.build_command(["build", "--target", "render"]) == [
        "build", "--target", "render", "--profiles-dir", "."]


def test_project_dir_is_bench():
    assert dbtw.PROJECT_DIR == ROOT / "bench"
