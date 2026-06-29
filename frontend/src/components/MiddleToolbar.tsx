import { Plus, RefreshCw } from "lucide-react";
import { SampleMenu } from "./SampleMenu";
import { ImportExportMenu } from "./ImportExportMenu";
import { ModeToggle } from "./ModeToggle";
import { useIsNarrow } from "@/hooks/useIsNarrow";
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
  const narrow = useIsNarrow();

  const addLabel = narrow ? <Plus className="w-5 h-5" /> : (
    <>
      <Plus className="w-5 h-5" />
      Add Segment
    </>
  );

  const generateLabel = narrow ? <RefreshCw className="w-4 h-4" /> : (
    <>
      <RefreshCw className="w-4 h-4" />
      Generate All
      {validCount > 0 && (
        <span
          className={`text-xs ml-1 ${
            cachedCount === validCount
              ? "text-teal-200"
              : "text-white"
          }`}
        >
          {cachedCount}/{validCount}
        </span>
      )}
    </>
  );

  const generateDisabled = busy || cachedCount === validCount;
  const isPodcast = mode === "podcast";

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 p-4 border-b ${
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
            className={`flex items-center gap-2 px-4 py-2.5 bg-teal-700 hover:bg-teal-600 disabled:bg-zinc-700 text-white disabled:text-zinc-400 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${focusRing}`}
          >
            {addLabel}
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
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${
              generateDisabled
                ? isDark
                  ? "bg-zinc-800 text-zinc-400"
                  : "bg-gray-100 text-gray-600"
                : "bg-amber-700 hover:bg-amber-600 text-white"
            } ${focusRing}`}
          >
            {generateLabel}
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
