import { ActionProvider, Renderer, StateProvider, VisibilityProvider } from "@json-render/react";
import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { Editor } from "./Editor";
import { EXAMPLES } from "./examples";
import { initialState, reduce } from "./reducer";
import { registry } from "./registry";
import { PanelActionsContext, RowsContext } from "./rows";
import { runQuery } from "./stream";
import { TimingBar } from "./TimingBar";
import { useRun } from "./useRun";

export default function App() {
  const [sql, setSql] = useState(EXAMPLES[0].sql);
  const [s, dispatch] = useReducer(reduce, initialState);
  const runSql = useRun(dispatch, runQuery);
  // A newer run always supersedes an in-flight older one (useRun aborts it),
  // so this is safe to call unconditionally from both the button and ⌘↵.
  const run = useCallback(() => runSql(sql), [runSql, sql]);

  useEffect(() => {
    const onRendered = (e: Event) => dispatch({ type: "rendered", ms: (e as CustomEvent<number>).detail });
    window.addEventListener("jevviz:rendered", onRendered);
    return () => window.removeEventListener("jevviz:rendered", onRendered);
  }, []);

  const actions = useMemo(() => ({
    alternates: (i: number) => s.panels[i]?.alternates ?? [],
    swap: (panelIndex: number, altId: string) => dispatch({ type: "swap", panelIndex, altId }),
  }), [s.panels]);

  return (
    <div className="app">
      <aside>
        <h1>Jev <code>VISUALIZE</code></h1>
        <Editor value={sql} onChange={setSql} onRun={run} />
        <div className="controls">
          <select aria-label="examples" onChange={(e) => setSql(EXAMPLES[Number(e.target.value)].sql)}>
            {EXAMPLES.map((ex, i) => <option key={ex.label} value={i}>{ex.label}</option>)}
          </select>
          <button onClick={run} disabled={s.running}>{s.running ? "Running…" : "Run ⌘↵"}</button>
        </div>
        {s.error && <p className={`error stage-${s.error.stage}`} role="alert">{s.error.stage}: {s.error.message}</p>}
      </aside>
      <main>
        {s.spec ? (
          <RowsContext.Provider value={s.rows}>
            <PanelActionsContext.Provider value={actions}>
              <StateProvider initialState={{}}>
                <VisibilityProvider>
                  <ActionProvider>
                    <Renderer spec={s.spec} registry={registry} />
                  </ActionProvider>
                </VisibilityProvider>
              </StateProvider>
            </PanelActionsContext.Provider>
          </RowsContext.Provider>
        ) : <p className="empty">Run a query. End it with <code>VISUALIZE '…'</code> to let Jev pick the chart.</p>}
      </main>
      <TimingBar s={s} />
    </div>
  );
}
