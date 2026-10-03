"""Spike S2: 3 fixed rows through each LLM endpoint with ai_query (confirm-first: billed).

    uv run python scripts/probe_endpoints.py --print            # SQL only, no call
    uv run python scripts/probe_endpoints.py --run              # 4 sets: gpt-oss x2, llama, sonnet
    uv run python scripts/probe_endpoints.py --usage            # system.serving table columns
"""

import argparse
import json

from jevdbx.databricks import Sql

ENDPOINTS = ["databricks-gpt-oss-20b", "databricks-meta-llama-3-3-70b-instruct",
             "databricks-claude-sonnet-5-5"]
RESPONSE_FORMAT = json.dumps({
    "type": "json_schema",
    "json_schema": {
        "name": "judgment",
        "schema": {"type": "object",
                   "properties": {"decision": {"type": "boolean"},
                                  "probability": {"type": "number"}},
                   "required": ["decision", "probability"], "additionalProperties": False},
        "strict": True,
    },
})
_STMT = "Statement: the review contradicts its rating.\n"
ROWS = [
    _STMT + 'record = {"comment": "Terrible stay", "rating": 4.8}',
    _STMT + 'record = {"comment": "Lovely place", "rating": 4.9}',
    _STMT + 'record = {"comment": "Lovely place", "rating": 1.2}',
]


def _lit(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def probe_sql(endpoint: str, reasoning_low: bool) -> str:
    params = "'temperature', 0.0" + (", 'reasoning_effort', 'low'" if reasoning_low else "")
    rows = " union all ".join(f"select {_lit(r)} as prompt" for r in ROWS)
    return (f"select prompt, ai_query({_lit(endpoint)}, prompt, "
            f"responseFormat => {_lit(RESPONSE_FORMAT)}, "
            f"modelParameters => named_struct({params}), failOnError => false) as r "
            f"from ({rows})")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--print", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--usage", action="store_true")
    a = ap.parse_args(argv)
    if a.print:
        for e in ENDPOINTS:
            print(probe_sql(e, e.startswith("databricks-gpt-oss")), end="\n\n")
        return
    sql = Sql()
    if a.usage:
        for t in ("endpoint_usage", "served_entities"):
            r = sql.run(f"select column_name, data_type from system.information_schema.columns "
                        f"where table_schema = 'serving' and table_name = '{t}'")
            print(t, r.error or r.rows)
        return
    for e in ENDPOINTS:
        for low in ([True, False] if e.startswith("databricks-gpt-oss") else [False]):
            r = sql.run(probe_sql(e, low))
            print(f"== {e} reasoning_low={low}: {r.state} {r.error or ''}")
            print("   columns:", r.columns)
            for row in r.rows:
                print("  ", row)


if __name__ == "__main__":
    main()
