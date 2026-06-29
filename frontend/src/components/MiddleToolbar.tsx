import { Plus, RefreshCw } from "lucide-react";
import { SampleMenu } from "./SampleMenu";
import { ImportExportMenu } from "./ImportExportMenu";
import { ModeToggle } from "./ModeToggle";
import type { Sample, TtsSample } from "@/lib/samples";
import type { ProjectMode } from "@/types/models";
import { focusRing } from "@/lib/theme";

interface Props {
  validCount: number;
  cachedCount: number;
  busy: boolean;
  isDark: boolean;
  mode: ProjectMode | null;
  onModeChange: (m: ProjectMode) => void;
  onAddSegment: () => void;
  onGenerateAll: () => void;
  onExportJson: () => void;
  onImportJson: (file: File) => void;
  onLoadPodcastSample: (sample: Sample) => void;
  onLoadTtsSample: (sample: TtsSample) => void;
}

export function MiddleToolbar({
  validCount,
  cachedCount,
  busy,
  isDark,
  mode,
  onModeChange,
  onAddSegment,
  onGenerateAll,
  onExportJson,
  onImportJson,
  onLoadPodcastSample,
  onLoadTtsSample,
}: Props) {
  const generateDisabled = busy || cachedCount === validCount;
  const isPodcast = mode === "podcast";

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-2 @[1200px]:gap-3 p-3 @[1200px]:p-4 border-b ${
        isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
      }`}
    >
      <div className="flex items-center gap-3">
        {mode !== null && (
          <ModeToggle isDark={isDark} mode={mode} onChange={onModeChange} />
        )}
        {isPodcast && (
          <button
            type="button"
            onClick={onAddSegment}
            disabled={busy}
            title="Add a new segment"
            className={`flex items-center gap-1.5 px-3 py-2 bg-teal-700 hover:bg-teal-600 disabled:bg-zinc-700 text-white disabled:text-zinc-400 rounded-lg font-medium text-sm transition-colors disabled:cursor-not-allowed ${focusRing}`}
          >
            <Plus className="w-4 h-4" />
            <span className="hidden @[1100px]:inline">Add Segment</span>
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {isPodcast && (
          <button
            type="button"
            onClick={onGenerateAll}
            disabled={generateDisabled}
            title={`Generate all uncached segments (${cachedCount}/${validCount} done)`}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg font-medium text-sm transition-colors disabled:cursor-not-allowed ${
              generateDisabled
                ? isDark
                  ? "bg-zinc-800 text-zinc-400"
                  : "bg-gray-100 text-gray-600"
                : "bg-amber-700 hover:bg-amber-600 text-white"
            } ${focusRing}`}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span className="hidden @[1100px]:inline">Generate All</span>
            {validCount > 0 && (
              <span
                className={`text-xs ml-1 ${
                  cachedCount === validCount ? "text-teal-100" : "text-white"
                }`}
              >
                {cachedCount}/{validCount}
              </span>
            )}
          </button>
        )}

        <ImportExportMenu
          isDark={isDark}
          busy={busy}
          onExportJson={onExportJson}
          onImportJson={onImportJson}
        />

        {mode !== null && (
          <SampleMenu
            isDark={isDark}
            mode={mode}
            onLoadPodcast={onLoadPodcastSample}
            onLoadTts={onLoadTtsSample}
          />
        )}
      </div>
    </div>
  );
}
