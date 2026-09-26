"use client";

import type { Dimension } from "@/lib/dimensions";
import { useAnimatedValue } from "@/lib/useAnimatedValue";
import { DimensionIcon } from "./icons";

interface DimensionCardProps {
  dimension: Dimension;
  /** Normalised 0..1 value from the latest judgment, or undefined before one exists. */
  value: number | undefined;
  weight: number;
  onWeightChange: (weight: number) => void;
  loading: boolean;
}

export function DimensionCard({
  dimension,
  value,
  weight,
  onWeightChange,
  loading,
}: DimensionCardProps) {
  const animated = useAnimatedValue(value ?? 0);
  const pct = Math.round(animated * 100);
  const hasValue = value !== undefined;

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-raised text-accent">
          <DimensionIcon icon={dimension.icon} className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="font-display text-base leading-tight font-semibold">
              {dimension.label}
            </h3>
            <span className="font-mono-num shrink-0 text-sm text-muted">
              {hasValue ? `${pct}%` : "—"}
            </span>
          </div>
          <p className="mt-0.5 truncate text-xs text-muted">{dimension.tagline}</p>
        </div>
      </div>

      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-raised">
        <div
          className={`h-full rounded-full bg-accent ${loading ? "opacity-60" : ""}`}
          style={{
            width: `${hasValue ? pct : 0}%`,
            transition: "width 550ms cubic-bezier(0.22, 1, 0.36, 1)",
          }}
        />
      </div>

      <label className="flex items-center gap-2 text-xs text-muted">
        <span className="w-12 shrink-0">weight</span>
        <input
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={weight}
          onChange={(event) => onWeightChange(Number(event.target.value))}
          className="h-1 flex-1 accent-[var(--accent)]"
          aria-label={`Weight for ${dimension.label}`}
        />
        <span className="font-mono-num w-9 shrink-0 text-right">
          {weight.toFixed(1)}&times;
        </span>
      </label>
    </div>
  );
}
