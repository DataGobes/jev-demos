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
    assert params["action"] == "build"  # `results` only shows a logged live run


def test_bundle_syncs_what_the_notebook_needs_and_no_host_or_warehouse_id():
    text = (ROOT / "databricks.yml").read_text()
    b = yaml.safe_load(text)
    sync = b["sync"]["include"]
    for needed in ("jaffle_shop/**", "notebooks/**", "src/**"):
        assert needed in sync
    assert "docs/eval-results.md" in sync  # results mode prints the logged entry
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


# ---- action=results: show the logged live run, run no dbt, call no Jev ------------------------


def _cells() -> list[str]:
    return _notebook().split("# COMMAND ----------")


def _results_cell() -> tuple[int, str]:
    hits = [(i, c) for i, c in enumerate(_cells()) if 'action == "results"' in c]
    assert len(hits) == 1, "exactly one cell handles action == results"
    return hits[0]


def test_notebook_has_an_action_widget_defaulting_to_build():
    src = _notebook()
    assert 'dbutils.widgets.dropdown("action", "build", ["build", "results"])' in src


def test_results_mode_runs_before_and_instead_of_dbt_and_never_calls_jev():
    cells = _cells()
    i, cell = _results_cell()
    assert "dbutils.notebook.exit(" in cells[i + 1]  # nothing below runs in results mode
    ahead = "\n".join(cells[: i + 2])
    for banned in ("subprocess", "dbt_cli", "%pip", "dbt_env", "noul_pack(", "noul_pack_demo(",
                   "apiToken", "authenticate()"):
        assert banned not in ahead, banned
    # every dbt-running cell comes after the exit
    later = "\n".join(cells[i + 2:])
    assert "subprocess.run" in later and "%pip install" in later
    assert "noul_pack(" not in _notebook()  # the notebook itself never calls the Jev function


def test_results_exit_is_its_own_cell_so_it_does_not_replace_the_displayed_output():
    """On Databricks a dbutils.notebook.exit in the same cell replaces that cell's displayed output
    with the exit value; the captions, table, entries and failing rows must stay visible."""
    cells = _cells()
    i, cell = _results_cell()
    # the final exit is not in the cell that displays the results
    assert "results_exit_message" in cell
    assert "dbutils.notebook.exit(f" not in cell
    assert "dbutils.notebook.exit(results_exit_message" not in cell
    assert cell.index("results_exit_message =") > cell.rindex("display(")
    # the next cell is only the results-mode guard + exit (comments aside)
    lines = [ln.strip() for ln in cells[i + 1].splitlines()]
    code = [ln for ln in lines if ln and not ln.startswith("#")]
    assert code == [
        'if dbutils.widgets.get("action") == "results":',
        "dbutils.notebook.exit(results_exit_message)",
    ]
    # build mode: the exit message is only ever set inside the results branch
    assert not re.search(r"^results_exit_message", cell, re.M)
    assert "%pip install" not in cells[i + 1]


def test_results_mode_queries_with_the_ledger_helpers():
    _, cell = _results_cell()
    for fn in ("latest_live_invocation_sql(", "judging_invocations_sql(", "judging_from_rows(",
               "judging_lines(", "judging_caption(", "entries_for_runs(", "stored_failures_sql("):
        assert fn in cell
    assert "sys.path.insert(0," in cell and "from jevdbx import evallog" in cell


def test_results_mode_runs_every_query_on_the_sql_warehouse_not_on_spark():
    """One engine: evallog's SQL was written and verified on the SQL warehouse; on serverless
    notebook compute (spark.sql) latest_live_invocation_sql fails with UNRESOLVED_COLUMN."""
    _, cell = _results_cell()
    assert "spark.sql(" not in cell and "spark." not in cell
    assert "spark.sql(evallog." not in cell
    assert "from jevdbx.databricks import" in cell and "Sql" in cell
    assert "from databricks.sdk import WorkspaceClient" in cell
    # the notebook's own client and the warehouse resolved from the `warehouse` widget
    assert "WorkspaceClient()" in cell
    assert 'dbutils.widgets.get("warehouse")' in cell
    assert "resolve_warehouse_id(" in cell
    assert re.search(r"Sql\(\s*client=\w+,\s*warehouse_id=\w+\s*\)", cell)
    # every ledger query goes through the warehouse client
    for fn in ("latest_live_invocation_sql(", "judging_invocations_sql(", "stored_failures_sql("):
        assert re.search(rf"run_sql\(\s*evallog\.{re.escape(fn)}", cell), fn
    assert "sql.run(statement)" in cell  # run_sql is the one door to the warehouse client
    assert "order by jev_p desc" in cell and "display(pd.DataFrame(" in cell
    # still no token: neither printed nor read in results mode
    for leak in ("print(", "token", "Authorization", "authenticate"):
        assert leak not in cell, leak


def test_results_mode_shows_every_run_that_judged_the_rows_not_only_the_latest():
    _, cell = _results_cell()
    cell = re.sub(r'"\s*\n\s*f?"', "", cell)  # adjacent string literals read as one
    assert "evallog.judging_caption(judges)" in cell
    assert "evallog.COST_NOTE" in cell
    assert "evallog.NOT_APPENDED" in cell  # a judging run missing from the log is said so
    assert "html.escape" in cell  # each logged entry is shown verbatim
    assert "LIVE" in cell and "no live run" in cell.lower()
    # the failing rows are checked against the latest invocation, not the judging runs
    assert cell.index("judging_invocations_sql(") < cell.index("stored_failures_sql(")
    assert "latest live run" in cell and "docs/eval-results.md" in cell


def test_results_mode_checks_stored_failures_before_showing_them():
    _, cell = _results_cell()
    check = cell.index("stored_failures_sql(")
    status = cell.index("failure_rows_status(")
    shown = cell.index("order by jev_p desc")
    assert check < status < shown
    assert 'status == "show"' in cell
    assert "stored failures come from a different run" in cell
    assert "rebuild or pick that run" in cell


def test_build_mode_keeps_its_simulated_and_live_captions_and_scored_test_names():
    src = _notebook()
    assert "SIMULATED (demo)" in src and "Mode: LIVE" in src
    last = _cells()[-1]
    assert "scored_tests(selection)" in last and "jev_p" in last


def test_notebook_names_the_scored_tests_in_one_place_only():
    assert "customers_full_name_is_a_person" not in _notebook()  # jevdbx.evallog owns the list


def test_readme_and_claude_md_document_results_mode():
    readme = (ROOT / "README.md").read_text()
    assert "action=results" in readme and "no Jev call" in readme
    claude = " ".join((ROOT / "CLAUDE.md").read_text().split())
    assert "action=results" in claude
    assert "latest logged live run" not in claude
    assert "every live run that judged the shown rows" in claude
    assert "failing rows from the latest" in claude


def test_results_mode_is_described_as_every_judging_run_not_the_latest_one():
    head = _notebook().split("# COMMAND ----------")[0]
    assert "every **live** run that judged the rows" in head and "latest logged" not in head
    readme = " ".join((ROOT / "README.md").read_text().split())
    assert "every live run that judged the rows on record" in readme
    assert "N counts distinct states, not rows" in readme
    assert "shows the latest **live** run" not in readme
