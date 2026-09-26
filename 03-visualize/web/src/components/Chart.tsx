import { useContext, useEffect, useRef, useState } from "react";
import embed from "vega-embed";
import { RowsContext } from "../rows";
import { vegaTheme } from "../theme";

export function Chart({ vega }: { vega: Record<string, unknown> }) {
  const rows = useContext(RowsContext);
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    setError(null);
    let cancelled = false;
    let finalize = () => {};
    const t0 = performance.now();
    // `height: "container"` lets the chart follow the panel's width-derived
    // height (`.chart` carries the aspect-ratio) instead of the fixed 280px the
    // backend emits, which left short panels padded and wide ones squat.
    const spec = { ...vega, width: "container", height: "container", datasets: { rows } };
    embed(ref.current, spec as never, { actions: false, renderer: "canvas", config: vegaTheme as never })
      .then((res) => {
        if (cancelled) {
          // The effect was cleaned up before embed() resolved: the view was
          // never handed to the cleanup's `finalize`, so finalize it now to
          // avoid leaking it (StrictMode double-invokes this effect in dev).
          res.view.finalize();
          return;
        }
        finalize = () => res.view.finalize();
        window.dispatchEvent(new CustomEvent("jevviz:rendered", { detail: performance.now() - t0 }));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
      finalize();
    };
  }, [vega, rows]);

  return (
    <div className="chart-wrap">
      <div ref={ref} className="chart" data-testid="chart" />
      {error && (
        <p className="chart-error" role="alert">
          Chart failed to render: {error}
        </p>
      )}
    </div>
  );
}
