"""Split a trailing VISUALIZE clause off a SQL statement."""

from __future__ import annotations

import re

BARE_INTENT = "the main pattern in this query's result"
MAX_INTENTS = 6
_INTENT = re.compile(r"\s*'((?:[^']|'')*)'\s*")


class VizSyntaxError(ValueError):
    pass


def _find_keyword(sql: str) -> int | None:
    """Index of the last top-level VISUALIZE keyword, skipping strings, quoted idents and comments."""
    i, n, found = 0, len(sql), None
    while i < n:
        ch = sql[i]
        if ch in "'\"":
            i += 1
            while i < n:
                if sql[i] == ch:
                    if i + 1 < n and sql[i + 1] == ch:
                        i += 2
                        continue
                    break
                i += 1
            i += 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j + 1
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
        elif sql[i:i + 9].upper() == "VISUALIZE":
            before = sql[i - 1] if i else " "
            after = sql[i + 9] if i + 9 < n else " "
            if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                found = i
            i += 9
        else:
            i += 1
    return found


def extract_viz(sql: str) -> tuple[str, list[str] | None]:
    at = _find_keyword(sql)
    if at is None:
        return sql, None
    tail = sql[at + 9:].strip().removesuffix(";").strip()
    intents: list[str] = []
    pos = 0
    while pos < len(tail):
        m = _INTENT.match(tail, pos)
        if not m:
            raise VizSyntaxError(f"expected a quoted intent after VISUALIZE, got: {tail[pos:pos + 30]!r}")
        intents.append(m.group(1).replace("''", "'"))
        pos = m.end()
        if pos < len(tail):
            if tail[pos] != ",":
                raise VizSyntaxError(f"unexpected text after VISUALIZE clause: {tail[pos:pos + 30]!r}")
            pos += 1
            if pos >= len(tail):
                raise VizSyntaxError("trailing comma in VISUALIZE clause")
    if len(intents) > MAX_INTENTS:
        raise VizSyntaxError(f"at most {MAX_INTENTS} intents per query")
    return sql[:at].rstrip(), intents
