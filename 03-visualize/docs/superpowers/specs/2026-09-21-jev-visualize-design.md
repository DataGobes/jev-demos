# Jev VISUALIZE — design spec

Date: 2026-09-21
Status: approved design, pre-implementation
Predecessor: `~/Projects/jev-demo-2` (semantic SQL: `jev_noul()` etc. in DuckDB WHERE clauses)

## 1. Purpose

A web demo where a SQL query ends in a natural-language `VISUALIZE` clause and
TypeSafe's Jev model decides which chart (or dashboard) answers it, rendered in
well under a second.

```sql
SELECT region, month, sum(revenue) AS revenue
FROM orders GROUP BY ALL
VISUALIZE 'how are regions trending'
```

Core principle: **code proposes, Jev selects, code assembles.** Jev is a
System One model — it returns typed judgments (Choice / Noul / Score) with
probabilities and cannot generate text or reliably do arithmetic. So code
enumerates only *valid* panels, Jev scores their *relevance* to the intent, and
code ranks and builds the render spec. This mirrors the candidate-selection
pattern in Vercel Labs' json-render Jev integration and TypeSafe's
function-calling and fan-out docs.

### Success criteria

1. On a golden set of ~30 (query, intent, acceptable panels) triples, Jev top-1
   accuracy clearly beats a rules-only baseline (first valid candidate). If it
   does not, the project stops before any frontend is built.
2. End-to-end (run → chart painted) is visibly sub-second on the demo dataset,
   proven by a live timing bar, not asserted.
3. Everything except the eval and the probe runs offline in a clearly labelled
   demo mode.

### Non-goals (v1)

- Generated titles/captions (templated only).
- Sankey / network / treemap (not in Vega-Lite).
- json-render's unreleased `experimental_composeSpec` / `experimental_createEvaluator`.
- The `jev_viz()` function form (parser has a single seam where it could be added).
- The jev-demo-2 crossover (`jev_noul()` filter + `VISUALIZE` in one query) — stretch goal.
- Auth, multi-user, deployment. Localhost only.

## 2. Architecture

Two processes. Python does all thinking; the frontend only renders.

```
Browser (Vite + React)                    Python (FastAPI)
┌──────────────────────────┐   POST /run   ┌─────────────────────────────────┐
│ SQL editor │ render pane │ ────────────▶ │ 1 extract_viz(sql)→(sql,intents)│
│            │ json-render │ ◀──────────── │ 2 DuckDB executes sql           │
│            │ + Vega-Lite │    NDJSON     │ 3 profile(result)               │
└──────────────────────────┘    stream     │ 4 enumerate_candidates(profile) │
                                           │ 5 Jev: score candidates×intents │
                                           │ 6 rank → assemble spec          │
                                           └─────────────────────────────────┘
```

Each backend step is a module with a plain-data interface, testable alone.

| Module | Responsibility | Depends on |
|---|---|---|
| `parse.py` | `extract_viz(sql) -> (sql, intents)` | — |
| `db.py` | open demo DB read-only, run SQL with timeout and row cap | duckdb |
| `profile.py` | `profile(result) -> Profile` | duckdb |
| `rules/` | `@rule` functions `Profile -> list[Candidate]`, pre-rank and cap | profile |
| `questions.py` | build Jev questions from profile, candidates, intents | reused from demo-2 |
| `backend.py` | `JevBackend`, `DemoBackend`, `make_backend()` | reused from demo-2, `typesafe-sdk` |
| `cache.py` | sqlite content-addressed cache | reused from demo-2 |
| `rank.py` | rank key, thresholds, alternates, dashboard collisions | — |
| `spec.py` | assemble flat json-render spec from ranked panels | — |
| `api.py` | FastAPI `/run` NDJSON stream, timings, stats | all above |
| `data.py` | seeded synthetic retailer generator | duckdb |
| `eval.py` | golden-set eval, Jev vs rules-only baseline | live key |

Reused from jev-demo-2 (copied and trimmed, not imported): `backend.py`,
`questions.py`, `cache.py`, stats/cost counter, the SIMULATED-badge convention.
Not reused: the `Scorer` row-batching engine and UDF registration (no per-row
scoring here).

## 3. `VISUALIZE` clause

