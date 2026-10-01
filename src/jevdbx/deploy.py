"""Platform DDL for demo 06: schema jev_demo.bench, judgments ledger, hook_runs, requests view,
the SIMULATED LLM stand-in llm_demo, and the raw-data volume. The Jev functions live in
jev_demo.jev (deployed by demo 05) and are only referenced."""

import re
from dataclasses import dataclass

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Target:
    catalog: str = "jev_demo"
    schema: str = "bench"
    function_schema: str = "jev"

    def __post_init__(self):
        for value in (self.catalog, self.schema, self.function_schema):
            if not _IDENT.match(value):
                raise ValueError(f"not a safe identifier: {value!r}")

    def fq(self, name: str) -> str:
        return f"{self.catalog}.{self.schema}.{name}"

    def fn(self, name: str) -> str:
        return f"{self.catalog}.{self.function_schema}.{name}"


def sql_string(value: str) -> str:
    """A Databricks SQL string literal: quotes become \\' and backslashes are doubled."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def judgments_table_sql(t: Target) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {t.fq('judgments')} (
  key STRING, judge STRING, test_name STRING, model_name STRING, question STRING, state STRING,
  p DOUBLE, decision BOOLEAN, requested_model STRING, answered_model STRING, mode STRING,
  layout STRING, pack_uuid STRING, pack_rows INT, pack_tokens BIGINT, pack_est_tokens BIGINT,
  attempts INT, retry_statuses ARRAY<INT>, error STRING,
  started_at TIMESTAMP, finished_at TIMESTAMP, invocation_id STRING, judged_at TIMESTAMP
) CLUSTER BY (key)
COMMENT 'Judgments by Jev and by ai_query LLMs: cache (successful rows) and ledger. jev-demo-6.'"""


def hook_runs_table_sql(t: Target) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {t.fq('hook_runs')} (
  invocation_id STRING, judge STRING, test_name STRING, model_name STRING, mode STRING,
  requested_model STRING, tested BIGINT, missing BIGINT, oversized BIGINT, inserted BIGINT,
  started_at TIMESTAMP, finished_at TIMESTAMP
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


def llm_demo_function_sql(t: Target) -> str:
    """SIMULATED stand-in for ai_query(..., failOnError => false): same return shape, a
    hash-derived probability, no network. Every 97th prompt returns an error."""
    return f"""CREATE OR REPLACE FUNCTION {t.fq('llm_demo')}(endpoint STRING, prompt STRING)
RETURNS STRUCT<result: STRING, errorMessage: STRING>
COMMENT 'SIMULATED stand-in for ai_query: hash values, no network. jev-demo-6.'
RETURN (
  WITH h AS (SELECT sha2(concat(endpoint, prompt), 256) AS d)
  SELECT CASE
    WHEN pmod(conv(substr(d, 9, 8), 16, 10), 97) = 0
      THEN named_struct('result', CAST(NULL AS STRING), 'errorMessage', 'SIMULATED error')
    ELSE named_struct(
      'result', to_json(named_struct(
          'decision', conv(substr(d, 1, 8), 16, 10) / 4294967295.0 > 0.5,
          'probability', round(conv(substr(d, 1, 8), 16, 10) / 4294967295.0, 4))),
      'errorMessage', CAST(NULL AS STRING))
  END FROM h
)"""


def raw_volume_sql(t: Target) -> str:
    return (f"CREATE VOLUME IF NOT EXISTS {t.fq('raw')} "
            "COMMENT 'Parquet files written by scripts/fetch_data.py. jev-demo-6.'")


def platform_statements(t: Target | None = None) -> list[tuple[str, str]]:
    t = t or Target()
    return [
        ("schema", f"CREATE SCHEMA IF NOT EXISTS {t.catalog}.{t.schema} "
                   "COMMENT 'Demo 06: Jev vs LLMs (ai_query) as dbt semantic tests.'"),
        ("raw volume", raw_volume_sql(t)),
        ("judgments", judgments_table_sql(t)),
        ("hook_runs", hook_runs_table_sql(t)),
        ("requests", requests_view_sql(t)),
        ("llm_demo", llm_demo_function_sql(t)),
    ]
