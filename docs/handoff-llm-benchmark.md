# Hand-off: Jev vs frontier LLM benchmark

Written 2026-09-20 at the end of the session that built semsql. Read this together with
`docs/plan.md` (the module interface contract) and `CLAUDE.md` (project rules).

## 1. Why this exists

The semsql demo video was posted to LinkedIn and did well. In the comments, Vinoth C.
(Lead Data Engineer @ SEEK) asked:

> "have you benchmarked Jev with any frontier LLM to validate the results in terms of
> accuracy, latency, and cost?"

Gijs replied that no benchmark had been run, and added: *"I've worked enough with frontier
LLM's to know that Jev beats them on cost and latency and it's not even close."* Vinoth
followed up that he wants to see how it compares to what TypeSafe claims on their site.

**The job:** build that benchmark and publish the numbers. This is a public follow-up to a
public claim, so the result has to be defensible whichever way it lands. If Jev loses on
some axis, that gets published too.

## 2. State of the repo

Branch `main`, clean tree, 7 commits, HEAD `478723c`. 107 tests pass (`uv run pytest -q`),
`uv run ruff check` clean.

```
src/semsql/  cli.py udf.py engine.py backend.py cache.py stats.py questions.py
             rubrics.toml data.py
tests/       8 files
demo.sql     the 4 recording queries (F1-F4 in the REPL)
docs/plan.md the interface contract — CLAUDE.md says do not deviate without updating it
```

Working today: `jev_noul`, `jev_score`, `jev_grade`, `jev_score_levels`, `jev_choice` as
DuckDB UDFs; async scorer with dedupe + sqlite cache + row packing + rpm pacing; Rich REPL
with a live cost panel; `semsql eval-pack`; a deterministic offline `DemoBackend`.

## 3. Blocker: there is no LLM API key on this machine

`.env` holds `TYPESAFE_API_KEY` only. No `ANTHROPIC_API_KEY`, no `OPENAI_API_KEY`, no
Azure/Gemini credentials in the shell or in `.env`. `ANTHROPIC_BASE_URL` is set but belongs
to the Claude Code harness — it is not a usable user API key, do not try to borrow it.

**First thing to do: ask the user which providers to benchmark and have them add the keys
to `.env` themselves.** Never ask for the key value in chat, never print or log it.
`load_dotenv()` in `cli.py` already reads `.env` without overriding real env vars.

Until keys exist, everything except the actual measurement runs can be built and tested
against a fake/recorded backend.

## 4. Facts already measured (do not re-measure)

Jev 1.13 (`jev-latest`), from the live TypeSafe docs on 2026-09-18:

| Fact | Value |
| --- | --- |
| Price | $0.042 per 1M input tokens; output tokens free |
| Rate limits | 1,200 requests/min, 250k tokens/s |
| Context | 64k tokens/request; 32k for state + longest question |
| Docs warning | "Accuracy falls as the state grows with content unrelated to the decision" |

Live runs from this session, on the current 10k synthetic dataset (seed 7):

| Run | Result |
| --- | --- |
| 20 rows, pack=1 | 1.58 s, 20 requests, $0.0003 |
| `eval-pack --sample 200 --pack 16` | mean abs diff 0.0541, max diff 0.5000, flip@0.5 1.50%, flip@0.8 0.50%; 200 req/$0.0025 vs 13 req/$0.0007 |
| Demo query, ~4,400 rows, pack=16 | 19.7 s, 333 requests, $0.0218 |
| Same query re-run (cached) | 0.04 s, 0 requests, $0.0000 |
| Keyword baseline `ILIKE '%refund%'` | 780 rows |
| Jev refund queue (stars<=2, p>0.8) | 913 rows, 595 of which never contain "refund" |

These are the numbers quoted in the published post. If the benchmark regenerates data or
changes the sample, do not overwrite these — report new numbers separately.

## 5. Ground truth is already in the generator

