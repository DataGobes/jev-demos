"""FastAPI app: POST /run streams NDJSON events as each stage completes."""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from jevviz.backend import Backend, make_backend
from jevviz.cache import Cache
from jevviz.db import QueryError, open_db, run_query
from jevviz.parse import VizSyntaxError, extract_viz
from jevviz.pipeline import visualize


class RunRequest(BaseModel):
    sql: str


def _line(event: dict) -> bytes:
    return (json.dumps(event, default=str) + "\n").encode()


@cache
def _connection(resolved_db_path: str):
    # DuckDB caches instances by file path within a process, so re-opening the
    # same file (e.g. multiple `create_app` calls against one db in tests)
    # fails on the second `SET lock_configuration`. Cache by resolved path so
    # repeated `create_app` calls for the same file, spelled differently
    # (relative vs. absolute, redundant `.`/`..` components), share one
    # connection instead of racing to open the file twice.
    return open_db(resolved_db_path)


def create_app(db_path: Path | str, backend: Backend | None = None, cache_path: Path | str | None = None,
               max_questions: int = 72) -> FastAPI:
    app = FastAPI(title="jevviz")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["POST", "GET"], allow_headers=["*"])
    con = _connection(str(Path(db_path).resolve()))
    judge = backend or make_backend()
    cache = Cache(cache_path) if cache_path else None

    @app.get("/health")
    def health() -> dict:
        return {"simulated": judge.simulated, "model": judge.name}

    @app.post("/run")
    async def run(req: RunRequest) -> StreamingResponse:
        async def stream() -> AsyncIterator[bytes]:
            try:
                sql, intents = extract_viz(req.sql)
            except VizSyntaxError as exc:
                yield _line({"type": "error", "stage": "parse", "message": str(exc)})
                return
            yield _line({"type": "parsed", "sql": sql, "intents": intents})
            t0 = time.perf_counter()
            try:
                result = run_query(con, sql)
            except QueryError as exc:
                yield _line({"type": "error", "stage": "query", "message": str(exc)})
                return
            rows = [dict(zip(result.columns, row)) for row in result.rows]
            yield _line({"type": "result", "columns": result.columns, "rows": rows, "row_count": result.row_count,
                         "truncated": result.truncated, "ms": {"query": round((time.perf_counter() - t0) * 1000, 1)}})
            if intents is None:
                return
            try:
                out = await visualize(sql, result, intents, judge, cache, max_questions)
            except Exception as exc:  # noqa: BLE001 - any pipeline failure must become an error event, not a silently truncated stream
                # The result event has already been sent, so the table stays on
                # screen (F4): an unguarded pipeline exception must not silently
                # truncate the NDJSON stream with no error event.
                yield _line({"type": "error", "stage": "jev", "message": f"{type(exc).__name__}: {exc}"})
                return
            yield _line({"type": "spec", "spec": out.spec, "panels": out.panels, "ms": out.ms,
                         "usage": {"input_tokens": out.input_tokens, "usd": out.usd},
                         "scored": out.scored, "cache": out.cache, "simulated": out.simulated})
            if out.error:
                yield _line({"type": "error", "stage": "jev", "message": out.error})

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    return app


if not os.environ.get("DOTENV_DISABLE"):
    load_dotenv()
app = create_app(os.environ.get("JEVVIZ_DB", "jevviz.duckdb"), cache_path=".jev_cache.sqlite",
                 max_questions=int(os.environ.get("JEVVIZ_MAX_QUESTIONS", "72"))) \
    if Path(os.environ.get("JEVVIZ_DB", "jevviz.duckdb")).exists() else None
