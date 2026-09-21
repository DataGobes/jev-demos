"""Offline safety test for the `DOTENV_DISABLE` opt-out in `jevviz.api`.

`jevviz.api`'s module-level `app` calls `load_dotenv()` at import time, which
would read `.env` and pick up a real `TYPESAFE_API_KEY` if present — turning
every import of the module into a paid, live call. `DOTENV_DISABLE=1` skips
that call.

This must run in a *subprocess* with a cleaned environment: the test process
itself must never import `jevviz.api` in a way that could load `.env`, and
must never read or print the key. The subprocess script below only asserts
that `/health` reports `simulated: true`; it never touches `.env` or
`TYPESAFE_API_KEY` directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = """
import json
import os
import sys

from jevviz.data import generate

db_path = sys.argv[1]
generate(db_path, n_orders=200)
os.environ["JEVVIZ_DB"] = db_path

from fastapi.testclient import TestClient
from jevviz.api import app

client = TestClient(app)
print(json.dumps(client.get("/health").json()))
"""


def test_dotenv_disable_keeps_module_level_app_simulated(tmp_path):
    db_path = tmp_path / "dotenv_disable.duckdb"

    # Cleaned environment: no TYPESAFE_API_KEY, DOTENV_DISABLE=1. Run with
    # cwd=REPO_ROOT (where the real .env lives) so this only proves anything
    # if DOTENV_DISABLE actually stops `.env` from being read.
    env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    env["DOTENV_DISABLE"] = "1"

    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(db_path)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"simulated": True, "model": "demo"}
