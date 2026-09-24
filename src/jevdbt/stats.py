"""Thread-safe counters for one dbt invocation, and the one-line run summary."""

from __future__ import annotations

import threading
from dataclasses import dataclass

# https://docs.typesafe.ai/models — charged per input token; output tokens are free.
PRICE_PER_MTOK_USD = 0.042


@dataclass(frozen=True)
class StatsSnapshot:
    judgments: int  # non-null states resolved by jev_noul (incl. duplicates and cache hits)
    sent: int  # states actually sent to the backend
    requests: int
    input_tokens: int
    errors: int
    udf_seconds: float  # wall time spent inside jev_noul

    @property
    def cached_fraction(self) -> float:
        return 1 - self.sent / self.judgments if self.judgments else 0.0

    @property
    def cost_usd(self) -> float:
        return self.input_tokens * PRICE_PER_MTOK_USD / 1_000_000


class Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._c = dict(judgments=0, sent=0, requests=0, input_tokens=0, errors=0, udf_seconds=0.0)

    def add(self, **deltas: float) -> None:
        with self._lock:
            for name, delta in deltas.items():
                if name not in self._c:
                    raise KeyError(name)
                self._c[name] += delta

    def snapshot(self) -> StatsSnapshot:
        with self._lock:
            return StatsSnapshot(**self._c)


def _cost(usd: float) -> str:
    return "<$0.001" if usd < 0.001 else f"${usd:.3f}"


def format_summary(snap: StatsSnapshot, *, simulated: bool, model: str, pack: int) -> str:
    mode = "SIMULATED" if simulated else "LIVE"
    line = (
        f"Jev · {snap.judgments:,} judgments · {snap.cached_fraction:.0%} cached · "
        f"{snap.requests:,} requests · {snap.udf_seconds:.1f} s · {_cost(snap.cost_usd)} · "
        f"{mode} {model} pack={pack}"
    )
    if snap.errors:
        line += f" · {snap.errors} errors"
    return line
