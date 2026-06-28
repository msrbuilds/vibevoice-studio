import { Loader2, Play, RefreshCw } from "lucide-react";
import type { EngineLanguage, Voice } from "@/types/models";
import { textStats, fmtDuration } from "@/lib/textStats";
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
  busy: boolean;
  isGenerating: boolean;
  onGenerate: () => void;
  onPlay: () => void;
}

export function TtsEditor(props: Props) {
  const { isDark, text, onTextChange, activeVoice, languages, showLanguage,
          language, onLanguageChange, busy, isGenerating, onGenerate, onPlay } = props;
  const stats = textStats(text);
  const inputBg = isDark ? "bg-zinc-900 border-zinc-800 text-white" : "bg-white border-gray-200 text-gray-900";
  const sub = isDark ? "text-zinc-500" : "text-gray-500";
  return (
    <div className="max-w-3xl mx-auto w-full space-y-3">
      <textarea
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        placeholder="Type or paste text to synthesize…"
        className={`w-full min-h-[260px] rounded-xl border p-4 text-sm leading-relaxed focus:outline-none focus:border-teal-500 ${inputBg}`}
      />
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className={`text-xs ${sub}`}>
          {stats.chars} chars · {stats.words} words · {fmtDuration(stats.seconds)}
        </div>
        <div className="flex items-center gap-2">
          {showLanguage && (
            <LanguageSelect isDark={isDark} languages={languages} value={language} onChange={onLanguageChange} />
          )}
          <span className={`text-xs ${sub}`}>
            Voice: <span className="text-teal-400">{activeVoice ? activeVoice.name : "none selected"}</span>
          </span>
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
