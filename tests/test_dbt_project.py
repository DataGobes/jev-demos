import json
import os
import shutil
import subprocess
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).parents[1]
SEMANTIC = ["customers_full_name_is_a_person", "returns_comment_matches_reason_code",
            "reviews_body_matches_stars", "tickets_body_has_no_pii"]
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    dst = tmp_path_factory.mktemp("dbt") / "jaffle_shop"
    ignore = shutil.ignore_patterns("target", "logs", "*.duckdb*", ".jev_cache.sqlite")
    shutil.copytree(ROOT / "jaffle_shop", dst, ignore=ignore)
    return dst


def dbt(project, *args, **env):
    full_env = {**os.environ, "JEV_MODE": "demo", "JEV_NO_CACHE": "1", "DOTENV_DISABLE": "1", **env}
    full_env.pop("TYPESAFE_API_KEY", None)
    return subprocess.run(
        ["uv", "run", "--project", str(ROOT), "dbt", *args, "--profiles-dir", "."],
        cwd=project, env=full_env, capture_output=True, text=True, timeout=600,
    )


def test_standard_tests_green(project):
    r = dbt(project, "build", "--exclude", "tag:semantic", "tag:baseline")
    assert r.returncode == 0, r.stdout[-3000:]
    assert "ERROR=0" in r.stdout
    assert "MissingArgumentsPropertyInGenericTestDeprecation" not in r.stdout


def test_semantic_tests_store_failures_and_summary(project):
    r = dbt(project, "test", "--select", "tag:semantic")
    assert "Jev · 1,300 judgments" in r.stdout, r.stdout[-3000:]
    assert "SIMULATED" in r.stdout
    con = duckdb.connect(str(project / "jaffle_shop.duckdb"), read_only=True)
    for name in SEMANTIC:
        query = f"select * from main_dbt_test__audit.{name} limit 0"
        cols = [c[0] for c in con.execute(query).description]
        assert "jev_p" in cols, name
    row = con.execute("select stats from main_dbt_test__audit.jev_last_run").fetchone()
    stats = json.loads(row[0])
    assert stats["judgments"] == 1300
    assert "SIMULATED" in stats["summary"]


def test_baseline_tables_exist(project):
    r = dbt(project, "test", "--select", "tag:baseline")
    assert r.returncode == 0, r.stdout[-3000:]  # severity warn
    con = duckdb.connect(str(project / "jaffle_shop.duckdb"), read_only=True)
    for name in SEMANTIC:
        con.execute(f"select count(*) from main_dbt_test__audit.baseline_{name}").fetchone()


def test_bad_threshold_is_a_compile_error(project, tmp_path):
    schema = project / "models" / "staging" / "schema.yml"
    original = schema.read_text()
    schema.write_text(original.replace("threshold: 0.8", "threshold: 1.5", 1))
    try:
        r = dbt(project, "compile", "--select", "tag:semantic")
        assert r.returncode != 0 and "threshold" in (r.stdout + r.stderr)
    finally:
        schema.write_text(original)
