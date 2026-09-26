# CLAUDE.md

semsql: semantic SQL over DuckDB. Plain-English judgments (`jev_noul`, `jev_score`,
`jev_score_levels`, `jev_choice`) become typed columns, backed by the TypeSafe Jev API
or a deterministic offline demo backend.

## Commands

- `uv run pytest -q` — run all tests
- `uv run ruff check` — lint
- `uv run semsql gen --rows 10000` — load synthetic reviews
- `uv run semsql` — REPL; `uv run semsql -c "SQL"` — one-shot
- `uv run semsql eval-pack --sample 200 --pack 16` — pack=1 vs pack=K agreement (needs `TYPESAFE_API_KEY`)

## Architecture

```
cli.py -> udf.py -> engine.py (Scorer) -> backend.py (JevBackend | DemoBackend)
                        |-> cache.py (sqlite)
cli.py reads <- stats.py
questions.py (Question, rubrics.toml loader)   data.py (synthetic dataset)
```

## Rules

- `docs/plan.md` "Interfaces" section is the contract between modules — do not
  deviate from it without updating the plan first.
- Never print, log, or cache the `TYPESAFE_API_KEY` value.
- Demo mode (no API key) must always be visibly labeled `SIMULATED` — in the live
  panel and the REPL banner — never let a demo run look like a real one.