Not DuckDB syntax (DuckDB's parser is only extensible from C++). The app splits
it off before execution.

Grammar, trailing position only:

```
<sql> VISUALIZE                      -- bare: no intent
<sql> VISUALIZE '<intent>'
<sql> VISUALIZE '<intent>', '<intent>', ...   -- one panel per intent
```

- Tokenizer is aware of string literals, quoted identifiers, `--` and `/* */`
  comments, so `VISUALIZE` inside a string is never matched.
- Case-insensitive keyword; optional trailing semicolon; `''` escapes a quote
  inside an intent.
- Everything before the clause goes to DuckDB unchanged.
- No clause → `intents` is `None` → the app behaves as a plain SQL client.
- Bare clause → `intents == []` → a single panel scored against the fixed
  pseudo-intent "the main pattern in this query's result". Labelled in the UI
  as the weakest mode.
- Maximum 6 intents per query (dashboard cap); more is a parse error.

## 4. Profile

Computed entirely in code; Jev is never asked to count or compare numbers.

Per column:

| Field | Definition |
|---|---|
| `kind` | `temporal`: DATE/TIMESTAMP, or string/int where ≥95% of non-null values parse as a date or a year 1900–2100. `quantitative`: numeric, not temporal. `nominal`: string/bool. Numeric with ≤12 distinct integer values is tagged both `nominal` and `quantitative`. |
| `distinct` | distinct non-null count |
| `null_share` | 0–1 |
| `min`, `max` | for temporal and quantitative |
| `samples` | first 3 distinct non-null values in sorted order (deterministic) |
| `evenly_spaced` | temporal/quantitative values sorted and evenly spaced |

Plus `row_count` and `select_order` (column position). Computed with one
aggregate query over the result. The profile must be deterministic because its
hash is part of the cache key.

## 5. Candidate enumeration

```python
@dataclass(frozen=True)
class Candidate:
    id: str            # "c03", stable within a run
    kind: str          # rule name, used for alternates diversity
    columns: tuple     # columns used; measure columns flagged separately
    measures: tuple    # subset of columns used as a summed/averaged quantity
    title: str         # templated
    description: str   # the only text Jev reads about this panel
    vega: dict         # complete Vega-Lite spec with data: {"name": "rows"}
```

v1 rules (each a pure function, registered with `@rule`):

| Rule | Fires when | Guard |
|---|---|---|
| `kpi` | 1 row, 1–4 quantitative columns | — |
| `line` | temporal × quantitative | ≥3 time points |
| `multi_line` | temporal × quantitative × nominal | nominal ≤8 distinct |
| `bar` | nominal × quantitative | ≤30 distinct; horizontal if >8; sorted descending |
| `grouped_bar`, `stacked_bar` | nominal × nominal × quantitative | inner nominal ≤6 distinct |
| `scatter` | quantitative × quantitative | ≥10 rows; optional nominal colour ≤8 distinct |
| `histogram` | single quantitative | ≥30 rows, >12 distinct |
| `heatmap` | nominal × nominal × quantitative | both ≤30 distinct |
| `pie` | nominal × quantitative | ≤6 distinct, all values ≥0 |
| `table` | always | — |

Titles: humanised column names (`sum_revenue` → "Revenue") in a per-rule
template. Descriptions follow one fixed grammar per rule — form, measure,
breakdown, *what it reveals*:

> Multi-series line chart of `revenue` over `month`, one line per `region`.
> Shows how each region's revenue changes over time and lets regions be compared.

The "what it reveals" clause is written once per rule and is what Jev matches
against the intent. Adding a chart type means adding one rule; the Jev questions
and the frontend do not change.

Pre-rank and cap (deterministic, before Jev): max 4 candidates per rule; prefer
columns earlier in the SELECT list; prefer lower null share; cap at 24. `table`
and `kpi` do not count toward the cap. Truncation is reported ("24 of 41
scored"), never silent.

## 6. Jev question design

One request per run. The candidate lives in the *question*, not the state, so
this is many questions about one state (the documented fan-out pattern) rather
than many items packed into one state.

State:

```jsonc
{ "sql": "<cleaned sql>",
  "columns": { "<name>": {"kind": ..., "distinct": ..., "samples": [...], "range": ...} },
  "row_count": 120 }
```

**Panel relevance — Score, one per (intent, candidate), id `i{n}.{cid}`.**
Instructions: `The analyst asked: "<intent>". Proposed panel: "<description>".
How well would this panel answer what the analyst asked?`

| Level | Description |
|---|---|
| 0 | The panel shows columns that have nothing to do with what was asked. |
| 1 | The panel uses relevant columns, but its form hides what was asked, such as totals when the question is about change over time. |
| 2 | The panel partly answers the question: right measure, but missing a breakdown or comparison the question mentions. |
| 3 | The panel directly answers the question: right measure, right breakdown, in a form that makes the asked pattern visible. |

**Column sanity — Noul, one per numeric-looking column, id `id.{column}`.**
`Is \`<column>\` an identifier, code or label rather than a quantity that is
meaningful to sum or average?` Noul > 0.5 → code drops candidates that use the
column in `measures`, before ranking. These ride in the same request; scores
for dropped candidates are discarded (speculative fan-out).

Ranking (`rank.py`):

- Rank key: `P(level ≥ 2) = probabilities[2] + probabilities[3]`. The
  interpolated `score` is not used (docs call it numerically weak). Ties broken
  by Score `confidence`, then pre-rank order.
- Match bands (placeholders, tuned on the golden set):
  `≥ 0.6` strong → render; `0.3–0.6` weak → render with a weak-match tag and the
  alternates strip open; `< 0.3` none → table with "no strong match".
- Alternates: next 3 by rank key, at most one per `kind`.
- Dashboard collisions: intents are resolved in order; an intent whose top
  candidate is already taken uses its next best.
- `rank_key()` and the band thresholds are deliberately isolated in one small
  function for the project owner to write/tune.

Budget: ~24 candidates × ~90 tokens + ~400 tokens state ≈ 2.5k input tokens ≈
$0.0001 per run at $0.042 / 1M input tokens. Limits from the docs: 64k
tokens/request, state + longest question ≤ 32k, 1,200 requests/min.

**Open unknown:** the docs state no maximum question count (largest documented
example: 13). Three intents means 72 questions. Resolved by the probe (build
step 1). Fallback: one request per intent, fired concurrently.

Cache key: `sha256(model | question.key() | profile_hash)`. Re-running a query
skips Jev; changing only the intent reuses the column Nouls.

Demo mode: `DemoBackend` scores by token overlap between intent and
description, deterministic, with simulated latency. The UI shows a SIMULATED
badge whenever `backend.simulated` is true.

## 7. API contract

`POST /run {"sql": "..."}` → `application/x-ndjson`, one event per line, flushed
as each stage completes.

| Event | After | Payload |
|---|---|---|
| `parsed` | extract_viz | `sql`, `intents` (null / [] / [..]) |
| `result` | DuckDB | `columns`, `rows` (cap 5,000), `row_count`, `truncated`, `ms.query` |
| `spec` | rank + assemble | `spec`, `panels[]`, `ms.{profile,enumerate,jev}`, `usage.{input_tokens,usd}`, `scored` ("24 of 41"), `cache` (hit/miss), `simulated` |
| `error` | any stage | `stage`, `message` |

```jsonc
// panels[] entry
{ "intent": "how are regions trending",
  "chosen":     {"id":"c03","kind":"multi_line","title":"…","p":0.82,"element":{…}},
  "alternates": [{"id":"c07","kind":"stacked_bar","title":"…","p":0.41,"element":{…}}],
  "match": "strong" }
```

No `VISUALIZE` clause → stream ends after `result`. Alternates ship as complete
elements so swapping is a client-side spec edit with no server or Jev call.
Only chosen + ≤3 alternates per intent cross the wire.

Failure rule: **a viz failure never hides the data.** The `result` event has
already painted the table; a later `error` adds a warning and leaves it in
place. SQL errors arrive as `error` with `stage: "query"` and are shown in the
editor pane.

## 8. Frontend

Vite + React, published stable `@json-render/core` + `@json-render/react`,
`vega-embed` for charts, CodeMirror 6 for the editor.

Catalog (the only renderable types; backend emits only these):

| Component | Props | Purpose |
|---|---|---|
| `Grid` | `columns` | dashboard layout |
| `Panel` | `title`, `intent`, `p`, `match` | frame, match chip, weak tag, alternates strip |
| `Chart` | `vega` | vega-embed; injects rows from state `/rows` |
| `Kpi` | `label`, `value`, `format` | single number |
| `Table` | `columns`, `maxRows` | fallback and instant first paint |

Rows are sent once and held in json-render state at `/rows`; every `Chart`
spec references `data: {"name": "rows"}`.

Page: editor left, render pane right, persistent timing bar at the bottom —
`query · profile · jev · render` in ms, tokens, USD, "N of M scored", cache
hit/miss, SIMULATED badge. Render time is measured client-side from `spec`
receipt to Vega's render-complete callback. ⌘↵ runs. An examples dropdown holds
the recordable demo script. A small CodeMirror extension highlights `VISUALIZE`
as a keyword.

To verify at build time (read from repo source during research, not yet
exercised): exact `defineCatalog` signature and `$state` binding shape in the
installed json-render version.

## 9. Safety

- DuckDB opens the demo database read-only with `enable_external_access=false`
  (no file reads, `ATTACH`, httpfs); per-statement timeout; 5,000-row cap.
- Server binds to localhost only.
- `TYPESAFE_API_KEY` is read from `.env` server-side, never logged, never sent
  to the client. `.env` is gitignored.

## 10. Dataset

Seeded synthetic retailer, generated into a read-only DuckDB file.

| Table | Rows | Columns of note |
|---|---|---|
| `orders` | ~50k | `order_date`, `region`, `channel`, `revenue`, `profit` (can be negative), `customer_id`, `product_id` |
| `customers` | ~5k | `segment`, `signup_year` (INT), `zip`, `country` |
| `products` | ~200 | `category`, `price`, `rating` (1–5) |

Deliberate traps: `customer_id` and `zip` (numeric non-measures),
`signup_year` (int that is time), `rating` (axis or measure), negative `profit`
(blocks pie). Planted patterns so intents have right answers: one declining
region, a seasonal spike, a high-revenue low-profit category, a price–rating
correlation.

## 11. Testing

| Layer | What | Network |
|---|---|---|
| Unit | `extract_viz` (quotes, comments, multi-intent, bare, >6 intents), `profile`, each rule, title humaniser, rank bands, alternates diversity, dashboard collisions | none |
| Property | every emitted `vega` validates against the Vega-Lite JSON schema | none |
| Stream | `/run` event order; error-keeps-table; no-clause ends after `result` — with `DemoBackend` | none |
| E2E | Playwright smoke in demo mode: run example → table → chart | none |
| Eval | golden set: Jev top-1 / top-3 vs rules-only baseline; threshold tuning | live key |

## 12. Build order

| Step | Work | Gate |
|---|---|---|
| 0 | `uv` project, copy/trim demo-2 modules, interface contract doc | — |
| 1 | Probe (throwaway): 24 / 48 / 72 Score questions, record latency and errors | decides single request vs one per intent |
| 2 | `data.py`, `parse.py`, `profile.py`, `rules/` — TDD, offline | — |
| 3 | `questions.py`, `rank.py`, golden set, `eval.py` | **Jev top-1 must clearly beat rules-only; otherwise stop and rethink before any UI** |
| 4 | `api.py` NDJSON stream | — |
| 5 | Frontend: catalog, editor, timing bar | — |
| 6 | Demo script, README, CLAUDE.md | — |

Steps 1 and 3 need a live key. Steps 2, 4 and 5 are suitable for delegation to
cheaper subagents against the step-0 interface contract. Owner-written pieces:
`rank_key()` + thresholds, and the golden-set intents.

## 13. Research sources

- TypeSafe docs: `docs.typesafe.ai` — api, models, primitives (choice, noul,
  score), confidence, patterns/fan-out, cookbooks/function_calling,
  cookbooks/parallel_questions, model-jaggedness/jev-1.13.
- Vercel Labs json-render: `github.com/vercel-labs/json-render`,
  `json-render.dev/docs/jev` (Jev composition marked experimental/unreleased).
- jev-demo-2: `docs/plan.md`, `docs/handoff-llm-benchmark.md`, `src/semsql/*`.
