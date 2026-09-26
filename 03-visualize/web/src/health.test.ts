import { afterEach, expect, test, vi } from "vitest";
import { fetchSimulated } from "./health";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("returns simulated from a successful /health response", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ simulated: true, model: "demo" }) }));
  await expect(fetchSimulated()).resolves.toBe(true);
});

test("returns null (never throws) when the backend is down", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
  await expect(fetchSimulated()).resolves.toBeNull();
});

test("returns null on a non-ok response", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({}) }));
  await expect(fetchSimulated()).resolves.toBeNull();
});
