import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "notebooks" / "jev_semantic_tests.py"


def _notebook() -> str:
    return NOTEBOOK.read_text()


def test_bundle_defines_serverless_notebook_job():
    b = yaml.safe_load((ROOT / "databricks.yml").read_text())
    job = b["resources"]["jobs"]["jev_semantic_tests"]
    task = job["tasks"][0]
    assert task["notebook_task"]["notebook_path"].endswith("notebooks/jev_semantic_tests.py")
    assert "new_cluster" not in task and "existing_cluster_id" not in task  # serverless
    assert "job_cluster_key" not in task and "job_clusters" not in job
    params = {p["name"]: p["default"] for p in job["parameters"]}
    assert params["mode"] == "demo" and params["selection"] == "yardstick"


def test_bundle_syncs_what_the_notebook_needs_and_no_host_or_warehouse_id():
    text = (ROOT / "databricks.yml").read_text()
    b = yaml.safe_load(text)
    sync = b["sync"]["include"]
    for needed in ("jaffle_shop/**", "notebooks/**", "src/**"):
        assert needed in sync
    assert not re.search(r"https://\S*databricks", text)
    assert not re.search(r"\b[0-9a-f]{16}\b", text)  # warehouse ids


def test_notebook_never_prints_the_token():
    src = _notebook()
    assert src.startswith("# Databricks notebook source")
    assert "apiToken()" in src
    assert "DBT_ENV_SECRET_DATABRICKS_TOKEN" in src
    assert "DBT_DATABRICKS_TOKEN" not in src.replace("DBT_ENV_SECRET_DATABRICKS_TOKEN", "")
    for leak in ("print(token", "display(token", "print(env", "display(env", "print(os.environ"):
        assert leak not in src
    assert "write_text" not in src and "open(" not in src  # the token never goes to a file


def test_notebook_runs_dbt_through_the_seed_patching_cli_with_src_on_the_path():
    src = _notebook()
    assert '"-m", "jevdbx.dbt_cli"' in src and "sys.executable" in src
    assert '"--profiles-dir", "."' in src and '"--target", "notebook"' in src
    assert "PYTHONPATH" in src and '"src"' in src
    assert '["dbt"' not in src  # never a bare dbt binary
    assert 'dbt-databricks==1.12.5' in src


def test_notebook_selections_match_the_scorer():
    src = _notebook()
    assert '"--exclude", "tag:production", "tag:production_baseline"' in src
    assert '"{production: true}"' in src
    assert '"+tag:production", "tag:production_baseline"' in src
    for widget in ('"mode"', '"selection"', '"warehouse"'):
        assert "dbutils.widgets" in src and widget in src
    assert "displayHTML" in src and "Jev ·" in src and "jev_p" in src
