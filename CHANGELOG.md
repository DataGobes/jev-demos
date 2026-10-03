# Changelog

Notable changes to the demos in this repo, newest first. Each entry names the demo it touches.
The demos aren't versioned, so entries are dated by the day they land on `main`. Numbers quoted
here come from live, logged runs; see each demo's own docs for the full record.

## 2026-10-03

### 06 · Jev vs LLMs through `ai_query` — new demo

- **Added** [`06-jev-vs-ai-query/`](06-jev-vs-ai-query/): one `jev_expect` test per dataset, judged
  by Jev or by an LLM served in Databricks through `ai_query`, switched with
  `--vars '{judge: …}'`. Prompts are frozen and pre-registered, the LLM spend has a $15 cap, and
  every number comes from the logged runs in `docs/eval-results.md`.
- **Pass 1** (the same 4,161 rows for every judge), F1 on Banking77 / Abt-Buy / wanderbricks: Jev
  0.56 / 0.86 / 0.98, gpt-oss-20b 0.67 / 0.86 / 0.91, Llama 3.3 70B 0.50 / 0.69 / 0.74. Jev is the
  most precise (0.85 to 1.00, 0 false alarms on 205 clean states), and gpt-oss-20b catches far more
  near-miss label swaps (0.72 against 0.24). Jev took 25 requests, 19.4 s and $0.029; gpt-oss-20b
  4,006 requests, 56.9 s and $0.183; Llama 141.3 s and $0.653. A fresh pass 2 reproduced every F1
  within 0.02 except Llama on wanderbricks (0.04).
