#!/usr/bin/env bash
# Run every dbt step FINDINGS.md quotes, logging each command and its output to probes/logs/.
#
#   DBT=/path/to/dbt probes/run_dbt_evidence.sh
#
# DBT defaults to `dbt` on PATH. Checks need dbt's DuckDB ADBC driver: dbt downloads it on first
# use, and when that is impossible, point ADBC_DRIVER_PATH at a directory with a duckdb.toml
# driver manifest (see FINDINGS.md §0). Never calls an external API: the only judge is the mock
# on 127.0.0.1.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
LOGS="$HERE/logs"
DBT="${DBT:-dbt}"
mkdir -p "$LOGS"
cd "$ROOT/project"

run() {  # run <log name> <command...>: log the command line, then its output and exit code
  local name="$1"; shift
  {
    echo "\$ $*"
    "$@" 2>&1
    echo "[exit $?]"
  } | sed -E "s#$ROOT/##g; s#$HOME#~#g" > "$LOGS/$name.log"
  echo "== $name"; cat "$LOGS/$name.log"
}

rm -rf target logs desc_checks.duckdb

run 01_version        "$DBT" --version
run 02_parse          "$DBT" parse --profiles-dir .
run 03_check          "$DBT" check --profiles-dir .
run 04_compile_info   "$DBT" compile --profiles-dir . --generate-info-schema
run 05_info_files     ls -1 target/info_schema/v1
run 06_info_inventory uv run --project "$ROOT" python "$HERE/inventory.py" target/info_schema/v1
run 07_desc_judge     uv run --project "$ROOT" desc-judge --info-schema target/info_schema/v1 --no-cache

# Probe checks, with the mock judge listening on 127.0.0.1.
export HTTPFS_EXT
HTTPFS_EXT="$(uv run --project "$ROOT" python -c \
  'import duckdb_extension_httpfs as m, pathlib; print(next(pathlib.Path(m.__file__).parent.rglob("httpfs.duckdb_extension")))')"
PORT=8765
export MOCK_JUDGE_URL="http://127.0.0.1:$PORT/judge" MOCK_JUDGE_LOG="$LOGS/08_mock_judge_requests.log"
: > "$MOCK_JUDGE_LOG"
uv run --project "$ROOT" python "$HERE/mock_judge_server.py" "$PORT" 2>/dev/null &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
sleep 1
run 08_check_probes   env DESC_CHECKS_PROBES=true "$DBT" check --profiles-dir .
echo "== 08_mock_judge_requests"; cat "$MOCK_JUDGE_LOG"
