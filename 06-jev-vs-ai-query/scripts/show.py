"""Terminal views for the recording. Numbers come only from docs/eval-results.md.

    uv run python scripts/show.py tests                          # the three sentences
    uv run python scripts/show.py board [--pass N] [--scope S]   # default: pass 1, scope sample
"""

import argparse
import re
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[1]
USAGE = "usage: show.py tests | board [--pass N] [--scope sample|full]"
_COST = re.compile(r"^- llm cost (\$[0-9.]+ \(\w+\))$", re.M)
_INV = re.compile(r"^- invocation (\S+)$", re.M)


def board_rows(md: str, pass_: int = 1, scope: str = "sample") -> list[tuple[str, ...]]:
    """(judge, scope, test, F1, LLM cost) from the latest result entry per judge for one pass and
    scope. Refused and measured-cost entries are not results; a later measured-cost entry for the
    same invocation replaces the logged LLM cost."""
    blocks = re.split(r"\n(?=## )", md)
    measured = {}
    for block in blocks:
        inv, cost = _INV.search(block), _COST.search(block)
        if " · measured cost · " in block.splitlines()[0] and inv and cost:
            measured[inv[1]] = cost[1]
    latest: dict[str, str] = {}
    for block in blocks:
        m = re.match(r"## \S+ · pass (\d+) · (\S+)$", block.splitlines()[0])
        sc = re.search(r"^- scope (\S+) ·", block, re.M)
        if m and int(m[1]) == pass_ and sc and sc[1] == scope:
            latest[m[2]] = block
    out = []
    for judge, block in latest.items():
        inv, cost = _INV.search(block), _COST.search(block)
        shown = measured.get(inv[1]) if inv else None
        shown = shown or (cost[1] if cost else "-")
        for line in block.splitlines():
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 8 and not cells[0].startswith(("test", "---", "baseline")):
                out.append((judge, scope, cells[0], cells[6], shown))
    return out


def tests() -> None:
    doc = yaml.safe_load((ROOT / "bench" / "models" / "staging" / "schema.yml").read_text())
    for model in doc["models"]:
        for col in model.get("columns", []):
            for t in col.get("data_tests", []):
                if isinstance(t, dict) and "jev_expect" in t:
                    e = t["jev_expect"]
                    print(f"{e['name']}\n  {e['arguments']['fails_if']}\n")


def board(pass_: int = 1, scope: str = "sample") -> None:
    table = Table(title=f"pass {pass_} · scope {scope} · latest logged entry per judge")
    for c in ("judge", "scope", "test", "F1", "LLM cost"):
        table.add_column(c)
    for row in board_rows((ROOT / "docs" / "eval-results.md").read_text(), pass_, scope):
        table.add_row(*row)
    Console().print(table)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("tests", "board"):
        print(USAGE, file=sys.stderr)
        return 2
    if argv[0] == "tests":
        tests()
        return 0
    ap = argparse.ArgumentParser(prog="show.py board")
    ap.add_argument("--pass", dest="pass_", type=int, default=1)
    ap.add_argument("--scope", choices=["sample", "full"], default="sample")  # pilots: not results
    a = ap.parse_args(argv[1:])
    board(a.pass_, a.scope)
    return 0


if __name__ == "__main__":
    sys.exit(main())
