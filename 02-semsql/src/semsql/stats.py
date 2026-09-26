"""Thread-safe live counters for a running semsql query."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

PRICE_PER_MTOK_USD = 0.042


@dataclass(frozen=True)
class StatsSnapshot:
    """Immutable view of counters at a point in time."""

    rows: int
    cache_hits: int
    requests: int
    input_tokens: int
    errors: int
    elapsed_s: float

    @property
    def rows_per_s(self) -> float:
        return self.rows / self.elapsed_s if self.elapsed_s > 0 else 0.0

    @property
    def cost_usd(self) -> float:
        return self.input_tokens * PRICE_PER_MTOK_USD / 1_000_000


class Stats:
    """Accumulates counters under a lock; safe to update from many threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows = 0
        self._cache_hits = 0
        self._requests = 0
        self._input_tokens = 0
        self._errors = 0
        self._started_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._rows = 0
            self._cache_hits = 0
            self._requests = 0
            self._input_tokens = 0
            self._errors = 0
            self._started_at = time.monotonic()

    def add(
        self,
        *,
        rows: int = 0,
        cache_hits: int = 0,
        requests: int = 0,
        input_tokens: int = 0,
        errors: int = 0,
    ) -> None:
        with self._lock:
            self._rows += rows
            self._cache_hits += cache_hits
            self._requests += requests
            self._input_tokens += input_tokens
            self._errors += errors

    def snapshot(self) -> StatsSnapshot:
        with self._lock:
            return StatsSnapshot(
                rows=self._rows,
                cache_hits=self._cache_hits,
                requests=self._requests,
                input_tokens=self._input_tokens,
                errors=self._errors,
                elapsed_s=time.monotonic() - self._started_at,
            )
