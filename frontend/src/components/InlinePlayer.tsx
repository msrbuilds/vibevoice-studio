import { FileAudio, Play, Square, Volume2 } from "lucide-react";
import { useIsNarrow } from "@/hooks/useIsNarrow";

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
  const narrow = useIsNarrow();

  const subText = isPlayingAll
    ? `Playing ${currentIndex + 1}/${segmentCount}`
    : cachedCount > 0
      ? `${segmentCount} segment${segmentCount !== 1 ? "s" : ""} · ${cachedCount}/${validCount} generated`
      : `${segmentCount} segment${segmentCount !== 1 ? "s" : ""}`;

  const downloadLabel = narrow ? <FileAudio className="w-5 h-5" /> : (
    <>
      <FileAudio className="w-5 h-5" />
      Download Audio
    </>
  );

  const playLabel = narrow ? <Play className="w-5 h-5" /> : (
    <>
      <Play className="w-5 h-5" />
      Play Podcast
    </>
  );

  const stopLabel = narrow ? <Square className="w-5 h-5" /> : (
    <>
      <Square className="w-5 h-5" />
      Stop Podcast
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
            {!narrow && (
              <p className={`font-medium ${isDark ? "text-white" : "text-gray-900"}`}>
                Full podcast
              </p>
            )}
            <p
              className={`${narrow ? "text-sm" : "text-sm"} truncate ${
                isDark ? "text-zinc-500" : "text-gray-500"
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
                  ? "bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 text-white disabled:text-zinc-500"
                  : "bg-gray-200 hover:bg-gray-300 disabled:bg-gray-100 text-gray-900 disabled:text-gray-400"
              }`}
            >
              {downloadLabel}
            </button>
          )}

          {isPlayingAll ? (
            <button
              type="button"
              onClick={onStopAll}
              title="Stop playback"
              className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-500 text-white rounded-lg font-medium transition-colors"
            >
              {stopLabel}
            </button>
          ) : (
            <button
              type="button"
              onClick={onPlayAll}
              disabled={validCount === 0 || isExporting}
              title={`Play through all ${segmentCount} segments in order`}
              className="flex items-center gap-2 px-6 py-3 bg-teal-600 hover:bg-teal-500 disabled:bg-zinc-700 text-white disabled:text-zinc-500 rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
            >
              {playLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
