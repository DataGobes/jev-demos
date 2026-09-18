"""Sqlite-backed cache of (model, question, text) -> judgment value."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

from semsql.questions import Question

Value = float | str

_CHUNK = 900  # keep well under sqlite's default 999 bound-variable limit


def _digest(model: str, question: Question, text: str) -> str:
    payload = f"{model}\x1f{question.key()}\x1f{text}".encode()
    return hashlib.sha256(payload).hexdigest()


class Cache:
    """Thread-safe sqlite cache. One row per (model, question, text) digest."""

    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, kind TEXT NOT NULL)"
        )
        self._con.commit()

    def get_many(self, model: str, question: Question, texts: list[str]) -> dict[str, float | str]:
        """Return {text: value} for texts found in the cache."""
        keys = {_digest(model, question, text): text for text in texts}
        if not keys:
            return {}
        result: dict[str, float | str] = {}
        key_list = list(keys)
        with self._lock:
            for i in range(0, len(key_list), _CHUNK):
                chunk = key_list[i : i + _CHUNK]
                placeholders = ",".join("?" * len(chunk))
                rows = self._con.execute(
                    f"SELECT key, value, kind FROM cache WHERE key IN ({placeholders})",
                    chunk,
                ).fetchall()
                for key, value, kind in rows:
                    text = keys[key]
                    result[text] = float(value) if kind == "float" else value
        return result

    def put_many(self, model: str, question: Question, items: dict[str, float | str]) -> None:
        """Upsert {text: value} into the cache in a single transaction."""
        if not items:
            return
        rows = []
        for text, value in items.items():
            key = _digest(model, question, text)
            kind = "float" if isinstance(value, float) else "str"
            rows.append((key, str(value), kind))
        with self._lock:
            self._con.executemany(
                "INSERT INTO cache (key, value, kind) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, kind=excluded.kind",
                rows,
            )
            self._con.commit()

    def clear(self) -> None:
        with self._lock:
            self._con.execute("DELETE FROM cache")
            self._con.commit()

    def close(self) -> None:
        with self._lock:
            self._con.close()
