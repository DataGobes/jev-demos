# jev-demo-4 — semantic dbt tests

A `jaffle_shop` dbt project where four `jev_expect` tests, written as plain English sentences
in `schema.yml`, catch rows that pass every structural test but are still wrong — a junk customer
name, a return comment that contradicts its reason code, a 5-star review that reads like a
complaint — or that leak something they shouldn't, like PII buried in a support ticket. Every flagged row carries a probability from
TypeSafe's Jev model, scored against a hidden answer key and a hand-written regex/keyword
baseline in the same project.

Fourth in the Jev demo series (Cringe-o-Meter, semsql, VISUALIZE). This is a demo repo, not a
package: no PyPI, no dbt hub.

## The test, as written

```yaml
- name: comment
  data_tests:
    - not_null
    - jev_expect:
        name: returns_comment_matches_reason_code
        arguments:
          fails_if: "The customer's `comment` describes a different main reason for the return than `reason_code` (damaged, wrong_item, late, changed_mind, other)."
          context: [reason_code]
          threshold: 0.8
          criteria:
            "true": "The stated main reason plainly belongs to another code"
            "false": "Consistent with the code, or too vague to tell; code 'other' fits anything unusual"
        config: {severity: error, store_failures: true, tags: [semantic]}
```

`fails_if` is the defect condition, phrased so "yes" means the row fails. `context` adds columns
Jev sees alongside the tested one; `threshold` is the probability above which a row is flagged;
`criteria` gives Jev a short true/false rubric. Everything else (`severity`, `store_failures`,
`tags`) is standard dbt.

## How it works

1. `dbt-duckdb` loads the `jevdbt.plugin` module (configured in `profiles.yml`) and registers a
   `jev_noul(state, question)` Arrow UDF on the DuckDB connection.
2. The `jev_expect` generic test macro (`jaffle_shop/macros/jev_expect.sql`) compiles each
   `jev_expect` block into a `jev_noul` call over a JSON `state` (the tested column plus
   `context` columns) and a JSON `question` (the `fails_if` sentence plus `criteria`), wrapped in
   a materialized CTE so the row-level probability, `jev_p`, is computed exactly once per row.
3. The UDF batches rows by question, dedupes identical states, and hands misses to a `Scorer`
   that packs them into requests, calls TypeSafe's Jev model (`AsyncTypeSafeClient.system_one`)
   under a concurrency and rate limit, and caches every result in `.jev_cache.sqlite`. Cached
   judgments are keyed by the model alias (`jev-latest`) and pack size, so clear the cache file
   after a model update.
4. `dbt test --select tag:semantic` runs the four tests; `store_failures: true` persists every
   row with `jev_p >= threshold` into `main_dbt_test__audit`, alongside a hand-written regex
   baseline (`tag:baseline`) run the same way.
5. `scripts/score.py` reads both sets of stored failures, joins them against the hidden
   `eval/golden_defects.csv` answer key, and prints precision/recall/F1 for Jev vs. the baseline
   on every test — the numbers that back the gate below and the numbers in this README.

## Run it

```bash
uv sync
uv run python scripts/make_seeds.py                 # deterministic seeds + golden key (seed=42)
cd jaffle_shop
uv run dbt build --profiles-dir . --exclude tag:semantic   # standard tests pass; regex baseline
                                                             # tests run too (severity warn),
                                                             # stored for the scorecard below
uv run dbt test --profiles-dir . --select tag:semantic     # the four jev_expect tests
cd ..
uv run python scripts/show_failures.py               # spot-check individual flagged rows
uv run python scripts/score.py                        # scorecard: Jev vs. regex baseline
```

Without `TYPESAFE_API_KEY`, that scorecard is a wiring check, not a result: every `jev_p` comes
from `DemoBackend`'s hash noise, and `score.py` says so on screen with a SIMULATED banner and
table title.

Never use the machine's global `dbt` — it resolves to dbt Fusion, which cannot load Python
adapter plugins (see "Why dbt-core, not Fusion" below). Always run `uv run dbt`, or activate
`.venv` first, from inside `jaffle_shop/`.

### Live vs. SIMULATED

Jev runs live only when `TYPESAFE_API_KEY` is set. Put it in a `.env` file at the repo root:

```
TYPESAFE_API_KEY=...
```

Without a key, every run falls back to a deterministic offline `DemoBackend` and every summary
line is labelled `SIMULATED` instead of `LIVE` — numbers from a `SIMULATED` run are for wiring
checks only, never reported as real. `JEV_MODE=demo` forces the offline backend even with a key
present (used for smoke-testing the recording script); `JEV_MODE=live` forces live and errors out
if no key is set.

