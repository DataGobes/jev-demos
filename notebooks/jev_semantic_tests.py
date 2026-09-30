# Databricks notebook source
# MAGIC %md
# MAGIC # Jev semantic dbt tests, run inside Databricks
# MAGIC `dbt build` on a serverless notebook; queries run on the SQL warehouse; Jev is the UC
# MAGIC function `jev_demo.jev.noul_pack`, whose key never leaves Unity Catalog.

# COMMAND ----------

# MAGIC %pip install -q "dbt-core==1.12.3" "dbt-databricks==1.12.5"

# COMMAND ----------

dbutils.widgets.dropdown("mode", "demo", ["demo", "live"])
dbutils.widgets.dropdown("selection", "yardstick", ["yardstick", "production"])
dbutils.widgets.text("warehouse", "jev-demo-5")

# COMMAND ----------

import os
import re
import subprocess
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient

mode = dbutils.widgets.get("mode")
selection = dbutils.widgets.get("selection")
w = WorkspaceClient()
ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
wanted = dbutils.widgets.get("warehouse")
warehouse = next(x for x in w.warehouses.list() if wanted in (x.name, x.id))

bundle_root = Path(os.getcwd()).parent  # the bundle syncs notebooks/, jaffle_shop/ and src/
project = bundle_root / "jaffle_shop"
pythonpath = os.pathsep.join(
    p for p in (str(bundle_root / "src"), os.environ.get("PYTHONPATH", "")) if p)

if selection == "production":
    args = ["build", "--vars", "{production: true}",
            "--select", "+tag:production", "tag:production_baseline"]
else:
    # A fresh schema needs stg_orders (relationships tests), so build the whole yardstick.
    args = ["build", "--exclude", "tag:production", "tag:production_baseline"]


def dbt_env() -> dict:
    """The subprocess environment. The run token lives only here (profiles.yml reads it from
    DBT_ENV_SECRET_DATABRICKS_TOKEN, which dbt scrubs from its logs); it is never displayed."""
    return {
        **os.environ,
        "PYTHONPATH": pythonpath,
        "DATABRICKS_HOST": w.config.host.removeprefix("https://").rstrip("/"),
        "JEV_HTTP_PATH": f"/sql/1.0/warehouses/{warehouse.id}",
        "DBT_ENV_SECRET_DATABRICKS_TOKEN": ctx.apiToken().get(),
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

tests = (["product_reviews_body_matches_stars"] if selection == "production"
         else ["customers_full_name_is_a_person", "returns_comment_matches_reason_code",
               "reviews_body_matches_stars", "tickets_body_has_no_pii"])
for t in tests:
    display(spark.sql(f"select * from jev_demo.jaffle_shop_dbt_test__audit.{t} "
                      "order by jev_p desc nulls last limit 20"))
