import type { NoulResponse, ScoreResponse } from "@typesafe-ai/sdk";

/**
 * Shared response shape for POST /api/judge, used by both the route handler
 * and the client so the two never drift out of sync. Only type-level imports
 * are pulled from the SDK here, so this file is safe to import from client
 * components (nothing SDK-runtime ships to the browser).
 */
export interface DimensionResult {
  /** Normalised 0..1 value: Score answers divided by (levels - 1), Noul answers as-is. */
  value: number;
  /** The untouched answer from the model (or the demo-mode heuristic stand-in). */
  raw: NoulResponse | ScoreResponse;
}

export interface JudgeResponseBody {
  demo: boolean;
  latencyMs: number;
  model?: string;
  usage?: { input_tokens: number; output_tokens: number };
  dimensions: Record<string, DimensionResult>;
}

export interface JudgeErrorBody {
  error: string;
}

export const MIN_POST_LENGTH = 20;
export const MAX_POST_LENGTH = 3000;
