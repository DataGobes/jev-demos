"""`desc-judge`: a check-shaped CLI over the dbt v2 information schema. 0 rows = pass.

    dbt compile --generate-info-schema          # writes target/info_schema/v1/
    desc-judge --info-schema target/info_schema/v1
    desc-judge --info-schema target/info_schema/v1 --state prod_info_schema/v1   # changed columns only
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .cache import VerdictCache
from .facts import load_column_facts
from .judges import JUDGES
from .runner import evaluate

CHECK_NAME = "description_matches_column"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="desc-judge", description=__doc__.splitlines()[0])
    p.add_argument("--info-schema", type=Path, required=True, help="target/info_schema/v1 directory")
    p.add_argument(
        "--state",
        type=Path,
        help="a baseline info_schema/v1 (e.g. from main); only columns that differ from it are judged",
    )
    p.add_argument(
        "--select",
        nargs="*",
        metavar="UNIQUE_ID",
        help="limit to these model unique_ids (e.g. from `dbt ls -s state:modified --output json`)",
    )
    p.add_argument("--judge", choices=sorted(JUDGES), default="mock")
    p.add_argument("--cache", type=Path, default=Path(".desc_judge_cache.json"))
    p.add_argument("--no-cache", action="store_true", help="judge everything, keep nothing")
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--format", choices=["table", "json"], default="table")
    p.add_argument("--warn", action="store_true", help="report failures but exit 0 (severity: warn)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    judge = JUDGES[args.judge]()
    cache = VerdictCache(None if args.no_cache else args.cache)
    facts = load_column_facts(args.info_schema)
    baseline = load_column_facts(args.state) if args.state else None
    select = set(args.select) if args.select else None

    report = evaluate(facts, judge, cache, select=select, baseline=baseline, batch_size=args.batch_size)
    cache.save()

    failed = bool(report.failures)
    status = "PASS" if not failed else ("WARN" if args.warn else "FAIL")
    stats = (
        f"judge={judge.id} in_scope={report.in_scope} judged={report.judged} cached={report.cached} "
        f"unchanged={report.unchanged} undocumented={report.undocumented}"
    )
    if args.format == "json":
        print(json.dumps({
            "check": CHECK_NAME,
            "status": status.lower(),
            "violations": len(report.failures),
            "stats": {k: v for k, v in asdict(report).items() if k != "failures"} | {"judge": judge.id},
            "rows": [asdict(f) for f in report.failures],
        }, indent=2))
    else:
        print(f"{status} {CHECK_NAME} ({len(report.failures)} violations) [{stats}]")
        if report.failures:
            w_id = max(len(f.unique_id) for f in report.failures)
            w_col = max(len(f.column_name) for f in report.failures)
            print(f"  {'unique_id':<{w_id}}  {'column_name':<{w_col}}  message")
            for f in report.failures:
                print(f"  {f.unique_id:<{w_id}}  {f.column_name:<{w_col}}  {f.message}  ({f.description!r})")
    return 1 if failed and not args.warn else 0


if __name__ == "__main__":
    sys.exit(main())
