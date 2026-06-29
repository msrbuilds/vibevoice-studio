import { useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import {
  getCfgHints,
  type EngineCfgHints,
} from "@/lib/engineHints";
import { focusRing } from "@/lib/theme";

interface Props {
  isDark: boolean;
  value: number;
  onChange: (v: number) => void;
  /**
   * Optional per-engine slider hints. When provided, the slider's
   * min/max/step, presets, and the three labels under the slider
   * reflect this engine's CFG semantics. When omitted, falls back
   * to the VibeVoice defaults.
   */
  hints?: EngineCfgHints;
}

/**
 * Reusable slider + presets panel. Embed inside any popover.
 *
 * The slider's range, presets, and labels adapt to the `hints` prop,
 * so the same body works for both VibeVoice's cfg_scale (0.5–5.0)
 * and Chatterbox's cfg_weight (0.0–1.0) without forking the component.
 */
export function CfgScaleBody({ isDark, value, onChange, hints }: Props) {
  const h = hints ?? getCfgHints(null);
  const summary = value.toFixed(h.precision);

  const set = (n: number) => {
    // Clamp to the engine's documented range so a runaway slider
    // doesn't push the value outside what the model accepts.
    onChange(Math.max(h.min, Math.min(h.max, n)));
  };

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span
          className={`text-xs font-medium ${
            isDark ? "text-zinc-400" : "text-gray-600"
          }`}
        >
          Value
        </span>
        <span className="text-sm font-mono text-orange-400">{summary}</span>
      </div>
      <input
        type="range"
        min={h.min}
        max={h.max}
        step={h.step}
        value={value}
        onChange={(e) => set(Number(e.target.value))}
        className="w-full accent-orange-500"
      />
      <div
        className={`flex justify-between text-[10px] ${
          isDark ? "text-zinc-600" : "text-gray-600"
        }`}
      >
        <span>{h.minLabel}</span>
        <span>{h.midLabel}</span>
        <span>{h.maxLabel}</span>
      </div>

      <div className="flex items-center gap-2 pt-1 flex-wrap">
        {h.presets.map((preset) => {
          // Highlight a preset when it's within half a step of the
          // current value. Using a relative threshold (step / 2) keeps
          // the highlight working for both 0.1 (VibeVoice) and 0.05
          // (Chatterbox) step sizes.
          const isActive = Math.abs(value - preset) < h.step / 2;
          return (
            <button
              key={preset}
              type="button"
              onClick={() => set(preset)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
                isActive
                  ? "bg-orange-600 text-white border-orange-500"
                  : isDark
                    ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border-zinc-700"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
              } ${focusRing}`}
            >
              {preset.toFixed(h.precision)}
            </button>
          );
        })}
      </div>

      {h.hint && (
        <p className={`text-xs ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
          {h.highlight ? (
            <>
              {h.hint.split(h.highlight)[0]}
              <span className="text-orange-400">{h.highlight}</span>
              {h.hint.split(h.highlight)[1] ?? ""}
            </>
          ) : (
            h.hint
          )}
        </p>
      )}
    </div>
  );
}

/** Standalone trigger-button popover (legacy; SettingsMenu uses CfgScaleBody). */
export function CfgScaleControl({ isDark, value, onChange, hints }: Props) {
  const [open, setOpen] = useState(false);
  const h = hints ?? getCfgHints(null);
  const summary = value.toFixed(h.precision);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border ${
          isDark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
            : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
        } ${focusRing}`}
        title="Voice cloning fidelity (CFG scale)"
      >
        <SlidersHorizontal className="w-4 h-4" />
        CFG {summary}
      </button>

      {open && (
        <div
          className={`absolute right-0 top-full mt-2 w-80 rounded-lg shadow-xl border z-30 overflow-hidden ${
            isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
          }`}
        >
          <div
            className={`px-4 py-3 border-b flex items-center justify-between ${
              isDark ? "border-zinc-800" : "border-gray-200"
            }`}
          >
            <div>
              <div
                className={`text-sm font-semibold ${
                  isDark ? "text-white" : "text-gray-900"
                }`}
              >
                Voice fidelity (CFG)
              </div>
              <div
                className={`text-xs mt-0.5 ${isDark ? "text-zinc-400" : "text-gray-600"}`}
              >
                Tradeoff: clone strength vs. naturalness
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className={`p-1 rounded ${
                isDark
                  ? "text-zinc-400 hover:text-zinc-300"
                  : "text-gray-600 hover:text-gray-600"
              } ${focusRing}`}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <CfgScaleBody
            isDark={isDark}
            value={value}
            onChange={onChange}
            hints={h}
          />
        </div>
      )}
    </div>
  );
}
