import { FileAudio, Play, Square, Volume2 } from "lucide-react";
import { focusRing } from "@/lib/theme";

interface Props {
  segmentCount: number;
  validCount: number;
  cachedCount: number;
  isPlayingAll: boolean;
  currentIndex: number;
  isExporting: boolean;
  isDark: boolean;
  onPlayAll: () => void;
  onStopAll: () => void;
  onExportAudio: () => void;
}

export function InlinePlayer({
  segmentCount,
  validCount,
  cachedCount,
  isPlayingAll,
  currentIndex,
  isExporting,
  isDark,
  onPlayAll,
  onStopAll,
  onExportAudio,
}: Props) {
  const subText = isPlayingAll
    ? `Playing ${currentIndex + 1}/${segmentCount}`
    : cachedCount > 0
      ? `${segmentCount} segment${segmentCount !== 1 ? "s" : ""} · ${cachedCount}/${validCount} generated`
      : `${segmentCount} segment${segmentCount !== 1 ? "s" : ""}`;

  const downloadLabel = (
    <>
      <FileAudio className="w-5 h-5" />
      <span className="@max-[1100px]:hidden">Download Audio</span>
    </>
  );
  const playLabel = (
    <>
      <Play className="w-5 h-5" />
      <span className="@max-[1100px]:hidden">Play Podcast</span>
    </>
  );
  const stopLabel = (
    <>
      <Square className="w-5 h-5" />
      <span className="@max-[1100px]:hidden">Stop Podcast</span>
    </>
  );

  return (
    <div
      className={`p-4 border-t ${
        isDark ? "bg-zinc-950 border-zinc-800" : "bg-gray-50 border-gray-200"
      }`}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Volume2 className="w-5 h-5 text-teal-400 shrink-0" />
          <div className="min-w-0">
            <p className={`font-medium @max-[900px]:hidden ${isDark ? "text-white" : "text-gray-900"}`}>
              Full podcast
            </p>
            <p
              className={`text-sm truncate ${
                isDark ? "text-zinc-400" : "text-gray-600"
              }`}
              title={subText}
            >
              {subText}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {!isPlayingAll && (
            <button
              type="button"
              onClick={onExportAudio}
              disabled={validCount === 0 || isExporting}
              title="Download joined WAV"
              className={`flex items-center gap-2 px-5 py-3 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${
                isDark
                  ? "bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 text-white disabled:text-zinc-400"
                  : "bg-gray-200 hover:bg-gray-300 disabled:bg-gray-100 text-gray-900 disabled:text-gray-600"
              } ${focusRing}`}
            >
              {downloadLabel}
            </button>
          )}

          {isPlayingAll ? (
            <button
              type="button"
              onClick={onStopAll}
              title="Stop playback"
              className={`flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-500 text-white rounded-lg font-medium transition-colors ${focusRing}`}
            >
              {stopLabel}
            </button>
          ) : (
            <button
              type="button"
              onClick={onPlayAll}
              disabled={validCount === 0 || isExporting}
              title={`Play through all ${segmentCount} segments in order`}
              className={`flex items-center gap-2 px-6 py-3 bg-teal-700 hover:bg-teal-600 disabled:bg-zinc-700 text-white disabled:text-zinc-400 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${focusRing}`}
            >
              {playLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
