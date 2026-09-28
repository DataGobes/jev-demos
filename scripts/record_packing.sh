#!/usr/bin/env bash
# Typewriter runner for the packing recording. Keypress advances each beat:
#   1. a text recap of the logged live one-row-per-request run (not re-run: it takes ~55 s),
#   2. the same four semantic tests, live and cold (cache off), with many rows per request,
#   3. both side by side, from the logged run and the run just made.
# Usage: scripts/record_packing.sh [--pack N] [--no-captions]      (default pack: 64)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/jaffle_shop"
source "$ROOT/.venv/bin/activate"
PACK=64
CAPTIONS=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pack) PACK="$2"; shift 2 ;;
    --no-captions) CAPTIONS=0; shift ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done
TYPE_DELAY="${TYPE_DELAY:-0.03}"
export JEV_PROGRESS=1
export JEV_NO_CACHE=1

# Preflight (not recorded): fresh models. stdout is silenced but stderr is not, so a broken
# build still shows and fails the script.
dbt build --profiles-dir . --exclude tag:semantic --quiet >/dev/null

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
# beat "<typed command>" "<caption>" [<hidden command run afterwards>]
beat() {
  read -rsn1
  clear
  type_cmd "$1"
  eval "$1" || true
  [[ -n "${3:-}" ]] && eval "$3"
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
  card "An AI judgment on every row. Not a request for every row." \
    "Four semantic dbt tests, 1,300 rows, judged by Jev (TypeSafe)." \
    "Before and after batching the rows. Live, no cache."
else
  clear
fi
RECAP="$(python ../scripts/packing_compare.py recap)"
read -rsn1
card "Last time: one request per row." \
  "$RECAP" \
  "" \
  "Same four tests, same 1,300 rows, live, no cache." \
  "(logged run, not re-run here: eval/pack_bench/single_p1_a.json)"
caption "Every row waited its turn."
beat "JEV_PACK=$PACK dbt test --profiles-dir . --select tag:semantic" \
  "$PACK rows per request. Same questions, same rows." \
  "python ../scripts/packing_compare.py save pack$PACK"
beat "python ../scripts/packing_compare.py show pack$PACK" \
  "Same answer key. A fraction of the calls."
read -rsn1
if [[ $CAPTIONS == 1 ]]; then
  card "The trick: each row rides inside its own question." \
    "Write-up, code and benchmark runs:" \
    "github.com/DataGobes/jev-demos  →  04-dbt-semantic-tests/docs/pack-layouts.md"
  read -rsn1
fi
