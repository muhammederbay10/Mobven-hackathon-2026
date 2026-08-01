/**
 * Money formatting/parsing tests — integer kuruş at every boundary, TL only
 * at the display edge (guide sections 14 and 19).
 */

import { describe, expect, it } from "vitest";

import { formatAmountMinor, parseAmountToMinor } from "./format";

/** tr-TR output uses non-breaking spaces; normalize for stable assertions. */
function plain(formatted: string): string {
  return formatted.replace(/\u00A0/g, " ").trim();
}

describe("formatAmountMinor", () => {
  it("formats integer kuruş with Turkish grouping and two decimals", () => {
    expect(plain(formatAmountMinor(25_000_000))).toContain("250.000,00");
    expect(plain(formatAmountMinor(120_000_050))).toContain("1.200.000,50");
    expect(plain(formatAmountMinor(0))).toContain("0,00");
  });

  it("renders null/undefined as an em dash", () => {
    expect(formatAmountMinor(null)).toBe("—");
    expect(formatAmountMinor(undefined)).toBe("—");
  });
});

describe("parseAmountToMinor", () => {
  it("parses Turkish-formatted amounts into integer kuruş", () => {
    expect(parseAmountToMinor("250.000")).toBe(25_000_000);
    expect(parseAmountToMinor("1.200.000,50")).toBe(120_000_050);
    expect(parseAmountToMinor("250000")).toBe(25_000_000);
    expect(parseAmountToMinor("0")).toBe(0);
    expect(parseAmountToMinor("12,3")).toBe(1230);
    expect(parseAmountToMinor(" 750.000 ₺ ")).toBe(75_000_000);
  });

  it("rejects unparseable input instead of guessing", () => {
    expect(parseAmountToMinor("")).toBeNull();
    expect(parseAmountToMinor("abc")).toBeNull();
    expect(parseAmountToMinor("12,345")).toBeNull();
    expect(parseAmountToMinor("-5")).toBeNull();
    expect(parseAmountToMinor("1.2.3,4,5")).toBeNull();
  });

  it("stays inside the safe-integer range", () => {
    expect(parseAmountToMinor("9".repeat(20))).toBeNull();
  });
});
