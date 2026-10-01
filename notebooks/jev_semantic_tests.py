# Databricks notebook source
# MAGIC %md
# MAGIC # Jev semantic dbt tests, run inside Databricks
# MAGIC `dbt build` on a serverless notebook; queries run on the SQL warehouse; Jev is the UC
# MAGIC function `jev_demo.jev.noul_pack`, whose key never leaves Unity Catalog.
# MAGIC
# MAGIC `action=build` (default) installs dbt and builds. `action=results` runs no dbt and makes no
# MAGIC Jev call: it shows every **live** run that judged the rows on record (a rerun judges
# MAGIC nothing), with the stored failing rows of the latest one (`mode` is ignored).

# COMMAND ----------

dbutils.widgets.dropdown("action", "build", ["build", "results"])
dbutils.widgets.dropdown("mode", "demo", ["demo", "live"])
dbutils.widgets.dropdown("selection", "yardstick", ["yardstick", "production"])
dbutils.widgets.text("warehouse", "jev-demo-5")

# COMMAND ----------

# action=results: show the logged live run and stop here. Nothing below runs (no pip install, no
# dbt, no Jev call): only the ledger queries and the synced eval log. The queries run on the SQL
# warehouse, like the rest of the project's SQL (dbt, score.py): evallog's SQL does not resolve on
# serverless notebook compute (Spark), so one engine runs it all. The SDK's notebook auth
# supplies the client; no credential is read or shown here.
action = dbutils.widgets.get("action")
if action == "results":
    import html
    import os
    import sys
    from pathlib import Path

    results_root = Path(os.getcwd()).parent
    sys.path.insert(0, str(results_root / "src"))
    import pandas as pd
    from databricks.sdk import WorkspaceClient

    from jevdbx import evallog
    from jevdbx.databricks import Sql, resolve_warehouse_id

    client = WorkspaceClient()
    warehouse_id = resolve_warehouse_id(client, dbutils.widgets.get("warehouse"))
    sql = Sql(client=client, warehouse_id=warehouse_id)

    def run_sql(statement: str):
        res = sql.run(statement)
        if res.state != "SUCCEEDED":
            raise RuntimeError(f"warehouse query failed ({res.state}): {res.error}")
        return res

    selection = dbutils.widgets.get("selection")
    tests = evallog.scored_tests(selection)
    latest = run_sql(evallog.latest_live_invocation_sql(tests)).rows
    if not latest:
        message = (f"No live run found for the {selection} selection: no invocation in "
                   "jev_demo.jev.hook_runs covers all of its scored tests in live mode.")
        displayHTML(f"<p><b>{html.escape(message)}</b></p>")
        dbutils.notebook.exit(message)
    invocation, recorded_micros = latest[0]  # columns: invocation_id, recorded_micros
    judged_at = evallog.utc_stamp(recorded_micros)

    # The rows on screen were judged by every live run that made a successful judgment on record,
    # not only the latest invocation (a rerun judges nothing and costs $0).
    judges = evallog.judging_from_rows(
        tuple(r) for r in run_sql(evallog.judging_invocations_sql(tests)).rows)
    if not judges:
        message = (f"No successful live judgments on record for the {selection} selection, "
                   "so there are no results to show.")
        displayHTML(f"<p><b>{html.escape(message)}</b></p>")
        dbutils.notebook.exit(message)
    displayHTML(f"<p><b>{html.escape(evallog.judging_caption(judges))}</b></p>")
    displayHTML("<pre>" + html.escape("\n".join([*evallog.judging_lines(judges),
                                                  "", evallog.COST_NOTE])) + "</pre>")

    log = results_root / "docs" / "eval-results.md"
    log_text = log.read_text(encoding="utf-8") if log.is_file() else ""
    displayHTML("<p><b>Logged entries (docs/eval-results.md, verbatim)</b></p>")
    for run_id, entry in evallog.entries_for_runs(log_text, judges):
        if entry is None:
            displayHTML(f"<p>invocation {run_id}: {evallog.NOT_APPENDED}.</p>")
        else:
            displayHTML(f'<pre style="white-space: pre-wrap">{html.escape(entry)}</pre>')

    displayHTML(f"<p><b>Failing rows, with Jev's probability (LIVE)</b>: stored by the latest live "
                f"run, invocation {invocation}, judged at {judged_at}.</p>")
    for t in tests:
        try:
            total, matching = run_sql(evallog.stored_failures_sql(t, invocation)).rows[0]
            status = evallog.failure_rows_status(int(total), int(matching))
            detail = f"{matching} of {total} stored rows are this run's"
        except Exception as e:  # noqa: BLE001 -- older stored failures have no provenance columns
            status = "unreadable"
            detail = f"the stored failures could not be read ({type(e).__name__})"
        if status == "show":
            displayHTML(f"<p>{t}</p>")
            shown = run_sql(f"select * from {evallog.AUDIT}.{t} "
                            "order by jev_p desc nulls last limit 20")
            display(pd.DataFrame(shown.rows, columns=shown.columns))
        elif status == "empty":
            displayHTML(f"<p>{t}: no failing rows stored.</p>")
        else:
            displayHTML(f"<p><b>Warning, {t}:</b> stored failures come from a different run "
                        f"({detail}); rebuild or pick that run.</p>")
    # Exited in the next cell: an exit in this cell would replace everything displayed above.
    results_exit_message = f"results of live invocation {invocation}"