`semsql.data.generate_labeled(n, seed) -> list[tuple[dict, str]]` returns each row with the
intent label that produced it. The label is deliberately absent from `generate_reviews()`
and from the `reviews` table, so no query can cheat.

Label counts at n=10,000, seed=7 (9,672 non-empty bodies):

```
praise 2004   defect 1381   delivery_problem 1175   neutral 1012   churn_threat 989
how_to 977    sarcasm 846   refund_no_keyword 818   refund_keyword 416
keyword_no_refund 382
```

Proposed truth mapping for the benchmark's primary task ("is the customer asking for their
money back?"):

- **True:** `refund_no_keyword`, `refund_keyword` (1,234 rows)
- **False:** everything else, including `keyword_no_refund` (the deliberate keyword traps)

**Caveat that must be stated in any published result:** these labels are what the generator
*intended*, not human judgments. Some rows are genuinely ambiguous — a `churn_threat`
template can imply wanting money back, and `sarcasm` rows can carry refund intent. Before
publishing accuracy figures, hand-check a random sample (100 rows is enough) and report the
label-noise rate you find. If noise is above a few percent, accuracy differences smaller
than that are not real.

A second task worth running, if time allows: the `anger` rubric as a 4-level ordinal
(`jev_score`/`jev_grade`). The generator's anger level is applied in `_make_body` but is not
currently returned by `generate_labeled` — it would need to be threaded out, which is a
small change to `data.py`. Ordinal agreement (Spearman, exact-level accuracy, off-by-one)
tells a different story than binary accuracy and is a good second chart.

## 6. Benchmark design

### Contenders

- **Jev** (`jev-latest`), `pack=1`, cache disabled.
- **2-3 frontier LLMs**, chosen with the user. Each gets a prompt-and-parse wrapper that
  returns a yes/no plus, where the API supports it, a probability.
- **Keyword baseline** (`ILIKE '%refund%'`). Free, instant, and it makes the accuracy
  numbers legible — include it, it costs nothing and it is the thing the video beat.

### Metrics

Per contender, on the same sample, in the same run:

- **Accuracy:** precision, recall, F1 and balanced accuracy at the decision threshold; plus
  ROC-AUC for contenders that emit a usable probability. Report the confusion matrix.
  Break out accuracy on the two adversarial slices (`refund_no_keyword`,
  `keyword_no_refund`) — that is where the interesting difference will be.
- **Latency:** p50 and p95 per-row wall time at a fixed concurrency, plus total wall time
  for the whole sample. Discard a warm-up request per contender.
- **Cost:** from each API's own reported token usage times that provider's published price.
  **Look the prices up from the provider's official pricing page during the session — do
  not use prices from memory.** Record the price, the URL and the date in the output.

### Fairness rules (write these into the report)

1. Same rows, same order, same machine, same network, same session.
2. Interleave contenders (round-robin per row) rather than running each in a block, so a
   slow network minute does not land entirely on one contender.
3. Temperature 0 / greedy for LLMs. Jev is deterministic given the same input.
4. Caching off everywhere, including any provider-side prompt caching you can disable.
5. Equal prompt effort: the LLM prompt gets the same instruction text as the Jev question,
   plus the minimum scaffolding needed to make it return parseable output. Iterate the LLM
   prompt at least a couple of rounds and keep the best — a deliberately bad LLM prompt
   would make the benchmark worthless. Save every prompt variant tried in the report.
6. Count LLM parse failures explicitly. A response that cannot be parsed is a failure of
   the integration and belongs in the table, not silently retried away.
7. `pack=1` for Jev in the headline table. Packed throughput can appear as a clearly
   labelled footnote, with the `eval-pack` agreement numbers next to it.

### Sample size

Start at 200 rows while iterating (matches `eval-pack`, keeps Jev cost around $0.003 and
LLM cost small). Final run at 1,000-2,000 rows, stratified so the adversarial slices are
well represented rather than proportional. Estimate LLM cost before the final run and tell
the user the number before spending it.

## 7. Suggested implementation

