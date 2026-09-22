import { ActionProvider, Renderer, StateProvider, VisibilityProvider } from "@json-render/react";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { parseAutoplay, splitVisualize } from "./autoplay";
import { Editor } from "./Editor";
import { EXAMPLES } from "./examples";
import { fetchSimulated } from "./health";
import { initialState, reduce } from "./reducer";
import { registry } from "./registry";
import { PanelActionsContext, RowsContext } from "./rows";
import { runQuery } from "./stream";
import { TimingBar } from "./TimingBar";
import { useRun } from "./useRun";

export default function App() {
  const auto = useMemo(() => parseAutoplay(window.location.search), []);
  const [exampleIndex, setExampleIndex] = useState(0);
  // Autoplay opens on a blank editor so a recording can start on a clean frame.
  const [sql, setSql] = useState(auto ? "" : EXAMPLES[0].sql);
  const [s, dispatch] = useReducer(reduce, initialState);
  const runSql = useRun(dispatch, runQuery);
  // A newer run always supersedes an in-flight older one (useRun aborts it),
  // so this is safe to call unconditionally from both the button and ⌘↵.
  const run = useCallback(() => runSql(sql), [runSql, sql]);
  const pickExample = (i: number) => { setExampleIndex(i); setSql(EXAMPLES[i].sql); };

  // The sequencer reads panel count for the dwell; a ref avoids a stale closure.
  const panelCount = useRef(0);
  panelCount.current = s.panels.length;

  useEffect(() => {
    if (!auto) return;
    document.documentElement.style.setProperty("zoom", String(auto.scale));
    const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
    // Subscribed *before* run() so a warm-cache chart (paints in ~50ms) can't be missed.
    const painted = () => new Promise<void>((r) => window.addEventListener("jevviz:rendered", () => r(), { once: true }));
    const loop = EXAMPLES.filter((e) => !e.skipInLoop);
    let cancelled = false;
    void (async () => {
      await sleep(auto.lead);
      for (let n = 0; !cancelled; n++) {
        const ex = loop[n % loop.length];
        const { head, tail } = splitVisualize(ex.sql);
        setExampleIndex(EXAMPLES.indexOf(ex));
        setSql(head);
        await sleep(auto.pause);
        for (let i = 1; i <= tail.length && !cancelled; i++) { setSql(head + tail.slice(0, i)); await sleep(auto.type); }
        if (cancelled) return;
        const done = painted();
        runSql(ex.sql);
        // 8s ceiling only matters if a run errors and nothing ever paints.
        await Promise.race([done, sleep(8000)]);
        await sleep(auto.dwell + Math.max(0, panelCount.current - 1) * auto.extra);
      }
    })();
    return () => { cancelled = true; document.documentElement.style.removeProperty("zoom"); };
  }, [auto, runSql]);

  useEffect(() => {
    const onRendered = (e: Event) => dispatch({ type: "rendered", ms: (e as CustomEvent<number>).detail });
    window.addEventListener("jevviz:rendered", onRendered);
    return () => window.removeEventListener("jevviz:rendered", onRendered);
  }, []);

  useEffect(() => {
    // F3: seed the SIMULATED badge from /health on load, so it's visible
    // before the first viz run - not only once a `spec` event arrives (demo
    // mode otherwise shows no badge for plain-SQL runs or runs that fail
    // before `spec`). A failed fetch (backend down) is ignored silently.
    let cancelled = false;
    void fetchSimulated().then((simulated) => {
      if (!cancelled && simulated !== null) dispatch({ type: "health", simulated });
    });
    return () => { cancelled = true; };
  }, []);

  const actions = useMemo(() => ({
    alternates: (i: number) => s.panels[i]?.alternates ?? [],
    swap: (panelIndex: number, altId: string) => dispatch({ type: "swap", panelIndex, altId }),
  }), [s.panels]);

  return (
    <div className="app">
      <header>
        <div className="controls">
          <h1>Jev <code>VISUALIZE</code></h1>
          <select aria-label="examples" value={exampleIndex} onChange={(e) => pickExample(Number(e.target.value))}>
            {EXAMPLES.map((ex, i) => <option key={ex.label} value={i}>{ex.label}</option>)}
          </select>
          <button className="run" onClick={run} disabled={s.running}>{s.running ? "Running…" : "Run ⌘↵"}</button>
        </div>
        <Editor value={sql} onChange={setSql} onRun={run} autoFocus={!!auto} />
        {s.error && <p className={`error stage-${s.error.stage}`} role="alert">{s.error.stage}: {s.error.message}</p>}
      </header>
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
