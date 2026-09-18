# semsql — Semantic SQL in DuckDB, powered by TypeSafe Jev

Goal: a terminal demo you can screen-record. Plain-English judgments become typed SQL
columns:

```sql
SELECT id, body, jev_score(body, 'anger') AS anger
FROM reviews
WHERE jev_noul(body, 'The customer is asking for their money back') > 0.8
ORDER BY anger DESC LIMIT 10;
```

While the query runs, a live Rich panel shows rows scored, rows/s, requests, input tokens,
cost in USD and cache hits. Change the English, re-run, new answer.

## Facts from the live docs (2026-09-18, Jev 1.13)

- SDK: `typesafe-sdk` 0.7.0, `AsyncTypeSafeClient().system_one(state, questions, model=...)`.
  Answers: `resp.answers[qid].noul` | `.score/.confidence/.probabilities` | `.choice/.confidence/.probabilities`.
  `resp.usage.input_tokens`. Errors: `TypeSafeAPIError` (`.status`, `.request_id`). SDK retries 429/529 itself.
- Auth: env `TYPESAFE_API_KEY`. Model default `jev-latest`.
- Price: $0.042 per 1M input tokens, output free.
- Limits: 1,200 requests/min, 250k tokens/s, 64k tokens/request, Choice max 255 options.
- Score levels must "describe situations, not degrees" → `jev_score` uses named rubrics
  with concrete level descriptions, not a bare dimension word.
- All questions in a request are evaluated in parallel against one state → we can pack
  several rows into one request (one question per row) to beat the 20 req/s ceiling.

## SQL surface

| Function | Returns | Meaning |
| --- | --- | --- |
| `jev_noul(text, question)` | DOUBLE 0..1 | probability the statement/question holds for the text |
| `jev_score(text, rubric)` | DOUBLE 0..n-1 | position on named rubric from `rubrics.toml` |
| `jev_score_levels(text, instructions, levels VARCHAR[])` | DOUBLE | ad-hoc rubric |
| `jev_choice(text, instructions, options VARCHAR[])` | VARCHAR | chosen option |

NULL text → NULL. The question/rubric args must be constant per query chunk (we take the
distinct values per chunk and handle each group).

## Architecture (src/semsql/)

```
cli.py ──> udf.py ──> engine.py (Scorer) ──> backend.py (JevBackend | DemoBackend)
  │                      │  └─> cache.py (sqlite)
  └── reads ── stats.py <┘
questions.py (Question dataclass, rubrics loader)      data.py (synthetic dataset)
```

### Interfaces (contract between modules — do not deviate)

```python
# questions.py
@dataclass(frozen=True)
class Question:
    kind: Literal["noul", "score", "choice"]
    instructions: str
    levels: tuple[str, ...] = ()     # score
    options: tuple[str, ...] = ()    # choice
    def key(self) -> str: ...        # stable hash input: kind|instructions|levels|options

def load_rubrics(path: Path | None = None) -> dict[str, Question]   # default: packaged rubrics.toml
# rubrics.toml:  [anger]  instructions = "..."  levels = ["...", "...", "..."]

# stats.py
PRICE_PER_MTOK_USD = 0.042
@dataclass(frozen=True)
class StatsSnapshot: rows:int; cache_hits:int; requests:int; input_tokens:int; errors:int; elapsed_s:float
    # properties: rows_per_s, cost_usd
class Stats:            # thread-safe (threading.Lock)
    def reset(self) -> None        # also restarts the clock
    def add(self, *, rows=0, cache_hits=0, requests=0, input_tokens=0, errors=0) -> None
    def snapshot(self) -> StatsSnapshot

# cache.py
class Cache:            # sqlite3, thread-safe, check_same_thread=False + lock
    def __init__(self, path: Path | str)      # ":memory:" allowed
    def get_many(self, model: str, question: Question, texts: list[str]) -> dict[str, float | str]
    def put_many(self, model: str, question: Question, items: dict[str, float | str]) -> None
    def clear(self) -> None
    def close(self) -> None

# backend.py
Value = float | str
@dataclass
class BatchResult: values: list[Value | None]; input_tokens: int     # None = failed row
class Backend(Protocol):
    name: str            # e.g. "jev-latest" / "demo"
    simulated: bool
    async def judge(self, texts: list[str], question: Question) -> BatchResult  # ONE request
    async def aclose(self) -> None
class JevBackend: ...    # AsyncTypeSafeClient
class DemoBackend: ...   # deterministic heuristic, asyncio.sleep(~0.15), clearly simulated
def make_backend(*, demo: bool | None = None, model: str = "jev-latest") -> Backend
    # demo=None → auto: DemoBackend when TYPESAFE_API_KEY is unset

# engine.py
class Scorer:
    def __init__(self, backend: Backend, stats: Stats, cache: Cache | None = None, *,
                 pack: int = 1, concurrency: int = 32, rpm: int = 1200)
    def score_many(self, texts: list[str | None], question: Question) -> list[Value | None]
        # SYNC + thread-safe; called from DuckDB UDF threads. Owns a background asyncio loop thread.
    def close(self) -> None

# udf.py
def register(con: duckdb.DuckDBPyConnection, scorer: Scorer, rubrics: dict[str, Question]) -> None

# data.py
def generate_reviews(n: int, seed: int = 7) -> list[dict]     # id, product, stars, body, created_at
def load_reviews(con, n: int = 10_000, seed: int = 7) -> None # CREATE OR REPLACE TABLE reviews
```

