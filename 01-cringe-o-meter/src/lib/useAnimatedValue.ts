import { useEffect, useRef, useState } from "react";

/**
 * Eases a number toward `target` over `durationMs` using requestAnimationFrame,
 * so meters and the composite dial glide between judgments instead of
 * snapping. Only used by client components (Cringometer.tsx renders it).
 */
export function useAnimatedValue(target: number, durationMs = 650): number {
  const [display, setDisplay] = useState(target);
  const displayRef = useRef(target);
  const rafRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const from = displayRef.current;
    const diff = target - from;

    if (Math.abs(diff) < 0.0005) {
      displayRef.current = target;
      setDisplay(target);
      return;
    }

    let start: number | null = null;

    function tick(ts: number) {
      if (start === null) start = ts;
      const progress = Math.min(1, (ts - start) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = from + diff * eased;
      displayRef.current = next;
      setDisplay(next);
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick);
      }
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== undefined) cancelAnimationFrame(rafRef.current);
    };
  }, [target, durationMs]);

  return display;
}
