"""Print (default) or apply (--apply) the demo 05 platform DDL on the dev warehouse.

    uv run python scripts/deploy.py                 # print every statement
    uv run python scripts/deploy.py --apply         # run them (schema, tables, view, functions)
    uv run python scripts/deploy.py --apply --only noul_pack noul_pack_demo
    uv run python scripts/deploy.py --production --apply   # production schema + volume (ask first)
    uv run python scripts/deploy.py --smoke         # one 2-row call of noul_pack: a LIVE Jev call,
                                                    # billed by TypeSafe (ask first)
    uv run python scripts/deploy.py --smoke --demo  # the same call of noul_pack_demo (SIMULATED)
"""

import argparse
import json
import sys

from jevdbx import deploy
from jevdbx.databricks import Sql


def smoke(demo: bool) -> int:
    """Run deploy.smoke_sql and print what the function returned (never the key: the function
    has no way to return it, and its errors are redacted)."""
    function = "noul_pack_demo" if demo else "noul_pack"
    label = "SIMULATED" if demo else "LIVE"
    res = Sql().run(deploy.smoke_sql(deploy.Target(), function))
    print(f"{label} smoke: jev_demo.jev.{function}, 2 records ({res.wall_s:.1f} s)")
    if res.state != "SUCCEEDED":
        print(f"statement {res.state}: {res.error}")
        return 1
    out = json.loads(res.rows[0][0])
    print(f"values: {out.get('values')}")
    print(f"input_tokens: {out.get('input_tokens')}")
    print(f"model: {out.get('model')}")
    print(f"attempts: {out.get('attempts')} · retries: {out.get('retries')}")
    print(f"error: {out.get('error')}")
    ok = out.get("error") is None and len(out.get("values") or []) == len(deploy.SMOKE_RECORDS)
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", nargs="+", metavar="LABEL")
    ap.add_argument("--production", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="one 2-row call of the deployed noul_pack: a LIVE Jev call (ask first)")
    ap.add_argument("--demo", action="store_true",
                    help="with --smoke: call noul_pack_demo instead (SIMULATED, no Jev call)")
    args = ap.parse_args(argv)
    if args.smoke and (args.apply or args.only or args.production):
        ap.error("--smoke runs no DDL: use it without --apply, --only or --production")
    if args.demo and not args.smoke:
        ap.error("--demo needs --smoke")
    if args.smoke:
        return smoke(args.demo)
    stmts = deploy.production_statements() if args.production else deploy.platform_statements()
    if args.only:
        valid = [label for label, _ in stmts]
        unknown = [label for label in args.only if label not in valid]
        if unknown:
            ap.error(f"unknown --only label(s): {', '.join(unknown)}; "
                     f"valid labels: {', '.join(valid)}")
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
