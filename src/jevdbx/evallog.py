"""docs/eval-results.md helpers: spend and tokens-per-row from logged lines, appending entries."""

import re
from pathlib import Path

_COST = re.compile(r"- llm cost \$([0-9.]+) \((?:measured|estimated)\)")
PREREG = "## Pre-registration (frozen before pass 1)"


_INV = re.compile(r"^- invocation (\S+)$", re.M)


def llm_spend(md: str) -> float:
    """Logged LLM spend. A later entry for the same invocation (a `measured cost` entry written by
    `score.py --measure`) replaces that invocation's earlier (estimated) cost."""
    by_inv: dict[str, float] = {}
    loose = 0.0
    for block in re.split(r"\n(?=## )", md):
        costs = []
        for line in block.split("\n"):  # not splitlines(): a stray \r must fail, not vanish
            if line.startswith("- llm cost"):
                m = _COST.fullmatch(line)
                if m is None:  # an unparsed cost line would drop spend from the $15 guard
                    raise ValueError(f"cannot parse llm cost line {line!r}")
                costs.append(float(m[1]))
        if not costs:
            continue
        inv = _INV.search(block)
        if inv:
            by_inv[inv[1]] = sum(costs)
        else:
            loose += sum(costs)
    return round(loose + sum(by_inv.values()), 6)


def tokens_per_row(md: str, endpoint: str, test: str) -> tuple[int, int] | None:
    found = None
    for block in re.split(r"\n(?=## )", md):
        head = block.splitlines()[0]
        if " · pilot · " in head and head.endswith(endpoint):
            m = re.search(rf"^- tokens/row {re.escape(test)} in (\d+) out (\d+) \(measured\)$",
                          block, re.M)
            if m:
                found = (int(m[1]), int(m[2]))
    return found


def append(path: Path, entry: str) -> None:
    text = path.read_text()
    path.write_text(text.rstrip("\n") + "\n\n" + entry.rstrip("\n") + "\n")


def has_preregistration(md: str) -> bool:
    return PREREG in md
