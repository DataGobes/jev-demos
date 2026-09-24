#!/usr/bin/env bash
# Typewriter runner for the screen recording. Keypress advances each beat.
# Usage: scripts/record.sh [--cold] [--pack N]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/jaffle_shop"
source "$ROOT/.venv/bin/activate"
COLD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cold) COLD=1; shift ;;
    --pack) export JEV_PACK="$2"; shift 2 ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done
TYPE_DELAY="${TYPE_DELAY:-0.03}"
export JEV_PROGRESS=1

# Preflight (not recorded): fresh models + baseline tables for the scorecard.
# stdout is silenced but stderr is not, so a broken build still shows and fails the script.
dbt build --profiles-dir . --exclude tag:semantic --quiet >/dev/null
[[ $COLD == 1 ]] && rm -f .jev_cache.sqlite

type_cmd() {
  printf '\033[1;32m❯\033[0m '
  local s="$1"
  for ((i = 0; i < ${#s}; i++)); do printf '%s' "${s:i:1}"; sleep "$TYPE_DELAY"; done
  printf '\n'
}
beat() {
  read -rsn1
  clear
  type_cmd "$1"
  eval "$1" || true
  echo
}

clear
beat "dbt build --profiles-dir . --exclude tag:semantic tag:baseline"
beat "python ../scripts/show.py tests"
beat "dbt test --profiles-dir . --select tag:semantic"
beat "python ../scripts/show.py rows"
beat "python ../scripts/show.py score"
beat "dbt test --profiles-dir . --select tag:semantic"
read -rsn1
