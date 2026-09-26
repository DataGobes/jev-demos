"""Verdict cache keyed on (judge id, column fingerprint).

A column whose name, type, description and SQL are unchanged is never judged twice by the same
judge. The judge id is part of the key, so switching Mock -> Jev (or changing Jev's prompt and
bumping its id) cannot reuse a verdict another judge made.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .judges import Verdict


class VerdictCache:
    """A JSON file, loaded once and written once per run. Commit it or keep it as a CI cache."""

    def __init__(self, path: Path | None):
        self.path = path
        self._data: dict[str, dict[str, dict]] = {}
        if path is not None and path.exists():
            self._data = json.loads(path.read_text())

    def get(self, judge_id: str, fingerprint: str) -> Verdict | None:
        hit = self._data.get(judge_id, {}).get(fingerprint)
        return Verdict(**hit) if hit is not None else None

    def put(self, judge_id: str, fingerprint: str, verdict: Verdict) -> None:
        self._data.setdefault(judge_id, {})[fingerprint] = asdict(verdict)

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace, so an interrupted run never leaves a half-written cache behind.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".desc_judge_cache.")
        with os.fdopen(fd, "w") as f:
            json.dump(self._data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)
