import { renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { Action } from "./reducer";
import type { RunEvent } from "./stream";
import { useRun } from "./useRun";

// A "gate" is a promise the test controls the resolution of, letting us pause
// an async generator mid-stream and interleave two runs deterministically.
function makeGate() {
  let release!: () => void;
  const wait = new Promise<void>((resolve) => { release = resolve; });
  return { wait, release };
}

// Waits for pending microtasks (and the macrotask queue) to drain, so an
// awaited gate's resolution has had a chance to propagate through the
// for-await loop and into a dispatch call before we assert on it.
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function controlledQuery(events: RunEvent[]) {
  const gates = events.map(() => makeGate());
  const signals: (AbortSignal | undefined)[] = [];
  async function* gen(_sql: string, signal?: AbortSignal) {
    signals.push(signal);
    for (let i = 0; i < events.length; i++) {
      await gates[i].wait;
      yield events[i];
    }
  }
  return { gen, gates, signals };
}

test("a newer run supersedes an older one: stale events are dropped, exactly one done fires", async () => {
  const dispatch = vi.fn<(action: Action) => void>();
  const a = controlledQuery([
    { type: "parsed", sql: "a", intents: null },
    { type: "result", columns: [], rows: [], row_count: 0, truncated: false, ms: { query: 1 } },
  ]);
  const b = controlledQuery([
    { type: "parsed", sql: "b", intents: null },
    { type: "result", columns: [], rows: [], row_count: 0, truncated: false, ms: { query: 2 } },
  ]);
  const runQuery = vi.fn((sql: string, signal?: AbortSignal) => (sql === "a" ? a.gen(sql, signal) : b.gen(sql, signal)));

  const { result } = renderHook(() => useRun(dispatch, runQuery));

  result.current("a");
  await flush();
  a.gates[0].release(); // A's "parsed" — should be dispatched, A not yet superseded
  await flush();

  result.current("b"); // supersedes A while A is still streaming
  await flush();

  a.gates[1].release(); // A's "result" arrives late — must never be dispatched
  await flush();
  b.gates[0].release(); // B's "parsed"
  await flush();
  b.gates[1].release(); // B's "result" — B's stream ends here
  await flush();

  const events = dispatch.mock.calls.map(([action]) => action);
  const eventTypes = events.filter((e) => e.type === "event").map((e) => (e as { event: RunEvent }).event.type);
  expect(eventTypes).toEqual(["parsed", "parsed", "result"]); // A's "parsed", then B's "parsed" + "result" — never A's late "result"
  expect(events.filter((e) => e.type === "done")).toHaveLength(1); // only B's run may finish
  expect(events.filter((e) => e.type === "start")).toHaveLength(2); // both runs started
});

test("a non-abort error dispatches a network error event and done", async () => {
  const dispatch = vi.fn<(action: Action) => void>();
  async function* failing(): AsyncGenerator<RunEvent> {
    throw new Error("boom");
    // eslint-disable-next-line no-unreachable
    yield { type: "parsed", sql: "", intents: null };
  }
  const runQuery = vi.fn(() => failing());

  const { result } = renderHook(() => useRun(dispatch, runQuery));
  result.current("s");
  await flush();

  const events = dispatch.mock.calls.map(([action]) => action);
  expect(events).toContainEqual({ type: "event", event: { type: "error", stage: "network", message: "Error: boom" } });
  expect(events.filter((e) => e.type === "done")).toHaveLength(1);
});

test("an aborted run's own AbortError does not surface as a network error", async () => {
  // Mirrors what fetch actually does: a signal that's already aborted (or
  // aborts mid-stream) rejects the pending read with an AbortError.
  const dispatch = vi.fn<(action: Action) => void>();
  async function* abortable(sql: string, signal?: AbortSignal): AsyncGenerator<RunEvent> {
    yield { type: "parsed", sql, intents: null };
    await new Promise<never>((_, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("The operation was aborted.", "AbortError")));
    });
  }
  const runQuery = vi.fn((sql: string, signal?: AbortSignal) => abortable(sql, signal));

  const { result } = renderHook(() => useRun(dispatch, runQuery));
  result.current("s1");
  await flush();
  result.current("s2"); // aborts s1's signal, rejecting s1's pending await with AbortError
  await flush();

  const events = dispatch.mock.calls.map(([action]) => action);
  expect(events.some((e) => e.type === "event" && e.event.type === "error")).toBe(false);
  // Neither run reaches a natural end here (s1 was cut off, s2's promise never
  // resolves), so neither may dispatch `done`.
  expect(events.filter((e) => e.type === "done")).toHaveLength(0);
});

test("unmounting aborts the in-flight run's signal", async () => {
  const dispatch = vi.fn<(action: Action) => void>();
  let capturedSignal: AbortSignal | undefined;
  async function* hang(_sql: string, signal?: AbortSignal): AsyncGenerator<RunEvent> {
    capturedSignal = signal;
    await new Promise(() => {}); // never resolves
  }
  const runQuery = vi.fn((sql: string, signal?: AbortSignal) => hang(sql, signal));

  const { result, unmount } = renderHook(() => useRun(dispatch, runQuery));
  result.current("s");
  await flush();
  expect(capturedSignal?.aborted).toBe(false);

  unmount();

  expect(capturedSignal?.aborted).toBe(true);
});
