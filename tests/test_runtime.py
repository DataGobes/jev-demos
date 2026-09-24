import json

import pytest

from jevdbt.runtime import Settings, build_runtime, resolve_settings


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
