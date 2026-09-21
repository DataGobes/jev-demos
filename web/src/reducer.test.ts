import { expect, test } from "vitest";
import { initialState, reduce } from "./reducer";

const leaf = (type: string) => ({ type, props: {}, children: [] });
const specEvent = {
  type: "spec" as const,
  spec: { root: "grid", elements: { grid: { type: "Grid", props: { columns: 1 }, children: ["panel-0"] },
    "panel-0": { type: "Panel", props: { title: "Bar", intent: "q", p: 0.8, match: "strong", panelIndex: 0 }, children: ["leaf-0"] },
    "leaf-0": leaf("Chart") } },
  panels: [{ intent: "q", match: "strong" as const, chosen: { id: "c00", kind: "bar", title: "Bar", p: 0.8, element: leaf("Chart") },
    alternates: [{ id: "c05", kind: "pie", title: "Pie", p: 0.4, element: leaf("Chart") }] }],
  ms: { profile: 1, enumerate: 1, jev: 250 }, usage: { input_tokens: 2400, usd: 0.0001 }, scored: "9 of 9", cache: "miss", simulated: true,
};
const resultEvent = { type: "result" as const, columns: ["a"], rows: [{ a: 1 }], row_count: 1, truncated: false, ms: { query: 3 } };

test("result paints a table immediately, spec replaces it", () => {
  let s = reduce(initialState, { type: "start" });
  s = reduce(s, { type: "event", event: resultEvent });
  expect(s.spec?.elements[s.spec.root].type).toBe("Table");
  expect(s.rows).toEqual([{ a: 1 }]);
  s = reduce(s, { type: "event", event: specEvent });
  expect(s.spec?.root).toBe("grid");
  expect(s.timings).toMatchObject({ query: 3, jev: 250 });
});

test("swap exchanges chosen and alternate without losing the old one", () => {
  let s = reduce(reduce(initialState, { type: "event", event: resultEvent }), { type: "event", event: specEvent });
  s = reduce(s, { type: "swap", panelIndex: 0, altId: "c05" });
  expect(s.spec?.elements["panel-0"].props).toMatchObject({ title: "Pie", p: 0.4 });
  expect(s.panels[0].chosen.id).toBe("c05");
  expect(s.panels[0].alternates.map((a) => a.id)).toEqual(["c00"]);
});

test("swap recomputes the match band for the newly-chosen alternate (E1)", () => {
  // specEvent's panel starts "strong" (p: 0.8); its only alternate is p: 0.4
  // ("weak" under the strong>=0.6, weak>=0.3 bands) - swapping it in must not
  // keep the stale "strong" label on either the panel state or the spec props.
  let s = reduce(reduce(initialState, { type: "event", event: resultEvent }), { type: "event", event: specEvent });
  s = reduce(s, { type: "swap", panelIndex: 0, altId: "c05" });
  expect(s.panels[0].match).toBe("weak");
  expect(s.spec?.elements["panel-0"].props).toMatchObject({ match: "weak" });
});

test("swap to a below-threshold alternate recomputes match down to none (E1)", () => {
  let s = reduce(reduce(initialState, { type: "event", event: resultEvent }), { type: "event", event: specEvent });
  const lowSpecEvent = { ...specEvent, panels: [{ ...specEvent.panels[0],
    alternates: [{ id: "c09", kind: "scatter", title: "Scatter", p: 0.2, element: leaf("Chart") }] }] };
  s = reduce(reduce(initialState, { type: "event", event: resultEvent }), { type: "event", event: lowSpecEvent });
  s = reduce(s, { type: "swap", panelIndex: 0, altId: "c09" });
  expect(s.panels[0].match).toBe("none");
  expect(s.spec?.elements["panel-0"].props).toMatchObject({ match: "none" });
});

test("jev error keeps the rendered spec and records a warning", () => {
  let s = reduce(reduce(initialState, { type: "event", event: resultEvent }), { type: "event", event: specEvent });
  s = reduce(s, { type: "event", event: { type: "error", stage: "jev", message: "boom" } });
  expect(s.spec?.root).toBe("grid");
  expect(s.error).toEqual({ stage: "jev", message: "boom" });
});

test("start clears the previous run", () => {
  const s = reduce(reduce(initialState, { type: "event", event: resultEvent }), { type: "start" });
  expect(s.spec).toBeNull();
  expect(s.running).toBe(true);
});

test("health action seeds simulated before any spec event", () => {
  const s = reduce(initialState, { type: "health", simulated: true });
  expect(s.simulated).toBe(true);
});

test("start preserves simulated seeded by health", () => {
  const seeded = reduce(initialState, { type: "health", simulated: true });
  const s = reduce(seeded, { type: "start" });
  expect(s.simulated).toBe(true);
});
