import type { AltEntry, SpecElement } from "./rows";

export type Spec = { root: string; elements: Record<string, SpecElement> };
export type PanelInfo = { intent: string; match: "strong" | "weak" | "none"; chosen: AltEntry; alternates: AltEntry[] };
export type RunEvent =
  | { type: "parsed"; sql: string; intents: string[] | null }
  | { type: "result"; columns: string[]; rows: Record<string, unknown>[]; row_count: number; truncated: boolean; ms: { query: number } }
  | { type: "spec"; spec: Spec; panels: PanelInfo[]; ms: { profile: number; enumerate: number; jev: number };
      usage: { input_tokens: number; usd: number }; scored: string; cache: string; simulated: boolean }
  | { type: "error"; stage: string; message: string };

export async function* runQuery(sql: string, signal?: AbortSignal): AsyncGenerator<RunEvent> {
  const resp = await fetch("/run", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ sql }), signal });
  if (!resp.ok || !resp.body) throw new Error(`server returned ${resp.status}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) yield JSON.parse(line) as RunEvent;
    }
    if (done) break;
  }
}
