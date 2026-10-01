#!/usr/bin/env bash
# Typewriter runner for the screen recording. A keypress advances each beat.
# Captions, a title card and an end card are built in, so the video only needs trimming.
#
# Usage: scripts/record.sh [--cold] [--notebook] [--results] [--no-production] [--no-captions]
#   --cold           forget this mode's judgments for the four tests before beat 4, so the
#                    semantic build is a real cold run (a live cold run re-bills ~1,000 states)
#   --notebook       beats 4 and 7 print how to run the bundle job instead of running dbt locally
#                    (beat 1 still runs dbt locally; this script never deploys or runs the bundle;
#                    --cold is ignored)
#   --results        like --notebook, but the job runs with action=results: it shows the latest
#                    logged live run (numbers, the docs/eval-results.md entry, failing rows) and
#                    runs no dbt and makes no Jev call, so nothing is judged on camera
#   --no-production  skip beat 7 (live mode only; it is always skipped in demo mode)
#   --no-captions    no title card, captions or end card
#
# LIVE by default (Jev calls are billed by TypeSafe). The smoke test is demo mode only, and every
# number it prints is SIMULATED and never a result:
#   yes '' | JEV_MODE=demo TYPE_DELAY=0 scripts/record.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$ROOT/.venv/bin/activate"
COLD=0
NOTEBOOK=0
RESULTS=0
PRODUCTION=1
CAPTIONS=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cold) COLD=1; shift ;;
    --notebook) NOTEBOOK=1; shift ;;
    --results) NOTEBOOK=1; RESULTS=1; shift ;;
    --no-production) PRODUCTION=0; shift ;;
    --no-captions) CAPTIONS=0; shift ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done
MODE="${JEV_MODE:-live}"
case "$MODE" in
  live | demo) export JEV_MODE="$MODE" ;;
  *) echo "JEV_MODE must be live or demo, got '$MODE'" >&2; exit 2 ;;
esac
[[ $MODE == demo ]] && PRODUCTION=0
if [[ $NOTEBOOK == 1 && $COLD == 1 ]]; then
  echo "--cold is ignored with --notebook (the preflight does not run); to start cold, clear" \
    "this mode's judgments for the four tests before recording." >&2
  COLD=0
fi
TYPE_DELAY="${TYPE_DELAY:-0.03}"
export DBT_SEND_ANONYMOUS_USAGE_STATS=false
PROD_WAREHOUSE="${JEV_PROD_WAREHOUSE:-jev-demo-5-prod}"

# dbt always runs through scripts/dbtw.py: it adds --profiles-dir . --target dev and a short-lived
# token from the Databricks CLI profile, and keeps the seed surname "Null" as text. The typed
# command stays the short, readable `dbt ...`.
dbt() { python "$ROOT/scripts/dbtw.py" "$@"; }

if [[ $RESULTS == 1 ]]; then
  echo "results only: no Jev calls (the notebook job shows the logged live runs)." >&2
elif [[ $MODE == live ]]; then
  echo "LIVE mode: this run calls Jev (TypeSafe billing). Ctrl-C now to stop." >&2
else
  echo "SIMULATED (demo mode): smoke test only, none of this is a result." >&2
fi

# Preflight (not recorded): fresh models, standard tests and the regex baselines for the scorecard.
# Nothing is judged here (the jev_expect tests are excluded); --cold forgets this mode's judgments
# from earlier runs so beat 4 judges every state on camera.
# stdout is silenced but stderr is not, so a broken build still shows and fails the script.
if [[ $NOTEBOOK == 0 ]]; then
  dbt seed --quiet >/dev/null
  dbt build --exclude tag:semantic --quiet >/dev/null
  if [[ $COLD == 1 ]]; then
    python - "$MODE" <<'PY'
import sys

sys.path.insert(0, "scripts")
import score
from jevdbx.databricks import Sql

res = Sql().run(score.fresh_sql(sys.argv[1], list(score.TESTS)))
sys.exit(0 if res.state == "SUCCEEDED" else f"--cold failed: {res.error}")
PY
  fi
fi

