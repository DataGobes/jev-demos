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


def test_beat7_caption_numbers_are_the_last_logged_production_entry():
    caption = re.search(r'"50,000 real reviews: recall ([\d.]+), just under the ([\d.]+) gate; '
                        r'audited precision ([\d.]+)\."', SCRIPT.read_text())
    assert caption, "beat 7 caption not found"
    log = (ROOT / "docs" / "eval-results.md").read_text()
    last = log[log.rindex("· production live/"):]
    logged = re.search(r"Jev: recall ([\d.]+) on [\d,]+ planted flips · raw precision [\d.]+ · "
                       r"audited precision ([\d.]+)", last)
    assert logged, "last production entry has no audited precision"
    assert (caption[1], caption[3]) == (logged[1], logged[2])
    assert "Gate: FAIL" in last and float(caption[1]) < float(caption[2])


def test_record_script_has_no_workspace_details():
    text = SCRIPT.read_text()
    assert not re.search(r"https?://\S*(databricks|azure)", text)
    assert not re.search(r"\b[0-9a-f]{16}\b", text)


def _notebook_beat(selection: str, results: int = 0) -> str:
    """Run record.sh's notebook_beat function alone (stubs for typing, captions and clear)."""
    script = (
        "type_cmd() { echo \"CMD: $1\"; }\ncaption() { :; }\nclear() { :; }\n"
        f"MODE=live; PROD_WAREHOUSE=prod-wh; RESULTS={results}\n"
        + subprocess.run(["sed", "-n", "/^notebook_beat()/,/^}/p", str(SCRIPT)],
                         capture_output=True, text=True, check=True).stdout
        + f"\nnotebook_beat {selection} cap <<< x\n"
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout


def test_notebook_production_beat_names_the_production_warehouse():
    out = _notebook_beat("production")
    cmd = next(ln for ln in out.splitlines() if ln.startswith("CMD:"))
    assert "selection=production" in cmd and "warehouse=prod-wh" in cmd


def test_notebook_yardstick_beat_uses_the_job_default_warehouse():
    cmd = next(ln for ln in _notebook_beat("yardstick").splitlines() if ln.startswith("CMD:"))
    assert "selection=yardstick" in cmd and "warehouse=" not in cmd


def test_beat7_shows_the_logged_production_entry_then_the_rerun():
    # F6: the rerun is fully cached ($0), so cost and throughput come from the logged entry
    # (docs/eval-results.md); the live rerun is shown only for its 0 requests.
    text = SCRIPT.read_text()
    beat7 = text.split("# Beat 7", 1)[1]
    assert "score.py --production" not in beat7
    logged = beat7.index("python scripts/show.py production")
    rerun = beat7.index("dbt build --vars '{production: true, jev_max_concurrency: 2}'")
    assert logged < rerun
    assert "0 requests" in beat7[rerun:]
    assert "logged" in beat7[logged:rerun]


def test_results_flag_makes_the_notebook_beats_show_the_logged_run_without_judging():
    assert "--results" in SCRIPT.read_text()
    cmd = next(ln for ln in _notebook_beat("yardstick", 1).splitlines() if ln.startswith("CMD:"))
    assert "action=results" in cmd and "selection=yardstick" in cmd and "mode=" not in cmd
    prod = next(ln for ln in _notebook_beat("production", 1).splitlines() if ln.startswith("CMD:"))
    assert "action=results" in prod and "warehouse=" not in prod  # results need no warehouse
    plain = next(ln for ln in _notebook_beat("yardstick").splitlines() if ln.startswith("CMD:"))
    assert "action=results" not in plain and "mode=live" in plain


def _top_level_block(start_pattern: str) -> str:
    """The script's top-level (unindented) `if ... fi` block that starts at `start_pattern`."""
    return subprocess.run(
        ["sed", "-n", f"/^{start_pattern}/,/^fi$/p", str(SCRIPT)],
        capture_output=True, text=True, check=True).stdout


def _run_beat7(results: int, notebook: int) -> str:
    script = (
        'beat() { echo "BEAT: $1 | $2"; }\n'
        'notebook_beat() { echo "NOTEBOOK: $1 | $2"; }\n'
        f"PRODUCTION=1; PROD_WAREHOUSE=w; RESULTS={results}; NOTEBOOK={notebook}\n"
        + _top_level_block(r"if \[\[ \$PRODUCTION == 1 \]\]; then")
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          check=True).stdout


def test_results_beat7_has_its_own_caption_not_the_rerun_one():
    out = _run_beat7(results=1, notebook=1)
    assert "NOTEBOOK: production | The logged production runs: states, requests, cost." in out
    assert "Rerun" not in out and "0 requests" not in out
    # without --results the rerun caption is unchanged
    assert "Rerun: nothing new to judge. 0 requests." in _run_beat7(results=0, notebook=1)
    assert "Rerun: nothing new to judge. 0 requests." in _run_beat7(results=0, notebook=0)


def _banner(results: int, mode: str) -> str:
    script = f"RESULTS={results}; MODE={mode}\n" + _top_level_block(r"if \[\[ \$RESULTS == 1 \]\]")
    res = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    return res.stderr


def test_results_banner_says_no_jev_calls_not_live_billing():
    err = _banner(1, "live")
    assert "results only: no Jev calls" in err
    assert "LIVE" not in err and "TypeSafe billing" not in err
    assert "LIVE mode: this run calls Jev" in _banner(0, "live")
    assert "SIMULATED (demo mode)" in _banner(0, "demo")
