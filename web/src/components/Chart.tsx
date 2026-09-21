import { useContext, useEffect, useRef } from "react";
import embed from "vega-embed";
import { RowsContext } from "../rows";

export function Chart({ vega }: { vega: Record<string, unknown> }) {
  const rows = useContext(RowsContext);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const t0 = performance.now();
    let finalize = () => {};
    embed(ref.current, { ...vega, datasets: { rows } } as never, { actions: false, renderer: "canvas" }).then((res) => {
      finalize = () => res.view.finalize();
      window.dispatchEvent(new CustomEvent("jevviz:rendered", { detail: performance.now() - t0 }));
    });
    return () => finalize();
  }, [vega, rows]);
  return <div ref={ref} className="chart" data-testid="chart" />;
}