- **Frontier judge**: Opus 5 is rejected by `ai_query` over a table ("not supported for batch
  inference"), so Opus 4.8 replaced it in a dated amendment. A full pass would cost about $20, over
  the cap, so Opus 4.8 is reported from the 50-row pilot only (0.67 / 1.00 / 1.00).
- **Jev at scale**: 18,674 new judgments over all of Banking77 and Abt-Buy in 120 requests, 25.5 s
  and $0.132.

## 2026-10-01

### 05 · dbt semantic tests on Databricks — new demo

- **Added** [`05-dbt-databricks/`](05-dbt-databricks/): demo 04's four `jev_expect` tests on
  Databricks. Jev runs in a Unity Catalog Python function (`jev_demo.jev.noul_pack`) that reads the
  TypeSafe key from a UC secret, a dbt post-hook judges each distinct state once and caches it in a
  Delta table, and packs are cut by estimated tokens (48k budget, 256-row cap). The same project
  also runs inside Databricks as a bundle job, with a results-only mode that judges nothing.
- **Yardstick** (demo 04's data, answer key and regex baselines): four fresh live runs, all gate
  PASS, each 1,057 states in 6 requests for $0.006 (demo 04 needed 18 requests at 64 rows per
  request). Recall moved by one row between identical runs (two rows sit on their threshold);
  precision did not move.
- **Production**: 50,000 Amazon Fine Food reviews with 1,386 planted star flips, 44,292 distinct
  states judged in 277 requests for $0.437, a 2,500-row increment judging only its 2,219 new states
  ($0.022), and a rerun with 0 requests. The raw gate **fails**: recall 0.84 against 0.85. Audited
  precision is 0.94 (blind audit by two LLM labellers); 2 of 100 audited planted flips don't read as
  mismatched, and corrected for that, recall is about 0.86 (a point estimate). Regex baseline F1 0.36, Jev raw F1 0.85.

## 2026-09-28

### 04 · dbt semantic tests — tests warn instead of fail; packing recording ([#5](https://github.com/DataGobes/jev-demos/pull/5))

- **Changed** the four `jev_expect` tests to `severity: warn` (suggested in a comment on the LinkedIn
  post). A probability should flag a row for review, not stop a pipeline. Flagged rows are still
  stored with their `jev_p`, and scores are unchanged: the scorecard reads the stored rows, not dbt's
  exit code.
- **Added** `scripts/record_packing.sh`, a short recording of the packing speed-up. It shows a text
  recap of the logged live one-row-per-request run, one live run at 64 rows per request, and
  `scripts/packing_compare.py` putting both side by side with the speed-up computed from the two
  runs.

### 04 · dbt semantic tests — how far packing goes ([#4](https://github.com/DataGobes/jev-demos/pull/4))

- **Added** benchmark runs of the `nested` layout at 128, 256, 512 and 1024 rows per request, plus a
  "How far packing goes" section in [`docs/pack-layouts.md`](04-dbt-semantic-tests/docs/pack-layouts.md).
  Up to 256 rows per request the answers match pack 64 within run-to-run noise (drift 0.0053 vs 0.0049),
  with identical pass/fail decisions: 5 requests instead of 1,057.
- **Found** that the limit is tokens, not question count. A live probe accepted 1,700 questions in one
  request (62k tokens). The 500-row customers test in a single request exceeds the 64k-token budget
  and fails with `max_tokens_exceeded`; the run reports it as errors, never as a silent pass.
- **Fixed** `pack_bench.py report` crashing on a test whose rows all errored; it now shows `FAILED`.

## 2026-09-26

### Repo · animated README hero

- **Added** `assets/jev-hero.svg`, an animated hero at the top of the README: one 28 s loop, one
  scene per demo, English typed in on the left, Jev in the middle, typed values out on the right.
  Plain CSS animation, no JS; with reduced motion it shows one static scene.
- **Added** `assets/jev-hero-mobile.svg`, a portrait version of the same loop (cards stacked, Jev
  between them). The README serves it below 600 px wide, so on a phone the text renders at about
  0.9× instead of 0.37×.
- **Added** `assets/build_hero.py` (Python stdlib only), which generates the SVG. Scenes are data,
  so a new demo is one more entry. Every number drawn comes from a live, logged run and each scene
  prints its source: semsql's 780 / 913 / 595, VISUALIZE's 1.00 vs 0.57, and the dbt returns
  test's precision/recall against regex. Scene 01 has no logged per-post scores, so it shows none.

### 01 · Cringe-o-Meter, 02 · semsql, 03 · VISUALIZE — first three demos ([#2](https://github.com/DataGobes/jev-demos/pull/2))

- **Added** `01-cringe-o-meter/` (Next.js), `02-semsql/` (Python + DuckDB) and `03-visualize/`
  (Python backend + React frontend), each imported with its history from its own dev repo, and
  listed in the root README.
- **Added** a root `CLAUDE.md` with the demo-to-dev-repo map, the subtree workflow, and the
  pre-publish checks: a history-wide secret scan, and no `.env`, caches or `.claude/` committed.

### 04 · dbt semantic tests — packed requests without losing accuracy ([#1](https://github.com/DataGobes/jev-demos/pull/1))

- **Added** the `nested` pack layout, now the default `pack_style` for pack > 1. Each record goes
  inside its own question's structured instructions and the shared state is empty. Answers no longer
  depend on pack size: live gated runs pass at pack=32 and pack=64 with 35 / 18 requests instead of
  1,057, about 2 s instead of ~54 s, and $0.006 instead of $0.017.
- **Added** the `pack_style` setting (`profiles.yml`, `JEV_PACK_STYLE`). It is part of the cache key
  and shows in the run summary (`pack=32/nested`) and the scorecard header.
- **Added** `scripts/pack_bench.py` and `eval/pack_bench/`: a row-level benchmark that compares request
  layouts against pack=1, with the 23 live runs behind the decision.
- **Added** [`docs/pack-layouts.md`](04-dbt-semantic-tests/docs/pack-layouts.md): the analysis of why
  records in a shared state lose recall as packs grow (returns 1.00 → 0.42 at pack=32), why the shared
  state must be empty, and which borderline rows still move.
- **Unchanged:** pack=1 still sends one record per request, so the recorded demo numbers stand. No
  questions, thresholds, golden key or regex baseline were changed.

## 2026-09-25

### 04 · dbt semantic tests

- **Added** built-in captions, a title card and an end card to `scripts/record.sh`.
- **Fixed** the documented smoke test: `JEV_MODE=demo` was placed on `yes` instead of `record.sh`,
  so it could run live from a checkout that has a key.

## 2026-09-24

- **Added** the monorepo scaffold and the MIT license.
- **Added** 04 · dbt semantic tests (full history imported from its development repo). It runs four
  `jev_expect` tests written as English sentences, scored against a hidden answer key and a regex
  baseline; it passes the gate at pack=1.
