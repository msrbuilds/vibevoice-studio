/**
 * Per-engine UI hints for the CFG / CFG-weight slider.
 *
 * The single "CFG" slider in the Settings popover maps to different
 * engine knobs depending on the active engine:
 *
 *   - VibeVoice:   `cfg_scale`     (0.5–5.0, default 1.3)
 *   - Kokoro:      ignored (Kokoro has no CFG knob) — but we still
 *                  render the slider so the user can see "what would
 *                  this control look like" if they switch engines.
 *                  VibeVoice hints are shown.
 *   - Chatterbox:  `cfg_weight`    (0.0–1.0, default 0.5)
 *
 * Keeping the hints as a typed module means adding a new engine = add
 * one entry here; the slider + presets + clamp all update automatically.
 */

export interface EngineCfgHints {
  /** Stable engine id (matches the engine.name on the backend). */
  name: string;
  /** Slider minimum (inclusive). */
  min: number;
  /** Slider maximum (inclusive). */
  max: number;
  /** Slider step. */
  step: number;
  /** Preset buttons shown under the slider. */
  presets: number[];
  /** Left label under the slider ("natural"). */
  minLabel: string;
  /** Middle label ("balanced"). */
  midLabel: string;
  /** Right label ("strong clone"). */
  maxLabel: string;
  /** Default value when this engine becomes active. */
  default: number;
  /** Decimal places to show when displaying the value. */
  precision: number;
  /** Short tip line at the bottom of the slider body. */
  hint?: string;
  /** Optional HTML-highlighted snippet inside `hint`. */
  highlight?: string;
}

// VibeVoice 1.5B (default for non-Chatterbox users). Range mirrors
// the engine's own docs:
//   1.0   = can drift, more natural
//   2.0–3.0 = strong voice clone, faithful to reference
//   >3.5  = can sound robotic on long text
const VIBEVOICE_HINTS: EngineCfgHints = {
  name: "vibevoice",
  min: 0.5,
  max: 5.0,
  step: 0.1,
  presets: [1.0, 1.5, 2.0, 3.0],
  minLabel: "natural",
  midLabel: "balanced",
  maxLabel: "strong clone",
  default: 1.3,
  precision: 1,
  hint:
    "For Urdu / Hindi, start at 2.5–3.0 and use Regenerate on each segment to test different takes.",
  highlight: "2.5–3.0",
};

// Kokoro has no CFG knob — the engine ignores the field entirely. We
// still show the VibeVoice-style slider as a familiar visual cue; the
// value gets clamped on the server but never affects output.
const KOKORO_HINTS: EngineCfgHints = {
  ...VIBEVOICE_HINTS,
  name: "kokoro",
  hint:
    "Kokoro does not use CFG — this slider is a no-op while Kokoro is active. Switch to VibeVoice or Chatterbox to actually tune voice fidelity.",
};

// Chatterbox Multilingual V3 — `cfg_weight` is classifier-free guidance
// strength on a 0.0–1.0 scale. The library clamps anything outside
// this range on the server.
const CHATTERBOX_HINTS: EngineCfgHints = {
  name: "chatterbox",
  min: 0.0,
  max: 1.0,
  step: 0.05,
  presets: [0.0, 0.3, 0.5, 0.7],
  minLabel: "natural",
  midLabel: "balanced",
  maxLabel: "strict clone",
  default: 0.5,
  precision: 2,
  hint:
    "Pairs with the Exaggeration slider below. Lower values produce more natural pacing; higher values adhere more strictly to the reference voice.",
  highlight: "Exaggeration",
};

// OmniVoice has no CFG knob — the engine ignores the field entirely. Show the
// familiar slider as a visual cue; the value never affects output.
const OMNIVOICE_HINTS: EngineCfgHints = {
  ...VIBEVOICE_HINTS,
  name: "omnivoice",
  hint:
    "OmniVoice does not use CFG — this slider is a no-op while OmniVoice is active. Voice fidelity comes from the reference clip.",
};

// VoxCPM `cfg_value` — classifier-free guidance, ~1.0–3.0, default 2.0.
const VOXCPM_HINTS: EngineCfgHints = {
  name: "voxcpm",
  min: 1.0,
  max: 3.0,
  step: 0.1,
  presets: [1.5, 2.0, 2.5, 3.0],
  minLabel: "natural",
  midLabel: "balanced",
  maxLabel: "strict",
  default: 2.0,
  precision: 1,
  hint:
    "VoxCPM CFG (cfg_value). Higher adheres more strictly to the reference voice or design prompt; lower is more natural. Pairs with the Quality control.",
  highlight: "Quality",
};

// Qwen3-TTS CustomVoice has no CFG knob — the engine ignores the field. Show
// the familiar slider as a visual cue; tuning happens in the Advanced panel.
const QWEN_HINTS: EngineCfgHints = {
  ...VIBEVOICE_HINTS,
  name: "qwen",
  hint:
    "Qwen CustomVoice doesn't use CFG — this slider is a no-op. Tune output via the Advanced generation panel (temperature / top-p / top-k / repetition penalty).",
};

const HINTS_BY_ENGINE: Record<string, EngineCfgHints> = {
  vibevoice: VIBEVOICE_HINTS,
  kokoro: KOKORO_HINTS,
  chatterbox: CHATTERBOX_HINTS,
  omnivoice: OMNIVOICE_HINTS,
  voxcpm: VOXCPM_HINTS,
  qwen: QWEN_HINTS,
};

/** Return the hints for an engine id, falling back to VibeVoice defaults. */
export function getCfgHints(engineName: string | null | undefined): EngineCfgHints {
  if (engineName && HINTS_BY_ENGINE[engineName]) {
    return HINTS_BY_ENGINE[engineName];
  }
  return VIBEVOICE_HINTS;
}

/** Convenience: get the default CFG value for an engine (used to snap on switch). */
export function getDefaultCfgForEngine(engineName: string | null | undefined): number {
  return getCfgHints(engineName).default;
}
