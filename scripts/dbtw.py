"""Run dbt in jaffle_shop/ authenticated with a short-lived token from the Databricks CLI profile.

    uv run python scripts/dbtw.py build --select +tag:semantic
    # -> dbt build --select +tag:semantic --profiles-dir . --target dev

The token and the environment are never printed.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from jevdbx.databricks import dbt_env

PROJECT_DIR = Path(__file__).resolve().parents[1] / "jaffle_shop"


def build_command(argv: list[str]) -> list[str]:
    """dbt arguments with `--profiles-dir .` and `--target dev` added unless already given."""
    args = list(argv)
    if not any(a == "--profiles-dir" or a.startswith("--profiles-dir=") for a in args):
        args += ["--profiles-dir", "."]
    if not any(a in ("--target", "-t") or a.startswith("--target=") for a in args):
        args += ["--target", "dev"]
    return args


def dbt_executable() -> list[str]:
    exe = shutil.which("dbt", path=str(Path(sys.executable).parent))
    return [exe] if exe else [sys.executable, "-c", "from dbt.cli.main import cli; cli()"]


def main(argv=None) -> int:
    args = build_command(sys.argv[1:] if argv is None else argv)
    env = {**os.environ, **dbt_env()}
    return subprocess.run([*dbt_executable(), *args], cwd=PROJECT_DIR, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
