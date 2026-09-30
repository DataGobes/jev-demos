"""Platform DDL for demo 05: schema, judgments ledger, hook_runs, requests view, both functions.

The functions' Python bodies are the real modules jevdbx.noul_pack and jevdbx.demo_pack, embedded
verbatim plus a short shim that binds their injected dependencies to the UC runtime.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from jevdbx import demo_pack, noul_pack

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Target:
    catalog: str = "jev_demo"
    schema: str = "jev"
    secret: str = "typesafe_api_key"

    def __post_init__(self):
        for value in (self.catalog, self.schema, self.secret):
            if not _IDENT.match(value):
                raise ValueError(f"not a safe identifier: {value!r}")

    def fq(self, name: str) -> str:
        return f"{self.catalog}.{self.schema}.{name}"


def _source(module) -> str:
    src = Path(module.__file__).read_text()
    if "from __future__" in src or "$$" in src:
        raise ValueError(f"{module.__name__} cannot be embedded in a UC function body")
    return src


_LIVE_SHIM = """
import time as _time
import uuid as _uuid
from databricks.secrets import get as _uc_secret_get

return handler(
    records, question, model,
    get_key=lambda: _uc_secret_get(catalog={catalog!r}, schema={schema!r}, key={secret!r}),
    post=urllib_post, sleep=_time.sleep, now=_time.time, new_id=lambda: str(_uuid.uuid4()),
)
"""

_DEMO_SHIM = """
import time as _time
import uuid as _uuid

return handler(records, question, model, now=_time.time, new_id=lambda: str(_uuid.uuid4()))
"""

_SIGNATURE = "(records ARRAY<STRING>, question STRING, model STRING)"


def live_function_sql(t: Target) -> str:
    shim = _LIVE_SHIM.format(catalog=t.catalog, schema=t.schema, secret=t.secret)
    body = _source(noul_pack) + shim
    return (
        f"CREATE OR REPLACE FUNCTION {t.fq('noul_pack')}{_SIGNATURE}\n"
        "RETURNS STRING\nLANGUAGE PYTHON\nNOT DETERMINISTIC\n"
        "COMMENT 'Jev (TypeSafe) Noul probabilities for one nested pack of records. jev-demo-5.'\n"
        f"SECRETS ({t.fq(t.secret)})\n"
        "ENVIRONMENT (environment_version = '6')\n"
        f"AS $$\n{body}\n$$"
    )


def demo_function_sql(t: Target) -> str:
    body = _source(demo_pack) + _DEMO_SHIM
    return (
        f"CREATE OR REPLACE FUNCTION {t.fq('noul_pack_demo')}{_SIGNATURE}\n"
        "RETURNS STRING\nLANGUAGE PYTHON\nNOT DETERMINISTIC\n"
        "COMMENT 'SIMULATED stand-in for noul_pack: hash values, no network. jev-demo-5.'\n"
        f"AS $$\n{body}\n$$"
    )


def judgments_table_sql(t: Target) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {t.fq('judgments')} (
  key STRING, test_name STRING, model_name STRING, question STRING, state STRING,
  p DOUBLE, requested_model STRING, answered_model STRING, mode STRING, layout STRING,
  pack_uuid STRING, pack_rows INT, pack_tokens BIGINT, pack_est_tokens BIGINT,
  attempts INT, retry_statuses ARRAY<INT>, error STRING,
  started_at TIMESTAMP, finished_at TIMESTAMP, invocation_id STRING, judged_at TIMESTAMP
) CLUSTER BY (key)
COMMENT 'Jev judgments: cache (successful rows) and ledger. jev-demo-5.'"""


def hook_runs_table_sql(t: Target) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {t.fq('hook_runs')} (
  invocation_id STRING, test_name STRING, model_name STRING, mode STRING, requested_model STRING,
  tested BIGINT, missing BIGINT, oversized BIGINT, inserted BIGINT, recorded_at TIMESTAMP
)
COMMENT 'One row per (dbt invocation, jev_expect test) written by the jev_judge post-hook.'"""


def requests_view_sql(t: Target) -> str:
    return f"""CREATE OR REPLACE VIEW {t.fq('requests')} AS
SELECT pack_uuid,
       any_value(invocation_id) AS invocation_id, any_value(test_name) AS test_name,
       any_value(mode) AS mode, any_value(answered_model) AS answered_model,
       any_value(pack_rows) AS pack_rows, any_value(pack_tokens) AS pack_tokens,
       any_value(pack_est_tokens) AS pack_est_tokens, any_value(attempts) AS attempts,
       any_value(retry_statuses) AS retry_statuses, any_value(error) AS error,
       min(started_at) AS started_at, max(finished_at) AS finished_at, count(*) AS rows_written
FROM {t.fq('judgments')}
WHERE pack_uuid IS NOT NULL
GROUP BY pack_uuid"""


def platform_statements(t: Target | None = None) -> list[tuple[str, str]]:
    t = t or Target()
    return [
        ("schema", f"CREATE SCHEMA IF NOT EXISTS {t.catalog}.{t.schema} "
                   "COMMENT 'Jev semantic tests: functions, judgments ledger. jev-demo-5.'"),
        ("judgments", judgments_table_sql(t)),
        ("hook_runs", hook_runs_table_sql(t)),
        ("requests", requests_view_sql(t)),
        ("noul_pack_demo", demo_function_sql(t)),
        ("noul_pack", live_function_sql(t)),
    ]


# --smoke: one fixed 2-row call of a deployed function. For the live function this is a live Jev
# call (billed by TypeSafe): confirm first. Record 1 contradicts its stars, record 2 matches.
SMOKE_MODEL = "jev-1.13.0"  # the pinned dbt var jev_model (a test keeps them equal)
SMOKE_RECORDS = (
    json.dumps({"body": "Absolutely loved it, the best coffee I have had in years.", "stars": 1}),
    json.dumps({"body": "Stale and bitter. I threw the bag away.", "stars": 1}),
)
SMOKE_QUESTION = json.dumps({
    "instructions": "The overall sentiment of the review `record.body` clearly contradicts its "
                    "`record.stars` rating (1 = very bad, 5 = excellent).",
    "criteria": {"true": "A glowing text with 1-2 stars, or an angry text with 4-5 stars",
                 "false": "Sentiment roughly matches the stars"},
})


def sql_string(value: str) -> str:
    """A Databricks SQL string literal. `''` is not an escape there: quotes become `\\'` and
    backslashes are doubled."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def smoke_sql(t: Target, function: str = "noul_pack") -> str:
    """SELECT one call of `function` on SMOKE_RECORDS; the result is the function's JSON."""
    if function not in ("noul_pack", "noul_pack_demo"):
        raise ValueError(f"not a Jev function: {function!r}")
    records = ", ".join(sql_string(r) for r in SMOKE_RECORDS)
    return (f"SELECT {t.fq(function)}(array({records}), {sql_string(SMOKE_QUESTION)}, "
            f"{sql_string(SMOKE_MODEL)}) AS result")


def production_statements(catalog: str = "jev_demo") -> list[tuple[str, str]]:
    if not _IDENT.match(catalog):
        raise ValueError(f"not a safe identifier: {catalog!r}")
    return [
        ("production schema", f"CREATE SCHEMA IF NOT EXISTS {catalog}.production "
                              "COMMENT 'Production run: real product reviews. jev-demo-5.'"),
        ("raw volume", f"CREATE VOLUME IF NOT EXISTS {catalog}.production.raw "
                       "COMMENT 'Parquet files written by scripts/fetch_reviews.py'"),
    ]
