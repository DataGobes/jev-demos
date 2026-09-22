# CLAUDE.md

Jev VISUALIZE demo: a SQL `VISUALIZE '<intent>'` clause where TypeSafe's Jev model ranks code-generated chart candidates. Spec: `docs/superpowers/specs/2026-09-21-jev-visualize-design.md`.

## Commands
- Backend: `uv sync`, `uv run python -m jevviz.data jevviz.duckdb`, `uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000`
- Backend, simulated on purpose (no live calls even with a key in `.env`): `env -u TYPESAFE_API_KEY DOTENV_DISABLE=1 uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000`
- Frontend: `cd web && npm install && npm run dev`
- Tests: `uv run pytest -q` · `uv run ruff check` · `cd web && npx vitest run` · `cd web && npm run e2e`
- Live eval (needs key): `uv run python -m jevviz.eval jevviz.duckdb`
- Recording, unattended: open `http://localhost:5173/?autoplay&scale=1.25` — pastes each example, types its `VISUALIZE` line, runs, dwells, loops; one cycle is ~43 s warm / ~48 s cold. Delete `.jev_cache.sqlite` first so the timing bar shows real Jev latency instead of `cache: hit`. Params `type`, `pause`, `dwell`, `extra`, `lead`, `scale` (see `web/src/autoplay.ts`); `skipInLoop` in `examples.ts` keeps an example out.

## Rules
- Never read, print or log `.env` or `TYPESAFE_API_KEY`. The key stays server-side.
- Jev never counts, compares numbers or writes text. Numeric guards live in `profile.py` and `rules/`; titles are templates.
- Rank by `P(level >= 2)`; never use the interpolated Score value.
- Every rule emits only valid charts; `tests/test_vega_valid.py` must stay green. Never loosen it.
- Demo mode must always show the `SIMULATED` badge. Do not report simulated numbers as real.
- The backend emits only `Grid`, `Panel`, `Chart`, `Kpi`, `Table`. No json-render `experimental_*` APIs.
- A viz failure never hides the data: the table stays on screen.
- Changing a rule description or `LEVELS` wording changes model behaviour: re-run the live eval and update `docs/eval-results.md`.
