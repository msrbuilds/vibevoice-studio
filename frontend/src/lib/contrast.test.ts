import { describe, it, expect } from "vitest";
import { contrastRatio, PALETTE } from "./contrast";

// Sanity checks on the math itself
describe("contrastRatio", () => {
  it("is 21 for black on white", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 0);
  });
  it("is 1 for identical colors", () => {
    expect(contrastRatio("#f97316", "#f97316")).toBeCloseTo(1, 5);
  });
  it("is symmetric", () => {
    const a = contrastRatio(PALETTE["zinc-400"], PALETTE["zinc-950"]);
    const b = contrastRatio(PALETTE["zinc-950"], PALETTE["zinc-400"]);
    expect(a).toBeCloseTo(b, 5);
  });
});

// The audit: every CHOSEN (post-fix) pair must clear its target.
// AAA = 7:1 for text; accent buttons flagged as AA = 4.5:1.
const AAA = 7;
const AA = 4.5;
const UI = 3; // graphical objects / large text

const AUDIT: Array<{ fg: string; bg: string; min: number; label: string }> = [
  // --- Dark theme text (target AAA) ---
  { fg: "zinc-400", bg: "zinc-950", min: AAA, label: "dark subtle/meta text" },
  { fg: "zinc-300", bg: "zinc-950", min: AAA, label: "dark muted text" },
  { fg: "zinc-100", bg: "zinc-950", min: AAA, label: "dark primary text" },
  { fg: "orange-400", bg: "zinc-950", min: AAA, label: "dark accent text" },
  // --- Light theme text (target AAA) ---
  { fg: "gray-600", bg: "white", min: AAA, label: "light subtle/meta/icon text" },
  { fg: "gray-700", bg: "white", min: AAA, label: "light muted text" },
  { fg: "gray-900", bg: "white", min: AAA, label: "light primary text" },
  // --- Accent text links (target AA; AAA infeasible on brand orange) ---
  { fg: "orange-700", bg: "white", min: AA, label: "light accent text" },
  // --- Solid accent buttons w/ white text (target AA; flagged) ---
  { fg: "white", bg: "orange-700", min: AA, label: "primary button (orange)" },
  { fg: "white", bg: "amber-700", min: AA, label: "generate-all button (amber)" },
  { fg: "white", bg: "red-600", min: AA, label: "danger button (red)" },
  // --- Danger icon hover (UI / large) ---
  { fg: "red-700", bg: "white", min: AA, label: "light danger icon hover" },
];

describe("WCAG audit — chosen colors clear their targets", () => {
  for (const { fg, bg, min, label } of AUDIT) {
    it(`${label}: ${fg} on ${bg} >= ${min}:1`, () => {
      const ratio = contrastRatio(PALETTE[fg], PALETTE[bg]);
      expect(ratio).toBeGreaterThanOrEqual(min);
    });
  }
});

// Regression guards: the colors we REPLACED must indeed have failed,
// documenting WHY they were changed.
describe("WCAG audit — replaced colors were failing", () => {
  it("zinc-500 on zinc-950 failed AA", () => {
    expect(contrastRatio(PALETTE["zinc-500"], PALETTE["zinc-950"])).toBeLessThan(AA);
  });
  it("gray-400 on white failed UI 3:1", () => {
    expect(contrastRatio(PALETTE["gray-400"], PALETTE["white"])).toBeLessThan(UI);
  });
  it("white on amber-600 failed AA", () => {
    expect(contrastRatio(PALETTE["white"], PALETTE["amber-600"])).toBeLessThan(AA);
  });
  it("white on orange-600 failed AA", () => {
    expect(contrastRatio(PALETTE["white"], PALETTE["orange-600"])).toBeLessThan(AA);
  });
});
