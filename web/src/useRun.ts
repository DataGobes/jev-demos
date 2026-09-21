import { useCallback, useEffect, useRef } from "react";
import type { Action } from "./reducer";
import type { RunEvent } from "./stream";

/** Shape of `runQuery` (or a test double for it): an NDJSON event stream for one SQL run. */
export type RunQueryFn = (sql: string, signal?: AbortSignal) => AsyncGenerator<RunEvent>;

/**
 * Orchestrates running a query: dispatches `start`, streams `event` actions,
 * and dispatches `done` when the stream ends or fails.
 *
 * A newer `run()` call always wins over an older one still in flight — it
 * aborts the previous run's controller before starting. The older run's
 * remaining events (including any already buffered before the abort took
 * effect) are dropped rather than dispatched, and only the current run may
 * dispatch `done` — an aborted run dispatches neither an error nor `done`,
 * so it can never clobber the newer run's state. The in-flight run is also
 * aborted on unmount.
 */
export function useRun(dispatch: (action: Action) => void, runQuery: RunQueryFn) {
  const controllerRef = useRef<AbortController | null>(null);

  const run = useCallback(
    (sql: string) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      dispatch({ type: "start" });
      void (async () => {
        try {
          for await (const event of runQuery(sql, controller.signal)) {
            if (controller.signal.aborted) return;
            dispatch({ type: "event", event });
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          dispatch({ type: "event", event: { type: "error", stage: "network", message: String(err) } });
        } finally {
          if (!controller.signal.aborted) dispatch({ type: "done" });
        }
      })();
    },
    [dispatch, runQuery],
  );

  useEffect(() => () => controllerRef.current?.abort(), []);

  return run;
}
