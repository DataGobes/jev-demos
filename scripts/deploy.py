"""Print (default) or apply (--apply) the demo 05 platform DDL on the dev warehouse.

    uv run python scripts/deploy.py                 # print every statement
    uv run python scripts/deploy.py --apply         # run them (schema, tables, view, functions)
    uv run python scripts/deploy.py --apply --only noul_pack noul_pack_demo
    uv run python scripts/deploy.py --production --apply   # production schema + volume (ask first)
"""

import argparse
import sys

from jevdbx import deploy
from jevdbx.databricks import Sql


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--production", action="store_true")
    args = ap.parse_args(argv)
    stmts = deploy.production_statements() if args.production else deploy.platform_statements()
    if args.only:
        stmts = [(label, sql) for label, sql in stmts if label in args.only]
    if not args.apply:
        for label, sql in stmts:
            print(f"-- {label}\n{sql};\n")
        return 0
    sql = Sql()
    for label, stmt in stmts:
        res = sql.run(stmt)
        note = f" -- {res.error}" if res.error else ""
        print(f"{label}: {res.state} ({res.wall_s:.1f} s){note}")
        if res.state != "SUCCEEDED":
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