type_cmd() {
  printf '\033[1;32m❯\033[0m '
  local s="$1"
  for ((i = 0; i < ${#s}; i++)); do printf '%s' "${s:i:1}"; sleep "$TYPE_DELAY"; done
  printf '\n'
}
caption() {
  [[ $CAPTIONS == 1 ]] || return 0
  printf '\n\033[1;30;43m  %s  \033[0m\n' "$1"
}
beat() {
  read -rsn1
  clear 2>/dev/null || true
  type_cmd "$1"
  eval "$1" || true
  caption "$2"
}
# A dbt beat that runs inside Databricks (--notebook): show the command, do not run or deploy it.
notebook_beat() {
  local selection="$1" cap="$2" run
  if [[ $RESULTS == 1 ]]; then
    # results mode reads the ledger on the job's SQL warehouse (default: the dev warehouse, so no
    # warehouse parameter): no dbt, no Jev call
    run="databricks bundle run jev_semantic_tests --params action=results,selection=$selection"
  else
    run="databricks bundle run jev_semantic_tests --params mode=$MODE,selection=$selection"
    # the job's warehouse parameter defaults to the dev warehouse
    [[ $selection == production ]] && run="$run,warehouse=$PROD_WAREHOUSE"
  fi
  read -rsn1
  clear 2>/dev/null || true
  type_cmd "$run"
  printf '\n  Runs inside Databricks, as the serverless notebook job jev_semantic_tests.\n'
  printf '  Once per workspace: databricks bundle deploy   (creates the job; not done here)\n'
  if [[ $RESULTS == 1 ]]; then
    printf '  Open the run page: the logged LIVE run, its docs/eval-results.md entry, the failing rows.\n'
    printf '  No dbt runs and no Jev call is made.\n'
  else
    printf '  Open the run page: the Summary and the failing-rows cells carry %s output.\n' \
      "$([[ $MODE == live ]] && echo LIVE || echo SIMULATED)"
  fi
  caption "$cap"
}
card() {
  clear 2>/dev/null || true
  printf '\n\n\n'
  printf '  \033[1m%s\033[0m\n\n' "$1"
  shift
  for line in "$@"; do printf '  %s\n' "$line"; done
}

if [[ $CAPTIONS == 1 ]]; then
  if [[ $MODE == demo ]]; then
    card "SIMULATED: smoke test, not a result." \
      "Demo mode uses the hash-noise function noul_pack_demo, not Jev."
    read -rsn1
  fi
  card "dbt tests, written as sentences. Now on Databricks." \
    "Four checks your usual dbt tests can't do, judged by Jev (TypeSafe)." \
    "Jev is a Unity Catalog function; the key never leaves Databricks." \
    "Scored against 75 planted bad rows and a hand-written regex baseline."
else
  clear 2>/dev/null || true
fi

# Beat 1. The standard build and tests on Databricks. The judging post-hook only judges when the
# jev_expect tests are selected, so this build (which excludes them) makes no Jev call.
beat "dbt build --exclude tag:semantic tag:baseline" \
  "Same project. Now on Databricks."
# Beat 2
beat "python scripts/show.py tests" \
  "Same sentences."
# Beat 3
beat "python scripts/show.py function" \
  "Jev is a governed function; the key never leaves Databricks."
# Beat 4
if [[ $NOTEBOOK == 1 ]]; then
  notebook_beat yardstick "Structurally valid. Still wrong, or leaking PII."
else
  beat "dbt build --select +tag:semantic" \
    "Structurally valid. Still wrong, or leaking PII."
fi
# Beat 5
beat "python scripts/show.py rows" \
  "Every flagged row comes with a probability."
# Beat 6
beat "python scripts/show.py score" \
  "Jev vs. what you'd hand-write in regex."
beat "python scripts/score.py" \
  "And next to demo 04's logged numbers."
# Beat 7: 50,000 real reviews (live mode only). First the logged production entry from
# docs/eval-results.md, verbatim: its numbers (planted flips, audited precision, cost, throughput)
# are the billed runs'. Then a live rerun on the production warehouse, shown only for its 0
# requests: everything is already judged, so its own cost line is $0 and is not the run's cost.
# With --results there is no live rerun: the notebook job (action=results) shows the logged runs
# that judged the rows (states, requests, cost) instead.
if [[ $PRODUCTION == 1 ]]; then
  # The numbers are the last logged production entry's (docs/eval-results.md); the entry shows the
  # raw gate FAIL, so the caption names it. Update both together if a new production run is logged.
  beat "python scripts/show.py production" \
    "50,000 real reviews: recall 0.84, just under the 0.85 gate; audited precision 0.94."
  export JEV_WAREHOUSE="$PROD_WAREHOUSE"
  if [[ $RESULTS == 1 ]]; then
    # --results: the logged runs (states, requests, cost), not a rerun
    notebook_beat production "The logged production runs: states, requests, cost."
  elif [[ $NOTEBOOK == 1 ]]; then
    notebook_beat production "Rerun: nothing new to judge. 0 requests."
  else
    beat "dbt build --vars '{production: true, jev_max_concurrency: 2}' --select +tag:production tag:production_baseline" \
      "Rerun: nothing new to judge. 0 requests."
  fi
fi
read -rsn1
if [[ $CAPTIONS == 1 ]]; then
  card "Code, data and the full eval log:" "github.com/DataGobes/jev-demos"
  read -rsn1
fi
