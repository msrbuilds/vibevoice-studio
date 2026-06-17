import { Check, Loader2, Play, RefreshCw, Square, Trash2 } from "lucide-react";
import { Download } from "lucide-react";
import type { Segment, Speaker } from "@/types/models";

interface Props {
  segment: Segment;
  index: number;
  speakers: Speaker[];
  isGenerating: boolean;
  isPlaying: boolean;
  isCached: boolean;
  canDelete: boolean;
  busy: boolean;
  theme: "light" | "dark";
  speakerColor: (id: string) => string;
  onUpdate: (id: string, field: "text" | "speakerId", value: string) => void;
  onRemove: (id: string) => void;
  onGenerate: () => void;
  onRegenerate: () => void;
  onPlay: () => void;
  onStop: () => void;
  onDownload: () => void;
}

export function SegmentCard({
  segment,
  index,
  speakers,
  isGenerating,
  isPlaying,
  isCached,
  canDelete,
  busy,
  theme,
  speakerColor,
  onUpdate,
  onRemove,
  onGenerate,
  onRegenerate,
  onPlay,
  onStop,
  onDownload,
}: Props) {
  const isActive = isPlaying || isGenerating;
  const isDark = theme === "dark";

  return (
    <div
      className={`group relative p-5 rounded-xl border transition-colors
        ${isDark ? "bg-zinc-900" : "bg-white"}
        ${
          isActive
            ? "border-teal-600/50"
            : isDark
              ? "border-zinc-800 hover:border-zinc-700"
              : "border-gray-200 hover:border-gray-300"
        }`}
    >
      <span
        className={`absolute -left-0.5 top-1/2 -translate-y-1/2 w-1 h-12 rounded-full transition-colors ${
          isActive
            ? "bg-teal-500"
            : isCached
              ? "bg-green-500"
              : isDark
                ? "bg-zinc-700 group-hover:bg-zinc-600"
                : "bg-gray-300 group-hover:bg-gray-400"
        }`}
      />

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span
            className={`flex items-center justify-center w-8 h-8 rounded-lg text-sm font-medium ${
              isDark ? "bg-zinc-800 text-zinc-400" : "bg-gray-100 text-gray-600"
            }`}
          >
            {index + 1}
          </span>
          <h3 className={`font-medium ${isDark ? "text-white" : "text-gray-900"}`}>
            Segment {index + 1}
          </h3>

          {isGenerating && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 bg-amber-600/20 rounded-full">
              <Loader2 className="w-3 h-3 text-amber-400 animate-spin" />
              <span className="text-amber-300 text-xs font-medium">Generating…</span>
            </span>
          )}
          {isPlaying && !isGenerating && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 bg-teal-600/20 rounded-full">
              <span className="w-2 h-2 bg-teal-400 rounded-full animate-pulse" />
              <span className="text-teal-300 text-xs font-medium">Playing…</span>
            </span>
          )}
          {isCached && !isActive && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 bg-green-600/20 rounded-full">
              <Check className="w-3 h-3 text-green-400" />
              <span className="text-green-300 text-xs font-medium">Ready</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          {isCached && (
            <button
              type="button"
              onClick={onDownload}
              disabled={isActive || busy}
              className="p-2 text-zinc-500 hover:text-teal-400 hover:bg-teal-500/10 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Download this segment as WAV"
            >
              <Download className="w-4 h-4" />
            </button>
          )}
          {canDelete && (
            <button
              type="button"
              onClick={() => onRemove(segment.id)}
              disabled={isActive || busy}
              className="p-2 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Delete segment"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <div className="flex-1">
          <label
            className={`block text-xs font-medium mb-1.5 ${
              isDark ? "text-zinc-400" : "text-gray-600"
            }`}
          >
            Speaker
          </label>
          <div className="flex items-center gap-2">
            {segment.speakerId && (
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: speakerColor(segment.speakerId) }}
              />
            )}
            <select
              value={segment.speakerId ?? ""}
              onChange={(e) => onUpdate(segment.id, "speakerId", e.target.value)}
              disabled={isActive || busy}
              className={`flex-1 px-3 py-2.5 rounded-lg text-sm border focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed appearance-none cursor-pointer ${
                isDark
                  ? "bg-zinc-800 border-zinc-700 text-white"
                  : "bg-white border-gray-300 text-gray-900"
              }`}
            >
              <option value="">Select speaker…</option>
              {speakers.map((sp) => (
                <option key={sp.id} value={sp.id}>
                  {sp.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="button"
          onClick={isCached ? onRegenerate : onGenerate}
          disabled={!segment.text.trim() || busy}
          className={`mt-5 flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${
            isCached
              ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700"
              : "bg-amber-600 hover:bg-amber-500 disabled:bg-zinc-700 text-white disabled:text-zinc-500"
          }`}
          title={isCached ? "Force a fresh take (bypass cache)" : "Generate audio for this segment"}
        >
          {isGenerating ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          {isCached ? "Regenerate" : "Generate"}
        </button>

        {isPlaying ? (
          <button
            type="button"
            onClick={onStop}
            className="mt-5 flex items-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-500 text-white rounded-lg font-medium transition-colors"
          >
            <Square className="w-4 h-4" />
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={onPlay}
            disabled={!segment.text.trim() || busy}
            className="mt-5 flex items-center gap-2 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 disabled:bg-zinc-800/50 text-white disabled:text-zinc-600 rounded-lg font-medium transition-colors border border-zinc-700 disabled:cursor-not-allowed"
          >
            <Play className="w-4 h-4" />
            Play
          </button>
        )}
      </div>

      <div>
        <label
          className={`block text-xs font-medium mb-1.5 ${
            isDark ? "text-zinc-400" : "text-gray-600"
          }`}
        >
          Text content
        </label>
        <textarea
          value={segment.text}
          onChange={(e) => onUpdate(segment.id, "text", e.target.value)}
          placeholder="Enter text for this segment…"
          disabled={isActive || busy}
          rows={3}
          className={`w-full px-4 py-3 rounded-lg text-sm border resize-none focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
            isDark
              ? "bg-zinc-800 border-zinc-700 text-white placeholder-zinc-500"
              : "bg-white border-gray-300 text-gray-900 placeholder-gray-400"
          }`}
        />
      </div>
    </div>
  );
}
