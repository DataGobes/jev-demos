"""Print (default) or apply the demo 06 platform DDL on the dev warehouse.

    uv run python scripts/deploy.py                 # print only
    uv run python scripts/deploy.py --apply         # confirm-first the first time (creates schema)
    uv run python scripts/deploy.py --apply --only llm_demo requests
"""

import argparse
import sys

from jevdbx.databricks import Sql
from jevdbx.deploy import platform_statements


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    stmts = platform_statements()
    known = {label for label, _ in stmts}
    if a.only and set(a.only) - known:
        print(f"unknown labels: {sorted(set(a.only) - known)}; known: {sorted(known)}")
        return 2
    chosen = [(label, sql) for label, sql in stmts if not a.only or label in a.only]
    if not a.apply:
        for label, sql in chosen:
            print(f"-- {label}\n{sql};\n")
        return 0
    sql = Sql()
    for label, stmt in chosen:
        r = sql.run(stmt)
        print(f"{label}: {r.state} {r.error or ''}")
        if r.state != "SUCCEEDED":
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