## Latest gated numbers

From `docs/eval-results.md`, run `2026-09-24T20:37:35Z · live/pack=1` (the recording pack — see
"Gate conclusion" in that file for the full picture and run-to-run variance):

| test | defects | Jev P | Jev R | Jev hard-neg | regex P | regex R | regex hard-neg |
|---|---|---|---|---|---|---|---|
| customers_full_name_is_a_person | 25 | 0.96 | 0.96 | 1 | 0.71 | 0.60 | 6 |
| returns_comment_matches_reason_code | 12 | 1.00 | 1.00 | 0 | 0.45 | 0.75 | 6 |
| reviews_body_matches_stars | 24 | 1.00 | 1.00 | 0 | 0.39 | 0.92 | 8 |
| tickets_body_has_no_pii | 14 | 1.00 | 1.00 | 0 | 0.48 | 0.86 | 13 |

**Gate: PASS** — Jev precision and recall ≥ 0.85 on every test, beating the regex baseline on F1
everywhere. 1,300 judgments, ~54 s wall time at pack=1 (dbt-measured; 1,057 requests bounded by
the 1,200 rpm limit ≈ 53 s minimum), $0.017.

Run-to-run variance: `tickets_body_has_no_pii` precision was 0.93 in the first pack=1 run and
1.00 in this one — one hard negative sits near the 0.5 threshold. Quote the range (0.93–1.00),
not just the best run.

Packing (batching multiple rows into one Jev request) trades accuracy for speed on exactly the
test that relates two fields: `returns_comment_matches_reason_code` recall falls from 1.00 at
pack=1 to 0.75 at pack=4 and 0.58 at pack=8, while the other three tests hold steady. So pack
stays at 1 by default; the plugin config and `JEV_PACK` exist to explore that trade-off, not to
ship a packed default.

The two remaining Jev errors are honest ones, not tuning targets: it misses `Pietje Puk` (a Dutch
placeholder name, culturally specific) and flags `Anna Test` (p=0.90 — "Test" is a real surname).
No wording, threshold, data, or answer-key changes were made to get this result.

## Recording

`scripts/record.sh [--cold] [--pack N]` types out each beat of the demo and waits for a keypress
before running it, clearing the screen first so every beat starts clean: a plain `dbt build`,
the `jev_expect` blocks in `schema.yml` (via `scripts/show.py tests`), the semantic test run, a
look at the flagged rows (`scripts/show.py rows`), the scorecard (`scripts/show.py score`), then
a rerun to show it's fully cached.

Terminal size: **90 columns x 30 rows**, a large font (so it reads on a muted phone clip). Each
`scripts/show.py` view is laid out for that box — short lines, generous spacing, nothing
truncated — so nothing scrolls off or wraps unreadably. `show.py score`'s two headline lines and
compact per-test table are meant to be legible even shrunk down for a phone timeline.

A cold pack=1 run (`--cold`, deletes `.jev_cache.sqlite` first) takes about 55 s of real wall time
for ~1,300 live judgments (~$0.017) — a single take, no speed-ramping needed. Beat 3 (the
semantic test run) can now be recorded cold and shown at real speed: `record.sh` exports
`JEV_PROGRESS=1`, so while the four tests are judging in the background, a live counter
(`  Jev · 612 judgments · 24.1 s · $0.008 ⠋`) rewrites itself on the terminal a few times a
second instead of sitting on a blank screen. It disappears on its own once judging finishes and
dbt prints its own result lines. A cached rerun's near-instant latency must never be presented as
live latency.

Smoke-test the script in demo mode only — **never run it live**:

```bash
JEV_MODE=demo DOTENV_DISABLE=1 TYPE_DELAY=0 yes '' | scripts/record.sh
```

This overwrites the stored-failure tables in `jaffle_shop/jaffle_shop.duckdb` with demo-mode
output; if you smoke-test after a live run, restore state by rerunning the live semantic +
baseline tests (no `JEV_MODE` set) once the cache is warm, so no live requests are actually made.

## Why dbt-core, not Fusion

This project depends on a Python adapter plugin (`jevdbt.plugin`, loaded via `dbt-duckdb`'s
`plugins:` config) to register the `jev_noul` UDF on the DuckDB connection before any test runs.
dbt Fusion — the machine's global `dbt` binary, and also what dbt-core 2.0 (currently rc) is
built on — is a from-scratch Rust engine that does not load Python adapter plugins, so it cannot
run this project at all. The pins here are dbt-core 1.12.5 + dbt-duckdb 1.11.0, the latest stable
release on the classic Python execution path; that pin should be revisited once dbt-core 2.0
stabilizes and Python plugin support (if any) is clear.
