import { expect, test, vi } from "vitest";
import { runQuery } from "./stream";

test("parses NDJSON split across chunk boundaries", async () => {
  const enc = new TextEncoder();
  const chunks = ['{"type":"parsed","sql":"s","inte', 'nts":null}\n{"type":"result","columns":[],', '"rows":[],"row_count":0,"truncated":false,"ms":{"query":1}}\n'];
  const body = new ReadableStream({ start(c) { chunks.forEach((x) => c.enqueue(enc.encode(x))); c.close(); } });
  vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status: 200 })));
  const events = [];
  for await (const e of runQuery("s")) events.push(e.type);
  expect(events).toEqual(["parsed", "result"]);
});
