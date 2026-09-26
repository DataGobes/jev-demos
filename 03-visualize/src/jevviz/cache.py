"""Sqlite cache of (model, state_hash, question) -> Answer."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path

from jevviz.types import Answer, Question


def _digest(model: str, state_hash: str, q: Question) -> str:
    return hashlib.sha256(f"{model}\x1f{state_hash}\x1f{q.key()}".encode()).hexdigest()


class Cache:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._con.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._con.commit()

    def get_many(self, model: str, state_hash: str, questions: dict[str, Question]) -> dict[str, Answer]:
        out: dict[str, Answer] = {}
        with self._lock:
            for qid, q in questions.items():
                row = self._con.execute("SELECT value FROM cache WHERE key = ?", (_digest(model, state_hash, q),)).fetchone()
                if row:
                    d = json.loads(row[0])
                    probs = {int(k): v for k, v in d["probabilities"].items()} if d["probabilities"] else None
                    out[qid] = Answer(d["kind"], d["noul"], probs, d["confidence"])
        return out

    def put_many(self, model: str, state_hash: str, questions: dict[str, Question], answers: dict[str, Answer]) -> None:
        rows = [
            (_digest(model, state_hash, questions[qid]),
             json.dumps({"kind": a.kind, "noul": a.noul, "probabilities": a.probabilities, "confidence": a.confidence}))
            for qid, a in answers.items() if qid in questions
        ]
        with self._lock:
            self._con.executemany("INSERT INTO cache (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", rows)
            self._con.commit()

    def close(self) -> None:
        with self._lock:
            self._con.close()
