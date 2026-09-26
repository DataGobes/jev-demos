/**
 * `?autoplay` - runs the example lineup unattended, for screen recordings.
 *
 * Nothing in the demo's data path changes; this only drives the same `setSql`
 * and `run` a person would. The SELECT part of each example is pasted and only
 * the VISUALIZE line is typed: that is the line the viewer should be watching,
 * and typing all ~300 chars of the dashboard would alone blow a 60s budget.
 *
 * Timings are URL params so pacing is tuned by reloading, not by editing code:
 *   ?autoplay&type=20&pause=500&dwell=4000&extra=1000&lead=1000&scale=1.25
 * type   ms per typed character           pause  ms after the paste, before typing
 * dwell  ms on a rendered result           extra  ms added per panel beyond the first
 * lead   ms before the first example       scale  CSS zoom, for phone-legible text
 */
export type Autoplay = { type: number; pause: number; dwell: number; extra: number; lead: number; scale: number };

const DEFAULTS: Autoplay = { type: 20, pause: 500, dwell: 4000, extra: 1000, lead: 1000, scale: 1 };

export function parseAutoplay(search: string): Autoplay | null {
  const q = new URLSearchParams(search);
  if (!q.has("autoplay")) return null;
  const num = (key: keyof Autoplay) => {
    const v = Number(q.get(key));
    return q.has(key) && Number.isFinite(v) && v > 0 ? v : DEFAULTS[key];
  };
  return { type: num("type"), pause: num("pause"), dwell: num("dwell"), extra: num("extra"), lead: num("lead"), scale: num("scale") };
}

/** Everything before the last VISUALIZE keyword is `head` (pasted); the rest is `tail` (typed). */
export function splitVisualize(sql: string): { head: string; tail: string } {
  const m = [...sql.matchAll(/\bVISUALIZE\b/gi)].pop();
  if (!m || m.index === undefined) return { head: "", tail: sql };
  return { head: sql.slice(0, m.index), tail: sql.slice(m.index) };
}
