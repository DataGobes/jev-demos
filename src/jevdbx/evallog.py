"""Read-only helpers for docs/eval-results.md."""


def entry_for(md: str, invocation: str) -> str | None:
    """The `## ...` block of `md` whose own `- invocation <id>` line names `invocation`, verbatim
    (heading through the line before the next `## ` heading), or None. Only that exact line
    matches: an id quoted elsewhere in an entry (cached judgments) or in prose does not."""
    invocation = invocation.strip()
    if not invocation:
        return None
    wanted = f"- invocation {invocation}"
    block: list[str] = []
    for line in md.splitlines():
        if line.startswith("## "):
            if block and any(b.rstrip() == wanted for b in block):
                break
            block = [line]
        elif block:
            block.append(line)
    else:
        if not any(b.rstrip() == wanted for b in block):
            return None
    return "\n".join(block).strip()