Follow the project's existing discipline: **update `docs/plan.md` with the new interfaces
before writing code** (CLAUDE.md rule), then build.

```
src/semsql/bench/
  __init__.py
  truth.py     label -> bool mapping, stratified sampling, slice definitions
  judges.py    Judge protocol: name, async judge_one(text) -> JudgeResult
               JevJudge (reuses backend.JevBackend at pack=1), LlmJudge (per provider),
               KeywordJudge (free, local)
  runner.py    interleaved async runner, per-judge latency samples, usage accumulation
  report.py    metrics + Rich tables + a markdown report written to docs/
cli.py         new `semsql bench` subcommand
tests/test_bench_*.py
```

Notes:

- **Do not reuse `stats.PRICE_PER_MTOK_USD` for LLMs.** It is Jev's price. Give each judge
  its own price record (input price, output price, source URL, date).
- `Stats` tracks totals but not per-request latency distributions; the runner needs its own
  list of per-row durations for p50/p95.
- Keep judge results raw (probability or label + usage + duration + raw response) and
  compute every metric afterwards in `report.py`, so thresholds and slices can be changed
  without re-spending.
- Persist raw results to a JSON/parquet file so the report can be regenerated offline and
  so the run is auditable by anyone who asks in the comments.
- Tests must not hit the network: fake judges with scripted responses, including a parse
  failure and an API error.

### CLI sketch

```
uv run semsql bench --sample 200 --judges jev,<llm-a>,<llm-b>,keyword \
                    --concurrency 8 --out docs/bench-2026-09-XX.md
```

## 8. Verification before reporting anything

- `uv run pytest -q` and `uv run ruff check` green.
- Actually run `semsql bench` end to end with fake judges, then with one real judge on 20
  rows, before the full run.
- **Start the real entry point yourself.** A bug in this session shipped a broken REPL
  because every test used `-c` and nobody launched `semsql` with no arguments. There is now
  a regression test for it; keep that habit for `bench`.
- Numbers in the report must come from a run you observed in this session, with the command
  that produced them recorded next to them.

## 9. Publication guidance

The output is a follow-up LinkedIn post and a reply to Vinoth. Keep the honesty posture the
rest of this project has used:

- Say the dataset is synthetic and say why that limits the accuracy claim.
- Report the label-noise spot-check.
- If Jev does not win an axis, lead with that — it is more credible and more interesting.
- Gijs's existing comment claims Jev wins cost and latency "and it's not even close." If the
  benchmark supports it, cite the numbers. If it does not, the follow-up post should say so
  plainly and correct the earlier comment.

## 10. Open items carried over from this session

1. **`docs/plan.md` lines 26-27 overstate the docs.** They read as if the TypeSafe docs
   endorse packing many rows per request. They do not: fan-out in the docs is many questions
   about *one* item, and the cookbooks (`rerank_typesafe`, `classifying_rag_passages`) use
   one request per item for longer texts. The per-item-path shape does appear in the Jev
   1.13 limitations page under "Counting", but only on an 8-word toy example. The user was
   asked whether to reword the plan and also switch the request to the docs' exact
   `items[i]` list-path style (which would require re-running `eval-pack`); **no answer yet
   — ask before changing it.**
2. Whether to publish the repo. The reply to Vinoth shows `uv run semsql --live --pack 16`,
   which invites the question.
3. The typewriter animation (F1-F9 in the REPL) has never been watched in a real terminal —
   only simulated headlessly. If it turns out the terminal eats the F-keys, a `Ctrl+1..4`
   fallback was offered.

## 11. Working preferences

- The user is on an expensive model in the main session and wants build work delegated to
  cheaper subagents (sonnet for building, haiku for lookups). Main session plans, writes the
  brief, reviews. See the `delegate-to-cheaper-subagents` memory.
- Fix the code rather than loosening a test. A duplicate-rate test caught a real data
  regression this session; the fix was more template variety, not a higher threshold.
- Read the live TypeSafe docs rather than relying on memory — that is how the fan-out
  mis-description above was caught.
