# CLAUDE.md

Demo 06: one dbt test, `jev_expect`, judged by Jev or by LLMs through `ai_query`
(`--vars '{judge: …}'`), on Banking77 triage, Abt-Buy duplicate pairs and
`samples.wanderbricks.reviews`. Spec: `docs/superpowers/specs/2026-10-01-jev-vs-ai-query-design.md`;
plan: `docs/superpowers/plans/2026-10-01-jev-vs-ai-query.md`. Demo 05 (`~/Projects/jev-demo-5`) is
read only.

## Commands
- Sync `uv sync` · tests `uv run pytest -q` · integration (SIMULATED, dev warehouse)
  `uv run pytest -m databricks -q` · lint `uv run ruff check`
- dbt only through `uv run python scripts/dbtw.py …` (runs in `bench/`)
- Platform DDL: `uv run python scripts/deploy.py` (print) · `--apply` (confirm-first the first time)
- Board: `uv run python scripts/show.py board` · live pass:
  `uv run python scripts/score.py --run --judge <judge> --scope <pilot|sample|full> --pass <n> --mode live --append`
- Pre-register (once, before the pilot): `uv run python scripts/score.py --preregister` · measured
  cost (usage lags ~2 h): `uv run python scripts/score.py --measure --append`

## Rules
- Never read/print/log `.env`, secrets, tokens or the TypeSafe key; never a PAT.
- No workspace host, warehouse id, storage account or tenant in a committed file.
- Confirm-first: live Jev runs, real `ai_query` calls, downloads, uploads, creating
  `jev_demo.bench` or its volume, first read of `system.serving.*`. Standing OK: other queries on the
  2X-Small warehouse `jev-demo-5`.
- SIMULATED output is never logged or quoted. Numbers come from logged live runs; estimates labelled.
- LLM cap $15 (enforced by `scripts/score.py`); prompts frozen after pre-registration: a change means
  rerunning every judge and logging before/after.
- `bench/macros/jev_question.sql` is the single place for question, prompt, state and key.
- Never edit keys, swap lists, family tables or baselines to make a judge win.
- git `user.email` is repo-local `info@datagobes.dev` (the global one is a client address).
