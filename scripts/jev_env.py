"""Print shell exports for dbt: host and warehouse path from the CLI profile. Never tokens.

    eval "$(uv run python scripts/jev_env.py)"            # dev warehouse jev-demo-5
    eval "$(uv run python scripts/jev_env.py --warehouse jev-demo-5-prod)"
"""

import argparse
import os

from jevdbx.databricks import DEFAULT_PROFILE, DEFAULT_WAREHOUSE, _client, resolve_warehouse_id


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", DEFAULT_PROFILE))
    ap.add_argument("--warehouse", default=DEFAULT_WAREHOUSE)
    args = ap.parse_args(argv)
    client = _client(args.profile)
    host = client.config.host.removeprefix("https://").rstrip("/")
    wid = resolve_warehouse_id(client, args.warehouse)
    print(f"export DATABRICKS_CONFIG_PROFILE={args.profile}")
    print(f"export DATABRICKS_HOST={host}")
    print(f"export JEV_WAREHOUSE={args.warehouse}")
    print(f"export JEV_HTTP_PATH=/sql/1.0/warehouses/{wid}")


if __name__ == "__main__":
    main()
