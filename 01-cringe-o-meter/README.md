# LinkedIn Cringe-o-Meter

A small, screenshot-bait demo app: paste a LinkedIn post draft, and eight
parallel judgments come back from **Jev**, [TypeSafe](https://typesafe.ai)'s
System One model, each answering one narrow question about the post
(humblebrag, engagement bait, fake vulnerability, buzzword density, broetry
formatting, the "I'm humbled to announce" opener, mundane/toddler life
lessons, unsolicited hustle advice). A live meter shows every dimension plus
one big composite "cringe score," and weight sliders let you reweight the
composite **without** calling the API again — everything recomputes from the
cached raw answers already in the browser.

## Run it

```bash
pnpm install
pnpm dev
```

Open http://localhost:3000.

## Environment

Copy `.env.example` to `.env.local` and set your key to call the real model:

```
TYPESAFE_API_KEY=sk-...
```

**Without a key**, the app still works: `src/app/api/judge/route.ts` falls
back to deterministic regex/keyword heuristics per dimension and returns
`demo: true` in the response. The UI shows a clearly visible "demo mode —
heuristic scores, not Jev" badge whenever that flag is set, so it's never
ambiguous which mode produced a given score.

## How the composite works

Every dimension is judged with a TypeSafe primitive chosen by whether degree
or presence matters (see `src/lib/dimensions.ts`, the single source of truth
both the server route and the UI import from):

- **Score** (4 ordered levels, concrete situational descriptions) for
  humblebrag, engagement bait, fake vulnerability, and buzzword density. The
  raw answer's `score` (a probability-weighted mean across the levels) is
  divided by `levels - 1` to normalise it to `0..1`.
- **Noul** (a yes/no presence probability) for broetry formatting, the
  stock "I'm humbled/thrilled/honored to announce" opener, mundane/toddler
  life lessons, and unsolicited hustle advice. The raw `noul` value is
  already `0..1`, so it's used as-is.

All 8 questions are sent to `client.systemOne()` in a single request and run
in parallel; they can't see each other's answers, so each question's
`instructions` fully explains what it's judging.

The server (`src/app/api/judge/route.ts`) returns each dimension's
normalised `0..1` value alongside its raw answer, latency, and (for real Jev
calls) token usage. The client never re-normalises or re-calls the API when
you move a slider — `src/lib/composite.ts` recombines the already-cached
`0..1` values. Cringe doesn't average out (three maxed dimensions are cringe
even when five are clean), so the composite leans on the worst offences:

```
mean      = Σ(value_i × weight_i) / Σ(weight_i)
top       = weighted mean of the highest values, up to 3 units of slider weight
composite = 0.8 × top + 0.2 × mean
```

Sliders run `0..2` (default `1`), so a dimension can be zeroed out, weighted
normally, or doubled. `verdictFor(score)` in `src/lib/composite.ts` maps the
composite to one of seven verdict tiers.

## Recording mode

Add `?record=1` to the URL (e.g. `http://localhost:3000/?record=1`) to enable
an overlay for making captioned screen recordings. It's inert without the
flag — no listener is attached and no caption markup is rendered.

Key bindings (all use `Alt`/`Option` so they never collide with typing in the
post textarea):

| Keys                 | Effect                        |
| -------------------- | ------------------------------ |
| `Alt`/`Option` + `1`–`6` | Show caption 1–6 (see `src/lib/captions.ts`) |
| `Alt`/`Option` + `0`     | Hide the caption               |
| `Escape`                 | Hide the caption (no modifier needed) |

There's no on-screen hint of these bindings — that's intentional, so nothing
shows up in the recording.

## Stack

Next.js (App Router, TypeScript), Tailwind CSS v4, `@typesafe-ai/sdk`
(server-only — the API key never reaches the browser). Dark, editorial,
single-accent design with Bricolage Grotesque (display) and JetBrains Mono
(numbers) via `next/font`.
