import { Plus, RefreshCw } from "lucide-react";
import { SampleMenu } from "./SampleMenu";
import { ImportExportMenu } from "./ImportExportMenu";
import { useIsNarrow } from "@/hooks/useIsNarrow";
import type { Sample } from "@/lib/samples";

interface Props {
  validCount: number;
  cachedCount: number;
  busy: boolean;
  isDark: boolean;
  onAddSegment: () => void;
  onGenerateAll: () => void;
  onExportJson: () => void;
  onImportJson: (file: File) => void;
  onLoadSample: (sample: Sample) => void;
}

export function MiddleToolbar({
  validCount,
  cachedCount,
  busy,
  isDark,
  onAddSegment,
  onGenerateAll,
  onExportJson,
  onImportJson,
  onLoadSample,
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
              : "text-amber-100"
          }`}
        >
          {cachedCount}/{validCount}
        </span>
      )}
    </>
  );

  const generateDisabled = busy || cachedCount === validCount;

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 p-4 border-b ${
        isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
      }`}
    >
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onAddSegment}
          disabled={busy}
          title="Add a new segment"
          className="flex items-center gap-2 px-4 py-2.5 bg-teal-600 hover:bg-teal-500 disabled:bg-zinc-700 text-white disabled:text-zinc-500 rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
        >
          {addLabel}
        </button>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={onGenerateAll}
          disabled={generateDisabled}
          title={`Generate all uncached segments (${cachedCount}/${validCount} done)`}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${
            generateDisabled
              ? isDark
                ? "bg-zinc-800 text-zinc-500"
                : "bg-gray-100 text-gray-400"
              : "bg-amber-600 hover:bg-amber-500 text-white"
          }`}
        >
          {generateLabel}
        </button>

        <ImportExportMenu
          isDark={isDark}
          busy={busy}
          onExportJson={onExportJson}
          onImportJson={onImportJson}
        />

        <SampleMenu isDark={isDark} onLoad={onLoadSample} />
      </div>
    </div>
  );
}
