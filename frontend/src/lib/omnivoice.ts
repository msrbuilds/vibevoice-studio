// OmniVoice per-speaker voice-mode helpers (Spec B).

export type OmniMode = "clone" | "design" | "auto";

// One-tap chips that append to the design prompt. These MUST be drawn from
// OmniVoice's official valid English instruct vocabulary — the worker rejects
// any unknown item (e.g. "calm"/"energetic"/"warm" are NOT valid). Grouped
// gender → age → pitch → accent → style; order = display order.
export const DESIGN_CHIPS: string[] = [
  // gender
  "female",
  "male",
  // age
  "child",
  "teenager",
  "young adult",
  "middle-aged",
  "elderly",
  // pitch
  "very low pitch",
  "low pitch",
  "moderate pitch",
  "high pitch",
  "very high pitch",
  // accent
  "american accent",
  "british accent",
  "australian accent",
  "canadian accent",
  "indian accent",
  "chinese accent",
  "japanese accent",
  "korean accent",
  "russian accent",
  "portuguese accent",
  // style
  "whisper",
];

/**
 * The speaker's effective OmniVoice mode. An explicit choice wins; otherwise
 * clone if a reference voice is set, else auto. Keeping it derived means
 * switching engines never mutates speaker state.
 */
export function effectiveMode(speaker: { voice: string; omnivoiceMode?: OmniMode }): OmniMode {
  return speaker.omnivoiceMode ?? (speaker.voice ? "clone" : "auto");
}

/** Append a chip to a design prompt, de-duping (comma-separated, case-insensitive). */
export function appendDesignChip(text: string, chip: string): string {
  const t = (text ?? "").trim();
  if (!t) return chip;
  const parts = t.toLowerCase().split(/,\s*/);
  if (parts.includes(chip.toLowerCase())) return t;
  return `${t}, ${chip}`;
}
