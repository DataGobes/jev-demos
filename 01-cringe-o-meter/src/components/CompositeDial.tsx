"use client";

import { useAnimatedValue } from "@/lib/useAnimatedValue";

interface CompositeDialProps {
  /** Composite score, 0..1. */
  value: number;
  label: string;
  blurb: string;
}

const SIZE = 208;
const STROKE = 13;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function CompositeDial({ value, label, blurb }: CompositeDialProps) {
  const animated = useAnimatedValue(value);
  const pct = Math.round(animated * 100);
  const offset = CIRCUMFERENCE * (1 - Math.max(0, Math.min(1, animated)));

  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative" style={{ width: SIZE, height: SIZE }}>
        <svg width={SIZE} height={SIZE} className="-rotate-90">
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            stroke="var(--border)"
            strokeWidth={STROKE}
            fill="none"
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            stroke="var(--accent)"
            strokeWidth={STROKE}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono-num text-6xl font-semibold tabular-nums">
            {pct}
          </span>
          <span className="text-[11px] uppercase tracking-[0.2em] text-muted">
            / 100 cringe
          </span>
        </div>
      </div>
      <div className="max-w-[260px] text-center">
        <p className="font-display text-2xl font-bold text-accent">{label}</p>
        <p className="mt-1 text-sm text-muted">{blurb}</p>
      </div>
    </div>
  );
}