### JevBackend request shape

- `len(texts) == 1`: `state = text`, `questions = {"q": <question>}`.
- packed (`len(texts) > 1`): `state = {"rows": {"r000": text0, "r001": text1, ...}}` and one
  question per row whose instructions are prefixed with
  ``Judge ONLY the text in `rows.r000`, ignoring all other rows. `` followed by the original
  instructions. Same criteria for every row.
- `TypeSafeAPIError` → all rows in that request become `None`, `stats.errors += 1`. Never raise
  out of `judge`.

### Scorer.score_many algorithm

1. NULL/empty texts → None. Dedupe remaining texts (compute each distinct text once).
2. Cache lookup (`cache_hits += n`, `rows += n`).
3. Chunk misses into groups of `pack`; run `backend.judge` for each under
   `asyncio.Semaphore(concurrency)` and an rpm pacer (min interval `60/rpm` between request
   starts). After each request: `stats.add(rows=len(chunk), requests=1, input_tokens=...)`, so
   the live panel moves during the query, not after.
4. Write successes to cache. Map back to input order.

### Packing honesty

`pack=1` is the accuracy-safe default. `--pack N` trades possible cross-row interference for
throughput. `semsql eval-pack --sample 200 --pack 16` reports agreement (mean abs diff of
nouls, threshold-flip rate at 0.5/0.8) between pack=1 and pack=N so the number shown in a clip
is defensible. Needs a real API key.

## CLI (cli.py, entry point `semsql`)

- `semsql` → REPL (prompt_toolkit, multi-line until `;`, history file `.semsql_history`).
- `semsql -c "SQL"` one-shot. `semsql gen --rows 10000` loads synthetic `reviews` into the db.
- `semsql eval-pack ...` as above.
- Flags: `--db semsql.duckdb`, `--pack`, `--concurrency`, `--rpm`, `--demo/--live`, `--no-cache`,
  `--cache-path .semsql_cache.sqlite`, `--model`.
- During a query: `rich.live.Live` panel (refresh 12/s) fed from `stats.snapshot()`: rows, rows/s,
  requests, tokens, **cost ($)**, cache hits, errors, backend name. If `backend.simulated`, a
  bold yellow `SIMULATED — no TYPESAFE_API_KEY` badge is always visible so a demo-mode
  recording can never pass for the real thing.
- After: result as Rich table (first 20 rows, long text truncated ~80 chars). DOUBLE columns whose
  values all lie in [0,1] get an inline bar (`█████░░░ 0.83`). Footer: rows, wall time, cost.
- Dot commands: `.help .tables .rubrics .stats .cache clear .quit`.

## Synthetic data (data.py)

10k seeded product reviews / support messages for a fictional appliance shop. Crucial for the
clip: keyword search must visibly fail where semantics win.
- refund intent WITHOUT the word "refund" ("I want my money back", "send it back and credit my card")
- the word "refund" WITHOUT refund intent ("no need for a refund, replacement arrived, love it")
- graded anger, urgency, sarcasm; some very short, some long; ~3% NULL/empty bodies.
- Template + slot-filling with enough variety that <5% of bodies are exact duplicates.

## Demo script for the recording (README)

1. `semsql gen --rows 10000`
2. `SELECT count(*) FROM reviews WHERE body ILIKE '%refund%';`  ← keyword baseline
3. The `jev_noul` query above with a cheap pre-filter CTE (e.g. `stars <= 2`) → live panel.
4. Edit the English ("...threatening to leave for a competitor"), re-run.
5. Re-run query 3 → all cache hits, 0 requests, $0.0000.

## Build split

- Agent A (sonnet): `data.py` + `tests/test_data.py`.
- Agent B (sonnet): `questions.py`, `rubrics.toml`, `stats.py`, `cache.py`, `backend.py`, `engine.py`, `udf.py` + tests.
- Agent C (sonnet): `cli.py`, `__init__.py` main, `README.md`, `CLAUDE.md`, `.gitignore` — codes against the interfaces above.
- Main session: integration, end-to-end verification in demo mode, review.

## Verification

`uv run pytest -q`, `uv run ruff check`, then e2e in demo mode:
`uv run semsql gen --rows 2000 && uv run semsql -c "<query>"`; re-run shows cache hits.
Live-mode check requires `TYPESAFE_API_KEY` (not present on this machine at build time).
