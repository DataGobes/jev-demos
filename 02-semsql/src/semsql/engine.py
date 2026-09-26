"""Scorer: turns text + Question into values via cache + backend, off the caller's thread."""

from __future__ import annotations

import asyncio
import threading
import time

from semsql.backend import Backend, Value
from semsql.cache import Cache
from semsql.questions import Question
from semsql.stats import Stats


class _RpmPacer:
    """Caps request starts to at most `rpm` per minute. `rpm <= 0` disables pacing."""

    def __init__(self, rpm: int) -> None:
        self._min_interval = 60.0 / rpm if rpm > 0 else 0.0
        self._enabled = rpm > 0
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def wait(self) -> None:
        if not self._enabled:
            return
        async with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                await asyncio.sleep(self._next_allowed - now)
                now = time.monotonic()
            self._next_allowed = max(now, self._next_allowed) + self._min_interval


class Scorer:
    """Owns a background asyncio loop thread; `score_many` is a sync, thread-safe facade."""

    def __init__(
        self,
        backend: Backend,
        stats: Stats,
        cache: Cache | None = None,
        *,
        pack: int = 1,
        concurrency: int = 32,
        rpm: int = 1200,
    ) -> None:
        self.backend = backend
        self.stats = stats
        self.cache = cache
        self.pack = max(1, pack)
        self.concurrency = concurrency
        self.rpm = rpm
        self._closed = False
        self._close_lock = threading.Lock()

        self._loop: asyncio.AbstractEventLoop | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._pacer: _RpmPacer | None = None
        ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, args=(ready,), daemon=True
        )
        self._thread.start()
        ready.wait()

    def _run_loop(self, ready: threading.Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._pacer = _RpmPacer(self.rpm)
        ready.set()
        loop.run_forever()

    def score_many(
        self, texts: list[str | None], question: Question
    ) -> list[Value | None]:
        """Resolve `texts` against `question`, using cache then backend. Order preserved."""
        result: list[Value | None] = [None] * len(texts)
        positions_by_text: dict[str, list[int]] = {}
        for i, text in enumerate(texts):
            if not text:
                continue
            positions_by_text.setdefault(text, []).append(i)
        distinct_texts = list(positions_by_text.keys())
        if not distinct_texts:
            return result

        resolved: dict[str, Value] = {}
        if self.cache is not None:
            hits = self.cache.get_many(self.backend.name, question, distinct_texts)
            if hits:
                resolved.update(hits)
                self.stats.add(cache_hits=len(hits), rows=len(hits))

        missing = [t for t in distinct_texts if t not in resolved]
        if missing:
            chunks = [
                missing[i : i + self.pack] for i in range(0, len(missing), self.pack)
            ]
            future = asyncio.run_coroutine_threadsafe(
                self._run_chunks(chunks, question), self._loop
            )
            chunk_results = future.result()
            to_cache: dict[str, Value] = {}
            for chunk, batch_result in zip(chunks, chunk_results):
                for text, value in zip(chunk, batch_result.values):
                    resolved[text] = value
                    if value is not None:
                        to_cache[text] = value
            if self.cache is not None and to_cache:
                self.cache.put_many(self.backend.name, question, to_cache)

        for text, idxs in positions_by_text.items():
            value = resolved.get(text)
            for i in idxs:
                result[i] = value
        return result

    async def _run_chunks(self, chunks: list[list[str]], question: Question) -> list:
        tasks = [
            asyncio.create_task(self._run_one_chunk(chunk, question))
            for chunk in chunks
        ]
        return await asyncio.gather(*tasks)

    async def _run_one_chunk(self, chunk: list[str], question: Question):
        assert self._semaphore is not None and self._pacer is not None
        async with self._semaphore:
            await self._pacer.wait()
            result = await self.backend.judge(chunk, question)
        self.stats.add(rows=len(chunk), requests=1, input_tokens=result.input_tokens)
        if any(v is None for v in result.values):
            self.stats.add(errors=1)
        return result

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        future = asyncio.run_coroutine_threadsafe(self.backend.aclose(), self._loop)
        try:
            future.result(timeout=10)
        except Exception:  # noqa: BLE001, S110 -- best-effort shutdown, must not block close()
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)
