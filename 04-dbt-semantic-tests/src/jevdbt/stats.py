"""Thread-safe counters for one dbt invocation, and the one-line run summary."""

from __future__ import annotations

import threading
from dataclasses import dataclass

# https://docs.typesafe.ai/models — charged per input token; output tokens are free.
PRICE_PER_MTOK_USD = 0.042


@dataclass(frozen=True)
class StatsSnapshot:
    judgments: int  # non-null states resolved by jev_noul (incl. in-run duplicates)
    unique: int  # distinct states resolved (per score_many call, summed)
    sent: int  # distinct states actually sent to the backend (cache misses)
    requests: int
    input_tokens: int
    errors: int
    wall_seconds: float  # wall-clock span of jev_noul activity: earliest start to latest end

    @property
    def cache_hits(self) -> int:
        """Distinct states resolved from the sqlite cache, not sent to the backend."""
        return self.unique - self.sent

    @property
    def cached_fraction(self) -> float:
        return self.cache_hits / self.unique if self.unique else 0.0

    @property
    def cost_usd(self) -> float:
        return self.input_tokens * PRICE_PER_MTOK_USD / 1_000_000


class Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._c = dict(judgments=0, unique=0, sent=0, requests=0, input_tokens=0, errors=0)
        self._span_start: float | None = None
        self._span_end: float | None = None
        self._in_flight = 0

    def add(self, **deltas: float) -> None:
        with self._lock:
            for name, delta in deltas.items():
                if name not in self._c:
                    raise KeyError(name)
                self._c[name] += delta

    def call_started(self) -> None:
        """Mark one `jev_noul` invocation as in flight (for the progress ticker)."""
        with self._lock:
            self._in_flight += 1

    def call_finished(self) -> None:
        with self._lock:
            self._in_flight -= 1

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight

    def record_span(self, start: float, end: float) -> None:
        """Extend the tracked wall-clock span of jev_noul activity to cover [start, end].

        dbt runs several tests concurrently on separate threads; each jev_noul invocation
        reports its own [start, end], and the snapshot's wall_seconds is the span from the
        earliest start to the latest end across all of them — not a sum of durations, which
        would double- (or N-) count time where threads overlap.
        """
        with self._lock:
            self._span_start = start if self._span_start is None else min(self._span_start, start)
            self._span_end = end if self._span_end is None else max(self._span_end, end)

    def snapshot(self) -> StatsSnapshot:
        with self._lock:
            wall_seconds = (
                self._span_end - self._span_start if self._span_end is not None else 0.0
            )
            return StatsSnapshot(**self._c, wall_seconds=wall_seconds)


def format_cost(usd: float) -> str:
    return "<$0.001" if usd < 0.001 else f"${usd:.3f}"


def format_summary(
    snap: StatsSnapshot, *, simulated: bool, model: str, pack: int, pack_style: str = "single"
) -> str:
    mode = "SIMULATED" if simulated else "LIVE"
    packing = f"pack={pack}" if pack == 1 else f"pack={pack}/{pack_style}"
    line = (
        f"Jev · {snap.judgments:,} judgments · {snap.unique:,} unique · "
        f"{snap.cached_fraction:.0%} cached · {snap.requests:,} requests · "
        f"{snap.wall_seconds:.1f} s · {format_cost(snap.cost_usd)} · {mode} {model} {packing}"
    )
    if snap.errors:
        line += f" · {snap.errors} errors"
    return line
