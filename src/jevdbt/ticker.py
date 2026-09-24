"""Live progress ticker for the silent stretch of `dbt test --select tag:semantic`.

Opt-in: only runs when `JEV_PROGRESS=1` (set by `scripts/record.sh`) and stderr is a real
terminal, so it never clutters a dbt log file or CI output. While any `jev_noul` call is in
flight it rewrites one stderr line ~4x/second; dbt's own stdout is untouched. When no call is
in flight it clears that line once and goes quiet, rather than spinning forever.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Mapping
from typing import Protocol

from jevdbt.stats import Stats, StatsSnapshot, format_cost

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
INTERVAL = 0.25
_CLEAR_LINE = "\r\033[K"


class _Writable(Protocol):
    def write(self, s: str) -> object: ...
    def flush(self) -> object: ...
    def isatty(self) -> bool: ...


def ticker_enabled(env: Mapping[str, str] | None = None, stream: _Writable | None = None) -> bool:
    """True only when `JEV_PROGRESS=1` and `stream` (default stderr) is a TTY."""
    env = os.environ if env is None else env
    stream = sys.stderr if stream is None else stream
    if env.get("JEV_PROGRESS") != "1":
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def format_ticker_line(snap: StatsSnapshot, elapsed: float, frame: str) -> str:
    """`  Jev · 612 judgments · 24.1 s · $0.008 ⠋` — pure, no I/O."""
    cost = format_cost(snap.cost_usd)
    return f"  Jev · {snap.judgments:,} judgments · {elapsed:.1f} s · {cost} {frame}"


class Ticker:
    """Daemon thread that rewrites one stderr line while `stats.in_flight` is nonzero."""

    def __init__(
        self,
        stats: Stats,
        *,
        stream: _Writable | None = None,
        interval: float = INTERVAL,
    ) -> None:
        self._stats = stats
        self._stream = sys.stderr if stream is None else stream
        self._interval = interval
        self._start = time.monotonic()
        self._frame = 0
        self._was_active = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
        if self._was_active:
            self._stream.write(_CLEAR_LINE)
            self._stream.flush()
            self._was_active = False

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._stats.in_flight > 0:
                frame = SPINNER_FRAMES[self._frame % len(SPINNER_FRAMES)]
                self._frame += 1
                elapsed = time.monotonic() - self._start
                line = format_ticker_line(self._stats.snapshot(), elapsed, frame)
                self._stream.write(_CLEAR_LINE + line + "\r")
                self._stream.flush()
                self._was_active = True
            elif self._was_active:
                self._stream.write(_CLEAR_LINE)
                self._stream.flush()
                self._was_active = False
            self._stop.wait(self._interval)
