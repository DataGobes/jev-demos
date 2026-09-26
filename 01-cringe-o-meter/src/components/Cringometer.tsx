"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DIMENSIONS, getDimension } from "@/lib/dimensions";
import { computeComposite, topContributors, verdictFor } from "@/lib/composite";
import { EXAMPLE_POSTS } from "@/lib/examples";
import {
  MAX_POST_LENGTH,
  MIN_POST_LENGTH,
  type JudgeErrorBody,
  type JudgeResponseBody,
} from "@/lib/types";
import { CompositeDial } from "./CompositeDial";
import { DimensionCard } from "./DimensionCard";

const DEBOUNCE_MS = 400;

function initialWeights(): Record<string, number> {
  return Object.fromEntries(DIMENSIONS.map((d) => [d.id, d.defaultWeight]));
}

export function Cringometer() {
  const [text, setText] = useState("");
  const [weights, setWeights] = useState<Record<string, number>>(initialWeights);
  const [result, setResult] = useState<JudgeResponseBody | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const runJudge = useCallback(async (post: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const thisRequestId = ++requestIdRef.current;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/judge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ post }),
        signal: controller.signal,
      });

      // A newer request superseded this one while we were in flight — drop it.
      if (thisRequestId !== requestIdRef.current) return;

      const json = (await res.json()) as JudgeResponseBody | JudgeErrorBody;

      if (thisRequestId !== requestIdRef.current) return;

      if (!res.ok) {
        setError("error" in json ? json.error : `Request failed (${res.status}).`);
        setResult(null);
        return;
      }

      setResult(json as JudgeResponseBody);
    } catch (err) {
      if (thisRequestId !== requestIdRef.current) return;
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Network error.");
    } finally {
      if (thisRequestId === requestIdRef.current) setLoading(false);
    }
  }, []);

  /**
   * Sets the draft text and, for the user-initiated "too short" case, resets
   * stale results right away. This runs in the event handler (not the effect
   * below) so it's a direct response to user input rather than a synchronous
   * setState inside an effect body.
   */
  const updateText = useCallback((next: string) => {
    setText(next);
    if (next.trim().length < MIN_POST_LENGTH) {
      abortRef.current?.abort();
      requestIdRef.current += 1;
      setResult(null);
      setError(null);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const trimmed = text.trim();
    if (trimmed.length < MIN_POST_LENGTH) return;

    const timer = setTimeout(() => {
      void runJudge(trimmed);
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [text, runJudge]);

  const values = useMemo(() => {
    if (!result) return {};
    return Object.fromEntries(
      Object.entries(result.dimensions).map(([id, d]) => [id, d.value]),
    );
  }, [result]);

  const composite = useMemo(() => computeComposite(values, weights), [values, weights]);
  const verdict = useMemo(() => verdictFor(composite), [composite]);
  const hasResult = result !== null;

  const handleWeightChange = useCallback((id: string, weight: number) => {
    setWeights((prev) => ({ ...prev, [id]: weight }));
  }, []);

  const handleCopy = useCallback(async () => {
    const top3 = topContributors(values, weights, 3)
      .map((id) => getDimension(id)?.label ?? id)
      .join(", ");
    const pct = Math.round(composite * 100);
    const summary = `LinkedIn Cringe-o-Meter: ${pct}/100 — "${verdict.label}"\nTop offenders: ${top3 || "n/a"}\nJudged by Jev (TypeSafe System One).`;

    try {
      await navigator.clipboard.writeText(summary);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Couldn't access the clipboard — copy the result manually.");
    }
  }, [values, weights, composite, verdict.label]);

  const charCount = text.length;
  const tooShort = text.trim().length > 0 && text.trim().length < MIN_POST_LENGTH;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 px-4 py-10 sm:px-6 lg:px-8">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium tracking-wide text-muted uppercase">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            Powered by Jev
          </span>
          {result?.demo && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent-soft px-3 py-1 text-xs font-semibold tracking-wide text-accent uppercase">
              Demo mode &mdash; heuristic scores, not Jev
            </span>
          )}
        </div>
        <h1 className="font-display text-4xl leading-[1.05] font-extrabold tracking-tight text-balance sm:text-5xl">
          LinkedIn Cringe-o-Meter
        </h1>
        <p className="max-w-xl text-base text-muted">
          Paste a draft post. Eight parallel judgments come back from Jev,
          TypeSafe&apos;s System One model &mdash; one narrow question each &mdash;
          and you reweight the composite live, with zero extra API calls.
        </p>
      </header>

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_POSTS.map((example) => (
            <button
              key={example.id}
              type="button"
              onClick={() => updateText(example.post)}
              className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-sm text-foreground/90 transition-colors hover:border-accent/60 hover:text-accent"
            >
              {example.label}
            </button>
          ))}
        </div>

        <div className="relative">
          <textarea
            value={text}
            onChange={(event) => updateText(event.target.value)}
            maxLength={MAX_POST_LENGTH}
            placeholder={`Paste your LinkedIn draft here… ("I'm humbled to announce…")`}
            rows={8}
            className="w-full resize-y rounded-2xl border border-border bg-surface p-4 text-base leading-relaxed text-foreground placeholder:text-muted/70 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
          />
          <div className="pointer-events-none absolute right-4 bottom-3 flex items-center gap-2 text-xs">
            {loading && (
              <span className="font-mono-num flex items-center gap-1.5 text-accent">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                judging&hellip;
              </span>
            )}
            <span
              className={`font-mono-num ${
                tooShort ? "text-accent" : "text-muted"
              }`}
            >
              {charCount}/{MAX_POST_LENGTH}
            </span>
          </div>
        </div>
        {tooShort && (
          <p className="text-xs text-muted">
            Needs at least {MIN_POST_LENGTH} characters before Jev will judge it.
          </p>
        )}
        {error && (
          <p className="rounded-lg border border-accent/40 bg-accent-soft px-3 py-2 text-sm text-accent">
            {error}
          </p>
        )}
      </section>

      <section className="grid grid-cols-1 gap-8 lg:grid-cols-[280px_1fr]">
        <div className="flex flex-col items-center gap-5 rounded-2xl border border-border bg-surface p-6 lg:sticky lg:top-8 lg:h-fit">
          <CompositeDial value={composite} label={verdict.label} blurb={verdict.blurb} />

          <div className="w-full border-t border-border pt-4 text-center">
            {result ? (
              <p className="font-mono-num text-sm text-foreground">
                judged in{" "}
                <span className="font-semibold text-accent">
                  {result.latencyMs} ms
                </span>{" "}
                &middot; {DIMENSIONS.length} questions
              </p>
            ) : (
              <p className="text-sm text-muted">
                {loading ? "waiting on Jev…" : "no judgment yet"}
              </p>
            )}
            {result?.usage && (
              <p className="mt-1 text-xs text-muted">
                {result.usage.input_tokens + result.usage.output_tokens} tokens
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={handleCopy}
            disabled={!hasResult}
            className="w-full rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
          >
            {copied ? "Copied!" : "Copy result"}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {DIMENSIONS.map((dimension) => (
            <DimensionCard
              key={dimension.id}
              dimension={dimension}
              value={values[dimension.id]}
              weight={weights[dimension.id]}
              onWeightChange={(weight) => handleWeightChange(dimension.id, weight)}
              loading={loading}
            />
          ))}
        </div>
      </section>

      <footer className="mt-auto border-t border-border pt-6 text-center text-xs text-muted">
        Judgments by Jev (TypeSafe System One). No text is generated.
      </footer>
    </div>
  );
}
