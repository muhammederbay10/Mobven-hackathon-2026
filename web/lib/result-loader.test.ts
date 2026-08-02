import { describe, expect, it } from "vitest";

import {
  cachedResultLoaderDurationMs,
  remainingResultLoaderDelayMs,
} from "./result-loader";

describe("cached result loader timing", () => {
  it("chooses an integer duration from 10 through 20 seconds", () => {
    expect(cachedResultLoaderDurationMs(0)).toBe(10_000);
    expect(cachedResultLoaderDurationMs(0.5)).toBe(15_000);
    expect(cachedResultLoaderDurationMs(0.999999)).toBe(20_000);
  });

  it("waits only for the part of the selected duration that has not elapsed", () => {
    expect(remainingResultLoaderDelayMs(1_000, 15_000, 5_000)).toBe(11_000);
    expect(remainingResultLoaderDelayMs(1_000, 15_000, 20_000)).toBe(0);
  });
});
