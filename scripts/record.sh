#!/usr/bin/env bash
# Typewriter runner for the screen recording. Keypress advances each beat.
# Captions, a title card and an end card are built in, so the video only needs trimming.
# Usage: scripts/record.sh [--cold] [--pack N] [--no-captions]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/jaffle_shop"
source "$ROOT/.venv/bin/activate"
COLD=0
CAPTIONS=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cold) COLD=1; shift ;;
    --pack) export JEV_PACK="$2"; shift 2 ;;
    --no-captions) CAPTIONS=0; shift ;;
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
caption() {
  [[ $CAPTIONS == 1 ]] || return 0
  printf '\n\033[1;30;43m  %s  \033[0m\n' "$1"
}
beat() {
  read -rsn1
  clear
  type_cmd "$1"
  eval "$1" || true
  caption "$2"
}
card() {
  clear
  printf '\n\n\n'
  printf '  \033[1m%s\033[0m\n\n' "$1"
  shift
  for line in "$@"; do printf '  %s\n' "$line"; done
}

if [[ $CAPTIONS == 1 ]]; then
  card "dbt tests, written as sentences." \
    "Four checks your usual dbt tests can't do, judged by Jev (TypeSafe)." \
    "Scored against 75 planted bad rows and a hand-written regex baseline."
else
  clear
fi
beat "dbt build --profiles-dir . --exclude tag:semantic tag:baseline" \
  "Every standard dbt test passes. Ship it?"
beat "python ../scripts/show.py tests" \
  "Four more tests, written as plain English sentences."
beat "dbt test --profiles-dir . --select tag:semantic" \
  "Structurally valid. Still wrong, or leaking PII."
beat "python ../scripts/show.py rows" \
  "Every flagged row comes with a probability."
beat "python ../scripts/show.py score" \
  "Jev vs. what you'd hand-write in regex."
beat "dbt test --profiles-dir . --select tag:semantic" \
  "Rerun: fully cached, cheap enough for CI."
read -rsn1
if [[ $CAPTIONS == 1 ]]; then
  card "Code, data and the full eval log:" "github.com/DataGobes/jev-demos"
  read -rsn1
fi
