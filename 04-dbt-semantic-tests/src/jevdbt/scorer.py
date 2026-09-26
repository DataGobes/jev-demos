"""Scorer: states + Question -> probabilities via cache and backend, on a background loop."""

from __future__ import annotations

import asyncio
import threading
import time

from jevdbt.backend import Backend, BatchResult
from jevdbt.cache import Cache
from jevdbt.questions import Question
from jevdbt.stats import Stats


class _RpmPacer:
    """Spaces request starts to at most `rpm` per minute. `rpm <= 0` disables pacing."""

    def __init__(self, rpm: int) -> None:
        self._interval = 60.0 / rpm if rpm > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        if not self._interval:
            return
        async with self._lock:
            now = time.monotonic()
            if now < self._next:
                await asyncio.sleep(self._next - now)
                now = time.monotonic()
            self._next = max(now, self._next) + self._interval


class Scorer:
    """Owns an asyncio loop thread; `score_many` is a synchronous, thread-safe facade."""

    def __init__(
        self,
        backend: Backend,
        stats: Stats,
        cache: Cache | None = None,
        *,
        pack: int = 1,
        pack_style: str = "nested",
        concurrency: int = 32,
        rpm: int = 1200,
    ) -> None:
        self.backend = backend
        self.stats = stats
        self.cache = cache
        self.pack = max(1, pack)
        # Packing changes what the backend sees (several states per request, laid out by
        # `pack_style`), which can shift the judged probability, so a packed run's cache entries
        # must not be served to a differently-packed run. pack=1 keeps the plain backend name so
        # existing unpacked cache entries stay valid.
        self._cache_model_key = (
            backend.name if self.pack == 1 else f"{backend.name}|pack={self.pack}|{pack_style}"
        )
        self._concurrency = concurrency
        self._rpm = rpm
        self._closed = False
        self._close_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait()

    def _run_loop(self, ready: threading.Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._pacer = _RpmPacer(self._rpm)
        ready.set()
        loop.run_forever()

    def score_many(self, states: list[str | None], question: Question) -> list[float | None]:
        out: list[float | None] = [None] * len(states)
        positions: dict[str, list[int]] = {}
        for i, s in enumerate(states):
            if s is not None:
                positions.setdefault(s, []).append(i)
        if not positions:
            return out

        resolved: dict[str, float | None] = {}
        if self.cache is not None:
            resolved.update(
                self.cache.get_many(self._cache_model_key, question, list(positions))
            )
        # Cache hits are resolved synchronously (no wait involved), so they're counted right
        # away. The rest is counted chunk by chunk as each request comes back (see `_one`) so
        # a live progress ticker watching `stats` sees judgments/sent grow during the wait,
        # instead of jumping from 0 to the total only once every chunk has finished.
        cache_hit_states = [s for s in positions if s in resolved]
        if cache_hit_states:
            self.stats.add(
                judgments=sum(len(positions[s]) for s in cache_hit_states),
                unique=len(cache_hit_states),
            )
        missing = [s for s in positions if s not in resolved]
        if missing:
            chunks = [missing[i : i + self.pack] for i in range(0, len(missing), self.pack)]
            chunk_judgments = [sum(len(positions[s]) for s in c) for c in chunks]
            assert self._loop is not None
            future = asyncio.run_coroutine_threadsafe(
                self._run(chunks, chunk_judgments, question), self._loop
            )
            to_cache: dict[str, float] = {}
            for chunk, result in zip(chunks, future.result(), strict=True):
                for s, v in zip(chunk, result.values, strict=True):
                    resolved[s] = v
                    if v is not None:
                        to_cache[s] = v
            if self.cache is not None:
                self.cache.put_many(self._cache_model_key, question, to_cache)

        for s, idxs in positions.items():
            for i in idxs:
                out[i] = resolved.get(s)
        return out

    async def _run(
        self, chunks: list[list[str]], chunk_judgments: list[int], question: Question
    ) -> list[BatchResult]:
        return await asyncio.gather(
            *(
                self._one(chunk, judgments, question)
                for chunk, judgments in zip(chunks, chunk_judgments, strict=True)
            )
        )

    async def _one(self, chunk: list[str], judgments: int, question: Question) -> BatchResult:
        async with self._semaphore:
            await self._pacer.wait()
            result = await self.backend.judge(chunk, question)
        self.stats.add(
            judgments=judgments,
            unique=len(chunk),
            sent=len(chunk),
            requests=1,
            input_tokens=result.input_tokens,
        )
        if any(v is None for v in result.values):
            self.stats.add(errors=1)
        return result

    def close(self) -> None:
        """Close the scorer and backend.

        Call only after every score_many() call has returned; closing mid-call stops
        the loop and leaves in-flight callers blocked. The plugin closes at process
        exit (atexit), after dbt has finished.
        """
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(self.backend.aclose(), self._loop)
        try:
            future.result(timeout=10)
        except Exception:  # noqa: BLE001 -- best-effort shutdown
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)
