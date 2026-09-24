"""Settings resolution and the per-process Runtime (scorer + stats) shared by all connections."""

from __future__ import annotations

import atexit
import json
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jevdbt.backend import make_backend
from jevdbt.cache import Cache
from jevdbt.scorer import Scorer
from jevdbt.stats import Stats, format_summary

_MODES = {"auto", "live", "demo"}


@dataclass(frozen=True)
class Settings:
    mode: str  # resolved: "live" | "demo"
    model: str
    pack: int
    concurrency: int
    rpm: int
    cache_path: str | None


def resolve_settings(config: Mapping[str, Any], env: Mapping[str, str]) -> Settings:
    mode = (env.get("JEV_MODE") or str(config.get("mode", "auto"))).lower()
    if mode not in _MODES:
        raise ValueError(f"jevdbt mode must be one of {sorted(_MODES)}, got {mode!r}")
    has_key = bool(env.get("TYPESAFE_API_KEY"))
    if mode == "auto":
        mode = "live" if has_key else "demo"
    if mode == "live" and not has_key:
        raise RuntimeError("JEV_MODE=live but TYPESAFE_API_KEY is not set")
    default_cache = config.get("cache_path", ".jev_cache.sqlite")
    cache_path: str | None = env.get("JEV_CACHE") or str(default_cache)
    if env.get("JEV_NO_CACHE") == "1":
        cache_path = None
    return Settings(
        mode=mode,
        model=str(config.get("model", "jev-latest")),
        pack=int(env.get("JEV_PACK") or config.get("pack", 1)),
        concurrency=int(config.get("concurrency", 32)),
        rpm=int(config.get("rpm", 1200)),
        cache_path=cache_path,
    )


class Runtime:
    def __init__(self, scorer: Scorer, stats: Stats, settings: Settings) -> None:
        self.scorer = scorer
        self.stats = stats
        self.settings = settings

    @property
    def simulated(self) -> bool:
        return self.scorer.backend.simulated

    def summary(self) -> str:
        return format_summary(
            self.stats.snapshot(),
            simulated=self.simulated,
            model=self.scorer.backend.name,
            pack=self.settings.pack,
        )

    def stats_json(self) -> str:
        snap = self.stats.snapshot()
        return json.dumps(
            {
                **snap.__dict__,
                "simulated": self.simulated,
                "model": self.scorer.backend.name,
                "pack": self.settings.pack,
                "summary": self.summary(),
            }
        )


def build_runtime(settings: Settings) -> Runtime:
    stats = Stats()
    cache = Cache(settings.cache_path) if settings.cache_path else None
    backend = make_backend(settings.mode, settings.model)
    scorer = Scorer(
        backend,
        stats,
        cache,
        pack=settings.pack,
        concurrency=settings.concurrency,
        rpm=settings.rpm,
    )
    return Runtime(scorer, stats, settings)


_runtime: Runtime | None = None
_runtime_lock = threading.Lock()


def get_runtime(config: Mapping[str, Any]) -> Runtime:
    """One Runtime per process: dbt opens a connection per thread; they share stats and cache."""
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            if os.environ.get("DOTENV_DISABLE") != "1":
                from dotenv import find_dotenv, load_dotenv

                load_dotenv(find_dotenv(usecwd=True))
            _runtime = build_runtime(resolve_settings(config, os.environ))
            atexit.register(_runtime.scorer.close)
        return _runtime
