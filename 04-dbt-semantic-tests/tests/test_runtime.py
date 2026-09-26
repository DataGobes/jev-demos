import json
import time

import pytest

from jevdbt.questions import Question
from jevdbt.runtime import (
    Settings,
    build_runtime,
    effective_pack_style,
    effective_rpm,
    resolve_settings,
)


def test_defaults_auto_without_key_is_demo():
    s = resolve_settings({}, {})
    assert s == Settings(mode="demo", model="jev-latest", pack=1, concurrency=32, rpm=1200,
                         cache_path=".jev_cache.sqlite")


def test_auto_with_key_is_live():
    assert resolve_settings({}, {"TYPESAFE_API_KEY": "k"}).mode == "live"


def test_env_overrides_config():
    s = resolve_settings(
        {"mode": "live", "pack": 4, "cache_path": "a.sqlite"},
        {"JEV_MODE": "demo", "JEV_PACK": "8", "JEV_NO_CACHE": "1"},
    )
    assert (s.mode, s.pack, s.cache_path) == ("demo", 8, None)


def test_pack_style_defaults_to_nested_and_env_overrides():
    assert resolve_settings({}, {}).pack_style == "nested"
    s = resolve_settings({"pack_style": "inline"}, {"JEV_PACK_STYLE": "rows"})
    assert s.pack_style == "rows"
    with pytest.raises(ValueError, match="pack_style"):
        resolve_settings({"pack_style": "sideways"}, {})


def test_pack_one_is_always_the_single_layout():
    assert effective_pack_style(Settings("demo", "jev-latest", 1, 4, 0, None, "nested")) == "single"
    assert effective_pack_style(Settings("demo", "jev-latest", 8, 4, 0, None, "nested")) == "nested"


def test_live_without_key_raises():
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        resolve_settings({"mode": "live"}, {})


def test_bad_mode_raises():
    with pytest.raises(ValueError):
        resolve_settings({"mode": "maybe"}, {})


def test_runtime_stats_json(tmp_path):
    rt = build_runtime(Settings("demo", "jev-latest", 1, 4, 0, str(tmp_path / "c.sqlite")))
    data = json.loads(rt.stats_json())
    assert data["judgments"] == 0 and data["simulated"] is True
    assert data["summary"].startswith("Jev · 0 judgments")
    assert "SIMULATED demo pack=1" in data["summary"]
    rt.scorer.close()


def test_demo_mode_does_not_wait_on_configured_rpm(tmp_path):
    # rpm=30 (1 request every 2s) would make 3 sequential requests take >= 4s if the pacer
    # were active; demo mode has no backend to protect, so it must ignore settings.rpm.
    rt = build_runtime(Settings("demo", "jev-latest", 1, 4, 30, str(tmp_path / "c.sqlite")))
    start = time.monotonic()
    rt.scorer.score_many([f'{{"s":{i}}}' for i in range(3)], Question("x"))
    elapsed = time.monotonic() - start
    rt.scorer.close()
    assert elapsed < 1.0


def test_effective_rpm_demo_is_always_zero():
    assert effective_rpm(Settings("demo", "jev-latest", 1, 4, 1200, None)) == 0


def test_effective_rpm_live_uses_configured_value():
    assert effective_rpm(Settings("live", "jev-latest", 1, 4, 5, None)) == 5
