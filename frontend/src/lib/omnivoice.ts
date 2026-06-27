// OmniVoice per-speaker voice-mode helpers (Spec B).

export type OmniMode = "clone" | "design" | "auto";

// One-tap chips that append to the design prompt. Order = display order.
export const DESIGN_CHIPS: string[] = [
  "female",
  "male",
  "low pitch",
  "high pitch",
  "british accent",
  "american accent",
  "whisper",
  "energetic",
  "calm",
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
