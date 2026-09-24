"""Sqlite cache of (model, question, state) -> noul probability."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

from jevdbt.questions import Question

_CHUNK = 900  # stay under sqlite's bound-variable limit


def _digest(model: str, question: Question, state: str) -> str:
    return hashlib.sha256(f"{model}\x1f{question.key()}\x1f{state}".encode()).hexdigest()


class Cache:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        sql = "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value REAL NOT NULL)"
        self._con.execute(sql)
        self._con.commit()

    def get_many(self, model: str, question: Question, states: list[str]) -> dict[str, float]:
        keys = {_digest(model, question, s): s for s in states}
        out: dict[str, float] = {}
        key_list = list(keys)
        with self._lock:
            for i in range(0, len(key_list), _CHUNK):
                chunk = key_list[i : i + _CHUNK]
                marks = ",".join("?" * len(chunk))
                rows = self._con.execute(
                    f"SELECT key, value FROM cache WHERE key IN ({marks})", chunk
                ).fetchall()
                for key, value in rows:
                    out[keys[key]] = float(value)
        return out

    def put_many(self, model: str, question: Question, items: dict[str, float]) -> None:
        if not items:
            return
        rows = [(_digest(model, question, s), v) for s, v in items.items()]
        with self._lock:
            self._con.executemany(
                "INSERT INTO cache (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                rows,
            )
            self._con.commit()

    def close(self) -> None:
        with self._lock:
            self._con.close()
