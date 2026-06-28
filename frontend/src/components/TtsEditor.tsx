import { Loader2, Play, RefreshCw } from "lucide-react";
import type { EngineLanguage, Voice } from "@/types/models";
import { textStats, fmtDuration } from "@/lib/textStats";
import { DESIGN_CHIPS, appendDesignChip, type OmniMode } from "@/lib/omnivoice";
import { LanguageSelect } from "./LanguageSelect";

interface Props {
  isDark: boolean;
  text: string;
  onTextChange: (t: string) => void;
  activeVoice: Voice | null;
  languages: EngineLanguage[];
  showLanguage: boolean;          // false for built-in-voice engines (filter handled in library)
  language: string | null;
  onLanguageChange: (code: string) => void;
  // OmniVoice only: per-buffer Clone/Design/Auto mode + design prompt.
  isOmni: boolean;
  omniMode: OmniMode;
  onOmniModeChange: (m: OmniMode) => void;
  voiceDesign: string;
  onVoiceDesignChange: (v: string) => void;
  busy: boolean;
  isGenerating: boolean;
  onGenerate: () => void;
  onPlay: () => void;
}

export function TtsEditor(props: Props) {
  const {
    isDark, text, onTextChange, activeVoice, languages, showLanguage,
    language, onLanguageChange, isOmni, omniMode, onOmniModeChange,
    voiceDesign, onVoiceDesignChange, busy, isGenerating, onGenerate, onPlay,
  } = props;
  const stats = textStats(text);
  const inputBg = isDark ? "bg-zinc-900 border-zinc-800 text-white" : "bg-white border-gray-200 text-gray-900";
  const selectBg = isDark ? "bg-zinc-800 border-zinc-700 text-white" : "bg-white border-gray-300 text-gray-900";
  const sub = isDark ? "text-zinc-500" : "text-gray-500";

  // Show the "Voice: X" note for any non-OmniVoice engine, and for OmniVoice
  // only in clone mode (design/auto carry no reference voice).
  const showVoiceNote = !isOmni || omniMode === "clone";

  const segBtn = (m: OmniMode, label: string) => (
    <button
      type="button"
      onClick={() => onOmniModeChange(m)}
      className={`flex-1 px-3 py-1.5 text-sm font-medium rounded transition-colors ${
        omniMode === m
          ? "bg-teal-600 text-white"
          : isDark
            ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
            : "bg-gray-100 text-gray-600 hover:bg-gray-200"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="max-w-3xl mx-auto w-full space-y-3">
      <textarea
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        placeholder="Type or paste text to synthesize…"
        className={`w-full min-h-[260px] rounded-xl border p-4 text-sm leading-relaxed focus:outline-none focus:border-teal-500 ${inputBg}`}
      />

      {/* OmniVoice voice mode: Clone / Design / Auto */}
      {isOmni && (
        <div className={`rounded-xl border p-3 space-y-2 ${isDark ? "border-zinc-800 bg-zinc-900/50" : "border-gray-200 bg-gray-50"}`}>
          <div className="flex gap-1.5">
            {segBtn("clone", "Clone")}
            {segBtn("design", "Design")}
            {segBtn("auto", "Auto")}
          </div>
          {omniMode === "clone" && (
            <p className={`text-xs ${sub}`}>
              Clones the voice selected in the library:{" "}
              <span className="text-teal-400">{activeVoice ? activeVoice.name : "none selected"}</span>
            </p>
          )}
          {omniMode === "design" && (
            <div className="space-y-1.5">
              <input
                type="text"
                value={voiceDesign}
                onChange={(e) => onVoiceDesignChange(e.target.value)}
                placeholder="e.g. female, low pitch, british accent"
                className={`w-full border rounded-md px-2 py-1.5 text-sm focus:outline-none focus:border-teal-500 ${selectBg}`}
              />
              <div className="flex flex-wrap gap-1">
                {DESIGN_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    onClick={() => onVoiceDesignChange(appendDesignChip(voiceDesign, chip))}
                    className={`px-1.5 py-0.5 text-[11px] rounded border transition-colors ${
                      isDark
                        ? "border-zinc-700 text-zinc-400 hover:border-teal-500 hover:text-teal-300"
                        : "border-gray-300 text-gray-500 hover:border-teal-500 hover:text-teal-600"
                    }`}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          )}
          {omniMode === "auto" && (
            <p className={`text-xs italic ${sub}`}>OmniVoice will invent a voice for this text.</p>
          )}
        </div>
      )}

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className={`text-xs ${sub}`}>
          {stats.chars} chars · {stats.words} words · {fmtDuration(stats.seconds)}
        </div>
        <div className="flex items-center gap-2">
          {showLanguage && (
            <LanguageSelect isDark={isDark} languages={languages} value={language} onChange={onLanguageChange} />
          )}
          {showVoiceNote && (
            <span className={`text-xs ${sub}`}>
              Voice: <span className="text-teal-400">{activeVoice ? activeVoice.name : "none selected"}</span>
            </span>
          )}
          <button type="button" onClick={onGenerate} disabled={busy || !text.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg font-medium bg-amber-600 hover:bg-amber-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white transition-colors">
            {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Generate
          </button>
          <button type="button" onClick={onPlay} disabled={busy}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              isDark ? "bg-zinc-800 hover:bg-zinc-700 text-white" : "bg-gray-100 hover:bg-gray-200 text-gray-900"}`}>
            <Play className="w-4 h-4" /> Play
          </button>
        </div>
      </div>
    </div>
  );
}
