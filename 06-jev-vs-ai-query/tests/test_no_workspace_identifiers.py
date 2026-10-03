"""No workspace identifiers in any tracked file (the repo is headed for the public jev-demos).

Scans every file `git ls-files` lists for: 16-hex warehouse ids, Azure Databricks hosts, abfss
URLs, ADLS hosts, GUIDs (tenant/subscription/workspace ids), and the storage-account and workspace
names used during development. Those two names are matched by sha256 of each word, so this file
does not spell them out. Exclusions are explicit: the seed CSVs (generated data) in bench/seeds and
the fake values in the test fixtures listed in ALLOWED. The fixture values below are split into
pieces so this file does not match itself.

A dbt invocation id is a random per-run UUID, not a workspace identifier: a GUID written as
`invocation <uuid>` (how scripts/score.py logs it in docs/eval-results.md) is allowed.
"""

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]

PATTERNS = {
    "16-hex warehouse id": re.compile(r"\b[0-9a-f]{16}\b"),
    "Azure Databricks host": re.compile(r"azuredatabricks\.net", re.I),
    "abfss URL": re.compile(r"abfss:/{2}", re.I),
    "ADLS host": re.compile(r"\.dfs\.core\.windows\.net", re.I),
    "GUID": re.compile(
        r"(?<!invocation )\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    "storage-account name pattern": re.compile(r"\bjevdemo\d*uc[a-z]{0,8}\b", re.I),
}
# sha256 of words that must never appear: the dev workspace name and the dev storage account.
FORBIDDEN_WORD_HASHES = {
    "39765b77166d677befae702f0f7cd713e6d3f56c91236a76929e8b12b21a787e",
    "4f8716c7d1c5eb562426a854375638b274acf97fc58556dacf99f4e93b643ce5",
}
# (path, exact matched text): fake values in test fixtures.
ALLOWED = {
    ("tests/test_databricks_client.py", "azuredatabricks" + ".net"),
}
SKIP = re.compile(r"^bench/seeds/.*\.csv$")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [p for p in out.stdout.splitlines() if not SKIP.match(p)]


def findings(path: str, text: str) -> list[str]:
    hits = []
    for name, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            if (path, m.group(0)) not in ALLOWED:
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{path}:{line}: {name}")
    for m in re.finditer(r"[A-Za-z0-9_-]+", text):
        if hashlib.sha256(m.group(0).lower().encode()).hexdigest() in FORBIDDEN_WORD_HASHES:
            hits.append(f"{path}:{text.count(chr(10), 0, m.start()) + 1}: forbidden name")
    return hits


def test_the_scanner_catches_each_pattern():
    guid = "01234567-89ab-" + "cdef-0123-456789abcdef"
    samples = [
        "warehouse 0a1b2c3d" + "4e5f6a7b", "adb-9.9.azuredatabricks" + ".net", "abfss" + "://c@x",
        "x.dfs.core" + ".windows.net", "tenant " + guid, "jevdemo" + "7ucneu",
    ]
    for s in samples:
        assert findings("docs/x.md", s), s
    assert not findings("docs/x.md", "invocation " + guid)
    assert findings("tests/test_databricks_client.py", "azuredatabricks" + ".net") == []


def test_no_workspace_identifiers_in_tracked_files():
    hits = []
    for path in tracked_files():
        p = ROOT / path
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary
        hits += findings(path, text)
    assert hits == [], "\n".join(hits)
