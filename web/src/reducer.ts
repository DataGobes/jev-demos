import type { PanelInfo, RunEvent, Spec } from "./stream";

export type AppState = {
  running: boolean; rows: Record<string, unknown>[]; spec: Spec | null; panels: PanelInfo[];
  timings: Partial<Record<"query" | "profile" | "enumerate" | "jev" | "render", number>>;
  usage: { input_tokens: number; usd: number } | null; scored: string | null; cache: string | null; simulated: boolean;
  rowNote: string | null; error: { stage: string; message: string } | null;
};
export type Action =
  | { type: "start" } | { type: "done" } | { type: "event"; event: RunEvent }
  | { type: "swap"; panelIndex: number; altId: string } | { type: "rendered"; ms: number }
  | { type: "health"; simulated: boolean };

export const initialState: AppState = { running: false, rows: [], spec: null, panels: [], timings: {}, usage: null,
  scored: null, cache: null, simulated: false, rowNote: null, error: null };

export function reduce(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "start": return { ...initialState, running: true, simulated: state.simulated };
    case "done": return { ...state, running: false };
    case "rendered": return { ...state, timings: { ...state.timings, render: Math.round(action.ms) } };
    case "health": return { ...state, simulated: action.simulated };
    case "swap": {
      const panel = state.panels[action.panelIndex];
      const alt = panel?.alternates.find((a) => a.id === action.altId);
      if (!state.spec || !panel || !alt) return state;
      const panels = state.panels.map((p, i) => i !== action.panelIndex ? p
        : { ...p, chosen: alt, alternates: [panel.chosen, ...p.alternates.filter((a) => a.id !== alt.id)] });
      const pid = `panel-${action.panelIndex}`, lid = `leaf-${action.panelIndex}`;
      const elements = { ...state.spec.elements, [lid]: alt.element,
        [pid]: { ...state.spec.elements[pid], props: { ...state.spec.elements[pid].props, title: alt.title, p: alt.p } } };
      return { ...state, panels, spec: { ...state.spec, elements } };
    }
    case "event": {
      const e = action.event;
      if (e.type === "parsed") return state;
      if (e.type === "error") return { ...state, error: { stage: e.stage, message: e.message } };
      if (e.type === "result") {
        const spec: Spec = { root: "table", elements: { table: { type: "Table", props: { columns: e.columns, maxRows: 200 }, children: [] } } };
        return { ...state, rows: e.rows, spec, timings: { query: e.ms.query },
          rowNote: e.truncated ? `showing ${e.rows.length.toLocaleString()} of ${e.row_count.toLocaleString()} rows` : null };
      }
      return { ...state, spec: e.spec, panels: e.panels, timings: { ...state.timings, ...e.ms }, usage: e.usage,
        scored: e.scored, cache: e.cache, simulated: e.simulated };
    }
  }
}
