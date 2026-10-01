"""Terminal views for the recording. Numbers come only from docs/eval-results.md.

    uv run python scripts/show.py tests     # the three sentences
    uv run python scripts/show.py board     # latest logged pass per judge
"""

import re
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[1]


def board_rows(md: str) -> list[tuple[str, str, str, str]]:
    latest: dict[str, str] = {}
    for block in re.split(r"\n(?=## \d{4}-)", md):
        m = re.match(r"## \S+ · pass \d+ · (\S+)", block.strip())
        if m:
            latest[m[1]] = block
    out = []
    for judge, block in latest.items():
        cost = re.search(r"^- llm cost (\$[0-9.]+ \(\w+\))$", block, re.M)
        for line in block.splitlines():
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 8 and not cells[0].startswith(("test", "---", "baseline")):
                out.append((judge, cells[0], cells[6], cost[1] if cost else "-"))
    return out


def tests() -> None:
    doc = yaml.safe_load((ROOT / "bench" / "models" / "staging" / "schema.yml").read_text())
    for model in doc["models"]:
        for col in model.get("columns", []):
            for t in col.get("data_tests", []):
                if isinstance(t, dict) and "jev_expect" in t:
                    e = t["jev_expect"]
                    print(f"{e['name']}\n  {e['arguments']['fails_if']}\n")


def board() -> None:
    table = Table(title="latest logged pass per judge")
    for c in ("judge", "test", "F1", "LLM cost"):
        table.add_column(c)
    for row in board_rows((ROOT / "docs" / "eval-results.md").read_text()):
        table.add_row(*row)
    Console().print(table)


if __name__ == "__main__":
    {"tests": tests, "board": board}[sys.argv[1]]()