# COMMAND ----------

# The exit is its own cell: dbutils.notebook.exit in the cell that displays the results replaces
# that cell's output with the exit value. In build mode this cell does nothing.
if dbutils.widgets.get("action") == "results":
    dbutils.notebook.exit(results_exit_message)

# The install cell below comes after the results branch on purpose: results mode installs nothing.
# The Python restart that follows an install clears state; widgets persist and every cell below
# sets itself up.

# COMMAND ----------

# MAGIC %pip install -q "dbt-core==1.12.3" "dbt-databricks==1.12.5"

# COMMAND ----------

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from databricks.sdk import WorkspaceClient

mode = dbutils.widgets.get("mode")
selection = dbutils.widgets.get("selection")
w = WorkspaceClient()
wanted = dbutils.widgets.get("warehouse")
warehouse = next((x for x in w.warehouses.list() if wanted in (x.name, x.id)), None)
if warehouse is None:
    raise LookupError(f"no SQL warehouse named or with id {wanted!r} (widget 'warehouse')")

bundle_root = Path(os.getcwd()).parent  # the bundle syncs notebooks/, jaffle_shop/ and src/
project = bundle_root / "jaffle_shop"
assert project.is_dir(), (
    f"dbt project not found at {project} "
    "(expected the bundle root to be the notebook folder's parent)")
# dbt's target/ and logs/ go to a scratch directory, never into the synced workspace files.
scratch = tempfile.mkdtemp(prefix="jev-dbt-")
sys.path.insert(0, str(bundle_root / "src"))  # jevdbx.evallog, for the scored test names
pythonpath = os.pathsep.join(
    p for p in (str(bundle_root / "src"), os.environ.get("PYTHONPATH", "")) if p)

if selection == "production":
    # 2 packs in flight per statement: 250k tokens/s at TypeSafe, retries never exercised live.
    args = ["build", "--vars", "{production: true, jev_max_concurrency: 2}",
            "--select", "+tag:production", "tag:production_baseline"]
else:
    # A fresh schema needs stg_orders (relationships tests), so build the whole yardstick.
    args = ["build", "--exclude", "tag:production", "tag:production_baseline"]


def dbt_env() -> dict:
    """The subprocess environment. The run token is acquired here, lazily, and lives only in the
    returned dict (profiles.yml reads it from DBT_ENV_SECRET_DATABRICKS_TOKEN, which dbt scrubs
    from its logs). It is the notebook's own short-lived credential: the SDK's notebook-native
    auth first, then the notebook context's API token. Never a PAT; never displayed, and error
    messages carry no header values."""
    token = None
    try:
        scheme, _, bearer = (w.config.authenticate().get("Authorization") or "").partition(" ")
        if scheme == "Bearer" and bearer:
            token = bearer
    except Exception:  # noqa: BLE001 -- fall back to the context token
        pass
    if token is None:
        token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    return {
        **os.environ,
        "DBT_TARGET_PATH": os.path.join(scratch, "target"),
        "DBT_LOG_PATH": os.path.join(scratch, "logs"),
        "PYTHONPATH": pythonpath,
        "DATABRICKS_HOST": w.config.host.removeprefix("https://").rstrip("/"),
        "JEV_HTTP_PATH": f"/sql/1.0/warehouses/{warehouse.id}",
        "DBT_ENV_SECRET_DATABRICKS_TOKEN": token,
        "JEV_MODE": mode,
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }


# COMMAND ----------

# jevdbx.dbt_cli keeps the surname "Null" (customer 477) text when dbt seeds the CSVs.
res = subprocess.run(
    [sys.executable, "-m", "jevdbx.dbt_cli", *args,
     "--profiles-dir", ".", "--target", "notebook"],
    cwd=project, env=dbt_env(), capture_output=True, text=True)
out = re.sub(r"\x1b\[[0-9;]*m", "", res.stdout)
print(out[-8000:])
summary = [line.strip() for line in out.splitlines() if "Jev ·" in line]
done = re.findall(r"Done\.\s.*?ERROR=(\d+)", out)
if res.returncode != 0 or not done or int(done[-1]) > 0:
    raise RuntimeError(
        f"dbt build failed (exit {res.returncode}); stderr tail:\n{res.stderr[-3000:]}")

# COMMAND ----------

# MAGIC %md ## Summary

# COMMAND ----------

displayHTML("<pre>" + "\n".join(summary) + "</pre>")

# COMMAND ----------

# MAGIC %md ## Failing rows, with Jev's probability

# COMMAND ----------

caption = ("Mode: SIMULATED (demo) — probabilities are not Jev judgments" if mode == "demo"
           else "Mode: LIVE")
displayHTML(f"<p><b>{caption}</b></p>")
from jevdbx.evallog import scored_tests  # noqa: E402

for t in scored_tests(selection):
    display(spark.sql(f"select * from jev_demo.jaffle_shop_dbt_test__audit.{t} "
                      "order by jev_p desc nulls last limit 20"))
