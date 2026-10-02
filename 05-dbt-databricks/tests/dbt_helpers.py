import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
JAFFLE = ROOT / "jaffle_shop"


def dbt(*args, env=None) -> subprocess.CompletedProcess:
    """Run dbt offline (DuckDB `render` target) in jaffle_shop/. JEV_MODE comes only from `env`."""
    full_env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false", **(env or {})}
    if env is None or "JEV_MODE" not in env:
        full_env.pop("JEV_MODE", None)
    return subprocess.run(
        ["uv", "run", "dbt", *args, "--profiles-dir", ".", "--target", "render"],
        cwd=JAFFLE, capture_output=True, text=True, env=full_env, timeout=300,
    )


def render(macro: str, args: dict, env=None) -> str:
    """Run a jev_render_* macro and return what it printed between the BEGIN/END markers."""
    out = dbt("run-operation", macro, "--args", json.dumps(args), env=env)
    m = re.search(r"-- BEGIN\n(.*?)\n-- END", out.stdout, re.S)
    assert m, f"no output from {macro}:\n{out.stdout}\n{out.stderr}"
    return m.group(1)
