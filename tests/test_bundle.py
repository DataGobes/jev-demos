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
    assert '"{production: true, jev_max_concurrency: 2}"' in src  # same as score.PROD_VARS
    assert '"+tag:production", "tag:production_baseline"' in src
    for widget in ('"mode"', '"selection"', '"warehouse"'):
        assert "dbutils.widgets" in src and widget in src
    assert "displayHTML" in src and "Jev ·" in src and "jev_p" in src


def test_notebook_gets_the_token_lazily_inside_dbt_env_sdk_auth_first():
    src = _notebook()
    body = src.split("def dbt_env()", 1)[1].split("# COMMAND ----------", 1)[0]
    assert "config.authenticate()" in body
    assert "Bearer" in body
    assert "apiToken().get()" in body  # fallback, same function
    assert body.index("config.authenticate()") < body.index("apiToken().get()")
    assert not re.search(r"^ctx\s*=", src, re.M)  # no eager cell-level context
    assert "apiToken" not in src.split("def dbt_env()", 1)[0]
    assert "dapi" not in src and "personal access" not in src.lower()


def test_notebook_keeps_dbt_working_files_out_of_the_synced_folder():
    src = _notebook()
    assert 'tempfile.mkdtemp(prefix="jev-dbt-")' in src
    assert '"DBT_TARGET_PATH"' in src and '"DBT_LOG_PATH"' in src


def test_notebook_fails_clearly_and_captions_the_mode():
    src = _notebook()
    assert "project.is_dir()" in src and "dbt project not found at" in src
    assert "next((x for x in w.warehouses.list()" in src and ", None)" in src
    assert "SIMULATED (demo)" in src and "probabilities are not Jev judgments" in src
    assert "Mode: LIVE" in src


def test_notebook_production_vars_equal_the_scorers():
    import importlib.util

    spec = importlib.util.spec_from_file_location("score_nb", ROOT / "scripts" / "score.py")
    score = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(score)
    assert f'"{score.PROD_VARS}"' in _notebook()
