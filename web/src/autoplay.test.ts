import { describe, expect, it } from "vitest";
import { parseAutoplay, splitVisualize } from "./autoplay";

describe("parseAutoplay", () => {
  it("is off unless ?autoplay is present", () => {
    expect(parseAutoplay("")).toBeNull();
    expect(parseAutoplay("?type=5")).toBeNull();
  });
  it("applies defaults sized for a sub-60s cycle", () => {
    expect(parseAutoplay("?autoplay")).toEqual({ type: 20, pause: 500, dwell: 4000, extra: 1000, lead: 1000, scale: 1 });
  });
  it("reads overrides and ignores garbage", () => {
    expect(parseAutoplay("?autoplay&type=12&dwell=3000&scale=1.25")).toMatchObject({ type: 12, dwell: 3000, scale: 1.25 });
    expect(parseAutoplay("?autoplay&type=abc&scale=-1")).toMatchObject({ type: 20, scale: 1 });
  });
});

describe("splitVisualize", () => {
  it("pastes everything up to the VISUALIZE line and types only that line", () => {
    const sql = "SELECT a, b FROM t GROUP BY ALL\nVISUALIZE 'how is a trending'";
    expect(splitVisualize(sql)).toEqual({ head: "SELECT a, b FROM t GROUP BY ALL\n", tail: "VISUALIZE 'how is a trending'" });
  });
  it("splits on the last VISUALIZE, case-insensitively", () => {
    expect(splitVisualize("SELECT x\nvisualize 'q'")).toEqual({ head: "SELECT x\n", tail: "visualize 'q'" });
  });
  it("types the whole statement when there is no VISUALIZE clause", () => {
    expect(splitVisualize("SELECT * FROM products LIMIT 20")).toEqual({ head: "", tail: "SELECT * FROM products LIMIT 20" });
  });
});
