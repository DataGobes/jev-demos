# Jev `VISUALIZE`

## What this is

A SQL query ends in a natural-language `VISUALIZE '<intent>'` clause, and
TypeSafe's Jev model decides which chart (or dashboard) answers it, rendered
in well under a second. For example:

```sql
SELECT region, month, sum(revenue) AS revenue
FROM orders GROUP BY ALL
VISUALIZE 'how are regions trending'
```

## How it works

Core principle: **code proposes, Jev selects, code assembles.** Jev is a
System One model — it returns typed judgments (probabilities), not text or
arithmetic — so the backend enumerates only *valid* chart candidates, asks
Jev to score their relevance to the intent, and code ranks the results and
builds the render spec. `POST /run` streams each stage as it completes, as
NDJSON:

1. `extract_viz(sql)` — split the trailing `VISUALIZE '...'` clause(s) off the SQL.
2. DuckDB executes the (clause-free) SQL, read-only.
3. `profile(result)` — classify each column (measure, dimension, time, identifier, ...).
4. `enumerate_candidates(profile)` — each `@rule` proposes charts it can validly render for this shape.
5. Jev scores every (candidate × intent) pair in one batched judgment.
6. `rank` picks the winner (and alternates) per intent; `spec.py` assembles the flat json-render spec.

A viz failure never hides the data: the table from the `result` event stays
on screen even if the `spec` stage errors. The same principle holds one layer
up in the frontend — if a chosen chart's Vega-Lite spec fails to render,
`Chart` shows an inline "Chart failed to render" alert instead of blanking
the panel; the underlying data is never hidden. The frontend renders the
backend's flat json-render spec through `Renderer`, which (in the installed
json-render 0.21.0) requires an `ActionProvider` ancestor even though this
catalog declares no actions — see `web/README.md` for the full rationale.

## Run it

```bash
uv sync
uv run python -m jevviz.data jevviz.duckdb
uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000
cd web && npm install && npm run dev      # second terminal, then open http://localhost:5173
```

## Demo mode

Without a `TYPESAFE_API_KEY`, the backend falls back to a deterministic
offline stand-in (`DemoBackend`) and the UI shows a visible `SIMULATED`
badge. Demo-mode output is for exploring the UI and running tests offline —
never present simulated scores or chart picks as real Jev judgments.

To run the backend in simulated mode on purpose (e.g. to reproduce the demo
without touching the live API even if `.env` holds a key):

```bash
env -u TYPESAFE_API_KEY DOTENV_DISABLE=1 uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000
```

## Tests

```bash
uv run pytest -q              # backend unit/integration tests, offline
cd web && npx vitest run      # frontend unit tests
cd web && npm run e2e         # Playwright smoke test, offline/simulated end-to-end
uv run python -m jevviz.eval  # live golden-set eval — needs TYPESAFE_API_KEY, costs real requests
```

## Results

**Question-count probe** (`docs/probe-results.md`, 2026-09-21, `jev-latest`,
typesafe-sdk 0.7.1): batches of 24, 48, and 72 Score questions in one request
all answered every question with no error in 3/3 runs, at a flat median
latency (267 / 277 / 306 ms); a batch of 144 also answered everything but
latency roughly doubled (625 ms). The owner chose **72 questions per
request**, with chunks over that size fired concurrently.

**Golden-set eval** (`docs/eval-results.md`, 2026-09-21, `jev-latest`,
typesafe-sdk 0.7.1, 20-case golden set — 10 seed cases from the plan plus 10
drafted by the assistant): Jev top-1 **90–95%** across two live runs (95%, then
90% after the final-review fixes), top-3 **100%**, vs. a rules-only ("first
valid candidate") baseline of top-1 **35%**. Every miss was a pie chosen over an
accepted bar of the same columns, within ~0.1 of each other. The first run,
on the 10 seed cases alone, was top-1 80% / top-3 100% / baseline 40%. The
set is small and half of it was drafted by the same model family that built
the system, the rules-only baseline is weak on position ties, and near-tie
scores move by roughly ±0.01 between live runs — so treat these numbers as
"the approach works," not as a rigorous benchmark. Ranking thresholds are
unchanged from the design defaults: `STRONG` 0.6, `WEAK` 0.3, `ID_NOUL` 0.5.

**End-to-end latency** (live, 2026-09-21, localhost, 5–13 candidates): first
query after server start 671 ms to the `spec` event (cold connection); later
queries 240–414 ms, including a 3-intent dashboard (414 ms, 7.4k input tokens);
a cache hit 7 ms. Vega render measured in the browser: 13–42 ms.

## Adding a chart type

Write one `@rule` function that takes a `Profile` and returns zero or more
`Candidate`s, each with a description in the fixed grammar **"form, measure,
breakdown, what it reveals"** (e.g. "line chart of revenue over order_month,
broken down by region, reveals how each region trends over time"). Register
it in `rules/`. Nothing else changes — the candidate is automatically
enumerated, capped, scored by Jev, ranked, and rendered like every other
chart kind.

## Limits

- No generated titles or captions — every title is a template.
- Vega-Lite chart types only (no Sankey, network, or treemap).
- Localhost only — no auth, no multi-user, no deployment story.
- Ranking thresholds (`STRONG`, `WEAK`, `ID_NOUL`) were tuned on a small
  (20-case) golden set; revisit if it's extended.
- `run_query` enforces a 10-second per-statement timeout and a 5,000-row cap,
  and makes duplicate result column names unique (`id`, `id_2`, ...) so no
  column silently overwrites another.
- The seeded dataset generator (`jevviz.data`, `n_orders=50_000` by default)
  produces roughly 31,000 `orders` rows — most candidate order IDs are
  skipped by the generator's planted seasonality/region filters, so the row
  count is well under `n_orders`.
