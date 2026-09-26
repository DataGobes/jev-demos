# CLAUDE.md

Research spike + fallback tool: can a dbt v2 native check call an LLM judge (Jev) to flag
column descriptions that don't match the column? Answer and evidence: `FINDINGS.md`.

## Commands
- Sync: `uv sync`
- Tests: `uv run pytest -q` · lint: `uv run ruff check`
- Fallback CLI: `uv run desc-judge --info-schema project/target/info_schema/v1 [--state <baseline>] [--format json]`
- dbt (needs dbt v2 on PATH): `cd project && dbt compile --profiles-dir . --generate-info-schema && dbt check --profiles-dir .`
- Probes (DuckDB 1.5.4 via ADBC, no dbt): `uv run python probes/probe_adbc.py`, `uv run python probes/probe_ext.py`

## Rules
- The judge is `MockJudge`, a keyword rule. Its verdicts are never a result about Jev and never
  go into a README, changelog or post as one.
- Never call a real LLM or external API from tests or probes. `probe_ext.py` talks only to a
  mock judge on 127.0.0.1.
- The mock judge exists three times and must agree: `src/desc_judge/judges.py`,
  `project/macros/mock_judge.sql`, `project/checks/description_matches_column_macro.sql`.
  Tests enforce parity; change all three together.
- `project/models/schema.yml` descriptions marked WRONG / SUBTLE are the test's answer key.
  Don't "fix" them.
- A judge's `id` is part of the cache key. Bump it whenever a verdict could change for the
  same input (model, prompt, threshold).
