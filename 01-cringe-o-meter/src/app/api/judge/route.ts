import { NextRequest, NextResponse } from "next/server";
import {
  APIError,
  APIUserAbortError,
  TypeSafeClient,
  noul,
  score,
  type NoulResponse,
  type Questions,
  type ScoreResponse,
} from "@typesafe-ai/sdk";
import { DIMENSIONS, SCORE_LEVELS, type Dimension } from "@/lib/dimensions";
import {
  MAX_POST_LENGTH,
  MIN_POST_LENGTH,
  type DimensionResult,
  type JudgeResponseBody,
} from "@/lib/types";

export const runtime = "nodejs";

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}

function buildQuestions(): Questions {
  const questions: Questions = {};
  for (const dim of DIMENSIONS) {
    questions[dim.id] =
      dim.primitive === "noul"
        ? noul(dim.instructions, dim.criteria)
        : score(dim.instructions, dim.criteria);
  }
  return questions;
}

function normalise(raw: NoulResponse | ScoreResponse): number {
  if (raw.type === "noul") return raw.noul;
  return raw.score / (SCORE_LEVELS - 1);
}

// ---------------------------------------------------------------------------
// Demo mode: deterministic regex/keyword heuristics used only when
// TYPESAFE_API_KEY is absent, so the app is still explorable without a key.
// These are intentionally crude approximations of the real Jev judgments.
// ---------------------------------------------------------------------------

function hitRatio(text: string, patterns: RegExp[], saturateAt: number): number {
  const hits = patterns.reduce((sum, re) => sum + (re.test(text) ? 1 : 0), 0);
  return clamp01(hits / saturateAt);
}

const BUZZWORDS = [
  "synerg", "circle back", "move the needle", "growth mindset", "thought leader",
  "disrupt", "unlock value", "double-click", "double click", "bandwidth",
  "north star", "level up", "game-changer", "game changer", "low-hanging fruit",
  "paradigm", "ecosystem", "value-add", "value add", "leverage", "streamline",
  "actionable", "deep dive", "touch base", "paradigm shift", "best-in-class",
];

