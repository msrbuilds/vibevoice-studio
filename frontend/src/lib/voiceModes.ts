// Shared per-speaker voice-mode helpers for engines that support
// Clone/Design/Auto (OmniVoice and VoxCPM). OmniVoice-specific design-chip
// vocabulary is kept here but only surfaced for OmniVoice in the UI.

export type VoiceMode = "clone" | "design" | "auto" | "custom";
// Back-compat alias for existing call sites.
export type OmniMode = VoiceMode;

// OmniVoice's official valid English instruct vocabulary (the worker rejects
// unknown items). VoxCPM uses FREE-TEXT design/style, so it does NOT use these.
export const DESIGN_CHIPS: string[] = [
  "female",
  "male",
  "child",
  "teenager",
  "young adult",
  "middle-aged",
  "elderly",
  "very low pitch",
  "low pitch",
  "moderate pitch",
  "high pitch",
  "very high pitch",
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
  "whisper",
];

export const NONVERBAL_TAGS: string[] = [
  "[laughter]",
  "[sigh]",
  "[confirmation-en]",
  "[question-en]",
  "[question-ah]",
  "[question-oh]",
  "[question-ei]",
  "[question-yi]",
  "[surprise-ah]",
  "[surprise-oh]",
  "[surprise-wa]",
  "[surprise-yo]",
  "[dissatisfaction-hnn]",
];

/** The ordered modes a given engine exposes in the toggle. */
export function availableModes(engineName: string | null | undefined): VoiceMode[] {
  if (engineName === "qwen") return ["custom", "clone", "design"];
  return ["clone", "design", "auto"]; // OmniVoice / VoxCPM
}

/** Human label for a mode (engine-aware where it differs). */
export function modeLabel(mode: VoiceMode): string {
  if (mode === "custom") return "Custom voice";
  if (mode === "clone") return "Clone";
  if (mode === "design") return "Design";
  return "Auto";
}

/**
 * The speaker's effective voice mode. An explicit choice wins (when it's valid
 * for this engine); otherwise Qwen defaults to `custom` (built-in voice), other
 * engines to clone if a reference voice is set else auto. Derived so switching
 * engines never mutates speaker state, and a stale choice from another engine
 * (e.g. a VoxCPM "auto" left on a Qwen speaker) falls back cleanly.
 */
export function effectiveMode(
  speaker: { voice: string; omnivoiceMode?: VoiceMode },
  engineName?: string | null,
): VoiceMode {
  const modes = availableModes(engineName);
  if (speaker.omnivoiceMode && modes.includes(speaker.omnivoiceMode)) return speaker.omnivoiceMode;
  if (engineName === "qwen") return "custom";
  return speaker.voice ? "clone" : "auto";
}

/** Append a chip to a design prompt, de-duping (comma-separated, case-insensitive). */
export function appendDesignChip(text: string, chip: string): string {
  const t = (text ?? "").trim();
  if (!t) return chip;
  const parts = t.toLowerCase().split(/,\s*/);
  if (parts.includes(chip.toLowerCase())) return t;
  return `${t}, ${chip}`;
}
