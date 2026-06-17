import { FileAudio, Play, Square, Volume2 } from "lucide-react";

interface Props {
  segmentCount: number;
  validCount: number;
  isPlayingAll: boolean;
  currentIndex: number;
  isExporting: boolean;
  isDark: boolean;
  onPlayAll: () => void;
  onStopAll: () => void;
  onExportAudio: () => void;
}

export function PlayerFooter({
  segmentCount,
  validCount,
  isPlayingAll,
  currentIndex,
  isExporting,
  isDark,
  onPlayAll,
  onStopAll,
  onExportAudio,
}: Props) {
  return (
    <div
      className={`fixed bottom-0 right-0 left-80 z-20 p-4 border-t ${
        isDark ? "bg-zinc-950 border-zinc-800" : "bg-gray-50 border-gray-200"
      }`}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Volume2 className="w-5 h-5 text-teal-400" />
          <div>
            <p className={`font-medium ${isDark ? "text-white" : "text-gray-900"}`}>
              Full podcast
            </p>
            <p className={`text-sm ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
              {isPlayingAll
                ? `Playing segment ${currentIndex + 1} of ${segmentCount}`
                : `${validCount} of ${segmentCount} segments ready`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {!isPlayingAll && (
            <button
              type="button"
              onClick={onExportAudio}
              disabled={validCount === 0 || isExporting}
              className="flex items-center gap-2 px-5 py-3 bg-zinc-700 hover:bg-zinc-600 disabled:bg-zinc-800 text-white disabled:text-zinc-500 rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
            >
              <FileAudio className="w-5 h-5" />
              Download Audio
            </button>
          )}

          {isPlayingAll ? (
            <button
              type="button"
              onClick={onStopAll}
              className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-500 text-white rounded-lg font-medium transition-colors"
            >
              <Square className="w-5 h-5" />
              Stop Podcast
            </button>
          ) : (
            <button
              type="button"
              onClick={onPlayAll}
              disabled={validCount === 0 || isExporting}
              className="flex items-center gap-2 px-6 py-3 bg-teal-600 hover:bg-teal-500 disabled:bg-zinc-700 text-white disabled:text-zinc-500 rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
            >
              <Play className="w-5 h-5" />
              Play Podcast
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
