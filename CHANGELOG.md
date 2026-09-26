# Changelog

Notable changes to the demos in this repo, newest first. Each entry names the demo it touches.
The demos aren't versioned, so entries are dated by the day they land on `main`. Numbers quoted
here come from live, logged runs; see each demo's own docs for the full record.

## 2026-09-26

### 01 · Cringe-o-Meter, 02 · semsql, 03 · VISUALIZE — first three demos

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
