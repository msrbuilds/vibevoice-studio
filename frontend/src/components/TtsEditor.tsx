import { useEffect, useRef } from "react";
import { Loader2, Play, RefreshCw, Square } from "lucide-react";
import { focusRing } from "@/lib/theme";
import type { EngineLanguage, Voice } from "@/types/models";
import { textStats, fmtDuration } from "@/lib/textStats";
import { DESIGN_CHIPS, NONVERBAL_TAGS, appendDesignChip, type OmniMode } from "@/lib/omnivoice";
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
  isPlaying: boolean;
  onGenerate: () => void;
  onPlay: () => void;
}

export function TtsEditor(props: Props) {
  const {
    isDark, text, onTextChange, activeVoice, languages, showLanguage,
    language, onLanguageChange, isOmni, omniMode, onOmniModeChange,
    voiceDesign, onVoiceDesignChange, busy, isGenerating, isPlaying, onGenerate, onPlay,
  } = props;
  const stats = textStats(text);
  const inputBg = isDark ? "bg-zinc-900 border-zinc-800 text-white" : "bg-white border-gray-200 text-gray-900";
  const selectBg = isDark ? "bg-zinc-800 border-zinc-700 text-white" : "bg-white border-gray-300 text-gray-900";
  const sub = isDark ? "text-zinc-400" : "text-gray-600";

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pendingCaret = useRef<number | null>(null);

  // After a tag insertion changes the text, restore the caret just past the
  // inserted tag (the textarea is controlled, so we do this post-render).
  useEffect(() => {
    if (pendingCaret.current != null && textareaRef.current) {
      const pos = pendingCaret.current;
      textareaRef.current.focus();
      textareaRef.current.setSelectionRange(pos, pos);
      pendingCaret.current = null;
    }
  }, [text]);

  // Insert a non-verbal tag at the cursor (or replace the selection), padding
  // with spaces so it never glues to adjacent words.
  const insertTag = (tag: string) => {
    const el = textareaRef.current;
    const start = el?.selectionStart ?? text.length;
    const end = el?.selectionEnd ?? text.length;
    const before = text.slice(0, start);
    const after = text.slice(end);
    const lead = before.length > 0 && !/\s$/.test(before) ? " " : "";
    const trail = after.length === 0 || !/^\s/.test(after) ? " " : "";
    const chunk = `${lead}${tag}${trail}`;
    pendingCaret.current = before.length + chunk.length;
    onTextChange(before + chunk + after);
  };

  // Show the "Voice: X" note for any non-OmniVoice engine, and for OmniVoice
  // only in clone mode (design/auto carry no reference voice).
  const showVoiceNote = !isOmni || omniMode === "clone";

  const segBtn = (m: OmniMode, label: string) => (
    <button
      type="button"
      onClick={() => onOmniModeChange(m)}
      className={`flex-1 px-3 py-1.5 text-sm font-medium rounded transition-colors ${
        omniMode === m
          ? "bg-orange-600 text-white"
          : isDark
            ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
            : "bg-gray-100 text-gray-600 hover:bg-gray-200"
      } ${focusRing}`}
    >
      {label}
    </button>
  );

  return (
    <div className="max-w-3xl mx-auto w-full space-y-3">
      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        placeholder="Type or paste text to synthesize…"
        className={`w-full min-h-[260px] rounded-xl border p-4 text-sm leading-relaxed focus:outline-none focus:border-orange-500 ${inputBg} ${focusRing}`}
      />

      {/* OmniVoice inline non-verbal sounds — insert a tag at the cursor */}
      {isOmni && (
        <div className="space-y-1.5">
          <div className={`text-xs ${sub}`}>
            Non-verbal sounds — click to insert at the cursor
          </div>
          <div className="flex flex-wrap gap-1">
            {NONVERBAL_TAGS.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => insertTag(tag)}
                className={`px-1.5 py-0.5 text-[11px] font-mono rounded border transition-colors ${
                  isDark
                    ? "border-zinc-700 text-zinc-400 hover:border-orange-500 hover:text-orange-300"
                    : "border-gray-300 text-gray-600 hover:border-orange-500 hover:text-orange-600"
                } ${focusRing}`}
              >
                {tag}
              </button>
            ))}
          </div>
        </div>
      )}

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
              <span className="text-orange-400">{activeVoice ? activeVoice.name : "none selected"}</span>
            </p>
          )}
          {omniMode === "design" && (
            <div className="space-y-1.5">
              <input
                type="text"
                value={voiceDesign}
                onChange={(e) => onVoiceDesignChange(e.target.value)}
                placeholder="e.g. female, low pitch, british accent"
                className={`w-full border rounded-md px-2 py-1.5 text-sm focus:outline-none focus:border-orange-500 ${selectBg} ${focusRing}`}
              />
              <div className="flex flex-wrap gap-1">
                {DESIGN_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    onClick={() => onVoiceDesignChange(appendDesignChip(voiceDesign, chip))}
                    className={`px-1.5 py-0.5 text-[11px] rounded border transition-colors ${
                      isDark
                        ? "border-zinc-700 text-zinc-400 hover:border-orange-500 hover:text-orange-300"
                        : "border-gray-300 text-gray-600 hover:border-orange-500 hover:text-orange-600"
                    } ${focusRing}`}
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
              Voice: <span className="text-orange-400">{activeVoice ? activeVoice.name : "none selected"}</span>
            </span>
          )}
          <button type="button" onClick={onGenerate} disabled={busy || !text.trim()}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium bg-orange-600 hover:bg-orange-500 disabled:bg-zinc-700 disabled:text-zinc-400 text-white transition-colors ${focusRing}`}>
            {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Generate
          </button>
          <button type="button" onClick={onPlay} disabled={busy && !isPlaying}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              isPlaying
                ? "bg-orange-600 hover:bg-orange-500 text-white"
                : isDark ? "bg-zinc-800 hover:bg-zinc-700 text-white" : "bg-gray-100 hover:bg-gray-200 text-gray-900"} ${focusRing}`}>
            {isPlaying ? <><Square className="w-4 h-4" /> Stop</> : <><Play className="w-4 h-4" /> Play</>}
          </button>
        </div>
      </div>
    </div>
  );
}
