import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "record.sh"


def test_record_script_is_valid_bash():
    res = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_record_script_is_executable_and_runs_dbt_only_through_dbtw():
    assert SCRIPT.stat().st_mode & 0o111
    text = SCRIPT.read_text()
    assert 'python "$ROOT/scripts/dbtw.py"' in text
    # no bare dbt binary: every `dbt` call is the shell function that wraps dbtw.py
    assert not re.search(r"(uv run|\bpython -m) dbt\b", text)


def test_record_script_never_deploys_or_runs_the_bundle():
    lines = [ln.strip() for ln in SCRIPT.read_text().splitlines()]
    executed = [ln for ln in lines if re.match(r"(databricks|eval)\b", ln)]
    assert not [ln for ln in executed if "bundle" in ln]
    # --notebook only prints (inside a printf and the typed text); nothing runs the bundle
    assert "--notebook" in SCRIPT.read_text()


def test_record_script_has_no_workspace_details():
    text = SCRIPT.read_text()
    assert not re.search(r"https?://\S*(databricks|azure)", text)
    assert not re.search(r"\b[0-9a-f]{16}\b", text)
