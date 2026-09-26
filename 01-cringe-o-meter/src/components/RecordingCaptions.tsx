"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CAPTIONS } from "@/lib/captions";

/** Matches the caption bar's CSS transition duration (see className below). */
const TRANSITION_MS = 200;

/**
 * Recording-mode caption overlay for making captioned screen recordings.
 *
 * Only active when the URL has `?record=1` — otherwise this renders nothing
 * and attaches no listeners, so normal usage of the app is unaffected.
 *
 * Alt/Option+1..6 show a caption, Alt/Option+0 or Escape hides it. Digits use
 * the Alt/Option modifier (checked via `event.code`, since Option+digit
 * produces a different `event.key` on macOS) so they never collide with
 * typing in the post textarea, which keeps working normally either way.
 */
export function RecordingCaptions() {
  const searchParams = useSearchParams();
  const active = searchParams.get("record") === "1";

  const [text, setText] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);
  const currentTextRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearPendingTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const showCaption = useCallback(
    (key: string) => {
      const caption = CAPTIONS.find((c) => c.key === key);
      if (!caption) return;

      clearPendingTimer();

      if (currentTextRef.current === null) {
        // Nothing on screen yet: fade straight in, no need to fade out first.
        currentTextRef.current = caption.text;
        setText(caption.text);
        setVisible(true);
      } else {
        // Cross-fade: fade the current line out, then swap text and fade in.
        setVisible(false);
        timerRef.current = setTimeout(() => {
          currentTextRef.current = caption.text;
          setText(caption.text);
          setVisible(true);
        }, TRANSITION_MS);
      }
    },
    [clearPendingTimer],
  );

  const hideCaption = useCallback(() => {
    clearPendingTimer();
    setVisible(false);
    timerRef.current = setTimeout(() => {
      currentTextRef.current = null;
      setText(null);
    }, TRANSITION_MS);
  }, [clearPendingTimer]);

  useEffect(() => clearPendingTimer, [clearPendingTimer]);

  useEffect(() => {
    if (!active) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        hideCaption();
        return;
      }

      if (!event.altKey) return;

      if (event.code === "Digit0") {
        event.preventDefault();
        hideCaption();
        return;
      }

      const match = /^Digit([1-6])$/.exec(event.code);
      if (match) {
        event.preventDefault();
        showCaption(match[1]);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [active, showCaption, hideCaption]);

  if (!active) return null;

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-[10%] z-50 flex justify-center px-4"
    >
      <div
        className={`max-w-[90vw] rounded-2xl border-l-4 border-accent bg-surface/95 px-6 py-4 text-center shadow-2xl shadow-black/40 backdrop-blur-sm transition-all duration-200 ease-out ${
          visible ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"
        }`}
      >
        <p className="text-balance font-display text-2xl leading-snug font-bold text-foreground sm:text-3xl">
          {text}
        </p>
      </div>
    </div>
  );
}
