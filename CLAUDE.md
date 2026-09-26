# CLAUDE.md

Shared, public showcase repo (`github.com/DataGobes/jev-demos`) for small demos of TypeSafe's Jev.
Each numbered folder is one self-contained demo with its own README, dependencies and, usually,
its own `CLAUDE.md`. **Read the demo's own `CLAUDE.md` before working inside a demo folder.**

## How demos get here: git subtree, one-way

Each demo is developed in its own local repo and imported with its full history under a
numbered prefix. The dev repo is the source of truth: change the demo there, then pull it in.

| folder | dev repo (local) | branch imported |
|---|---|---|
| `01-cringe-o-meter/` | `~/Projects/jev-demo` | `main` |
| `02-semsql/` | `~/Projects/jev-demo-2` | `main` |
| `03-visualize/` | `~/Projects/jev-demo-3` | `feat/jev-visualize` |
| `04-dbt-semantic-tests/` | `~/Projects/jev-demo-4` | `main` (or the feature branch being PR'd) |
| `05-dbt-v2-checks/` | none: a research spike built in this repo | n/a (edit in place; `git subtree split` if it becomes a demo) |

- Add a demo: `git subtree add --prefix=NN-name <dev-repo-path> <branch>`
- Update a demo: commit in the dev repo, then
  `git subtree pull --prefix=NN-name <dev-repo-path> <branch> -m "Update NN-name: <what changed>"`
- Don't use `--squash`: the demos' history is part of what's shared.
- Don't edit files inside a demo folder here. The next `subtree pull` would conflict with the dev
  repo. The exception is a fix that must also go back (`git subtree push`); ask first.

## Before anything leaves this machine

This repo is public and its history is permanent. Before importing or pulling a demo:
- Scan the dev repo's **whole history** (every blob reachable from `--all`, plus commit messages)
  for keys and tokens, not just the current files. Report locations and pattern names only, never
  the values.
- Never commit `.env`, `.env.local`, caches (`*.sqlite`, `*.duckdb`), `.venv/`, `node_modules/`, or
  `.claude/` (local session and preview config). Check each demo's `.gitignore` covers them.
- Never read, print or log `.env` or `TYPESAFE_API_KEY`.
- Don't commit a dev repo's uncommitted work for its owner: import what's committed and say what
  was left out.

## Conventions

- Work on a branch and open a PR against `main`; don't push to `main` directly.
- Every change that lands updates `CHANGELOG.md` (newest first, dated, one `###` per demo touched).
- Adding or renaming a demo updates the table in the root `README.md`.
- Numbers in READMEs, changelog entries and posts come from live, logged runs. A demo's `SIMULATED`
  / demo-mode output is never quoted as a result.
- Each demo runs from its own folder (`cd NN-name`). There is no root-level build, test or
  dependency setup.