function heuristicValue(dim: Dimension, text: string): number {
  const lower = text.toLowerCase();

  switch (dim.id) {
    case "humblebrag":
      return hitRatio(
        lower,
        [
          /humbled to/i, /small brain/i, /don'?t know how/i, /still confused/i,
          /not usually one to share/i, /humble ?brag/i, /can'?t believe (i|they)/i,
        ],
        3,
      );

    case "engagementBait":
      return hitRatio(
        lower,
        [
          /agree\?/i, /comment (yes|below|👍|🔥)/i, /type (yes|🔥)/i,
          /repost if/i, /tag (a|someone)/i, /am i wrong\?/i, /like if/i, /drop a/i,
        ],
        3,
      );

    case "fakeVulnerability":
      return hitRatio(
        lower,
        [
          /diagnosed/i, /divorce/i, /lost my (job|mother|father|dad|mom|home)/i,
          /didn'?t know if i('| )?(d|would)/i, /breakdown/i, /hospital/i,
          /rock bottom/i, /\bcried\b/i,
        ],
        3,
      );

    case "buzzwordDensity": {
      const wordCount = Math.max(1, lower.split(/\s+/).filter(Boolean).length);
      const buzzwordHits = BUZZWORDS.reduce(
        (sum, phrase) => sum + (lower.includes(phrase) ? 1 : 0),
        0,
      );
      return clamp01(buzzwordHits / Math.max(3, wordCount / 12));
    }

    case "broetry": {
      const lines = text.split(/\n+/).map((l) => l.trim()).filter(Boolean);
      if (lines.length < 3) return 0.05;
      const shortLines = lines.filter((l) => l.split(/\s+/).length <= 6).length;
      return clamp01(shortLines / lines.length);
    }

    case "stockOpener":
      return /^\s*(i'?m|i am)\s+(humbled|thrilled|honored|excited)\b/i.test(text) ||
        /\b(excited|thrilled|honored|humbled) to (announce|share)\b/i.test(lower)
        ? 0.92
        : 0.05;

    case "mundaneLesson": {
      const child = /\bmy (son|daughter|toddler|kid|kids|\d-year-old|niece|nephew)\b/i.test(lower);
      const mundane = /\b(coffee order|traffic jam|grocery|elevator|waiting room|uber ride|gym)\b/i.test(lower);
      const lesson = /\b(taught me|lesson|reminded me|realized|realised)\b/i.test(lower);
      if ((child || mundane) && lesson) return 0.9;
      if (lesson) return 0.3;
      return 0.05;
    }

    case "hustleAdvice":
      return hitRatio(
        lower,
        [
          /wake up at [45]/i, /sleep is for/i, /work(ed)? weekends/i,
          /if you want it bad enough/i, /nobody('s| is) coming to save you/i,
          /\bhustle\b/i, /no days off/i, /\bgrind\b/i,
        ],
        2,
      );

    default:
      return 0;
  }
}

function heuristicRaw(dim: Dimension, value: number): NoulResponse | ScoreResponse {
  if (dim.primitive === "noul") {
    return { type: "noul", noul: clamp01(value) };
  }

  const levels = SCORE_LEVELS;
  const rawScore = clamp01(value) * (levels - 1);
  const nearest = Math.round(rawScore);
  const probabilities: Record<string, number> = {};
  const legend: Record<string, string> = {};
  for (let i = 0; i < levels; i++) {
    probabilities[String(i)] = i === nearest ? 0.7 : 0.3 / (levels - 1);
    legend[String(i)] = dim.criteria[i];
  }

  return {
    type: "score",
    score: rawScore,
    confidence: 0.55,
    probabilities: probabilities as ScoreResponse["probabilities"],
    legend: legend as ScoreResponse["legend"],
  };
}

function runDemoHeuristics(text: string): Record<string, DimensionResult> {
  const dimensions: Record<string, DimensionResult> = {};
  for (const dim of DIMENSIONS) {
    const value = clamp01(heuristicValue(dim, text));
    dimensions[dim.id] = { value, raw: heuristicRaw(dim, value) };
  }
  return dimensions;
}

// ---------------------------------------------------------------------------

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Request body must be valid JSON." },
      { status: 400 },
    );
  }

  const post =
    typeof body === "object" && body !== null && "post" in body
      ? (body as { post: unknown }).post
      : undefined;

  if (typeof post !== "string") {
    return NextResponse.json(
      { error: "`post` must be a string." },
      { status: 400 },
    );
  }

  const trimmed = post.trim();
  if (trimmed.length < MIN_POST_LENGTH) {
    return NextResponse.json(
      { error: `Post must be at least ${MIN_POST_LENGTH} characters.` },
      { status: 400 },
    );
  }
  if (trimmed.length > MAX_POST_LENGTH) {
    return NextResponse.json(
      { error: `Post must be at most ${MAX_POST_LENGTH} characters.` },
      { status: 400 },
    );
  }

  const apiKey = process.env.TYPESAFE_API_KEY;

  if (!apiKey) {
    const start = performance.now();
    const dimensions = runDemoHeuristics(trimmed);
    const latencyMs = Math.round(performance.now() - start);
    const responseBody: JudgeResponseBody = { demo: true, latencyMs, dimensions };
    return NextResponse.json(responseBody, { status: 200 });
  }

  const client = new TypeSafeClient({ apiKey });
  const questions = buildQuestions();

  try {
    const start = performance.now();
    const result = await client.systemOne(
      { state: { post: trimmed }, questions },
      { signal: req.signal },
    );
    const latencyMs = Math.round(performance.now() - start);

    const dimensions: Record<string, DimensionResult> = {};
    for (const dim of DIMENSIONS) {
      const raw = result.answers[dim.id] as NoulResponse | ScoreResponse;
      dimensions[dim.id] = { value: clamp01(normalise(raw)), raw };
    }

    const responseBody: JudgeResponseBody = {
      demo: false,
      latencyMs,
      model: result.model,
      usage: result.usage,
      dimensions,
    };

    return NextResponse.json(responseBody, { status: 200 });
  } catch (err) {
    if (err instanceof APIUserAbortError || (err instanceof Error && err.name === "AbortError")) {
      // Client cancelled (debounce superseded this request); nothing to report.
      return NextResponse.json({ error: "Request aborted." }, { status: 499 });
    }

    if (err instanceof APIError) {
      console.error("TypeSafe API error", err.status, err.message);
      return NextResponse.json(
        { error: `TypeSafe API error: ${err.message}` },
        { status: 502 },
      );
    }

    console.error("Unexpected error while judging post", err);
    return NextResponse.json(
      { error: "Unexpected error while judging the post." },
      { status: 500 },
    );
  }
}
