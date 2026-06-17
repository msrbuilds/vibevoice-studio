import { Download, Plus, RefreshCw, Upload } from "lucide-react";
import { CachePanel } from "./CachePanel";
import { SampleMenu } from "./SampleMenu";
import type { Sample } from "@/lib/samples";


interface Props {
  segmentCount: number;
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

export function ActionBar({
  segmentCount,
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
  return (
    <div
      className={`fixed top-0 right-0 left-80 z-20 flex flex-wrap items-center justify-between gap-4 p-4 border-b ${
        isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
      }`}
    >
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onAddSegment}
          disabled={busy}
          className="flex items-center gap-2 px-4 py-2.5 bg-teal-600 hover:bg-teal-500 disabled:bg-zinc-700 text-white disabled:text-zinc-500 rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
        >
          <Plus className="w-5 h-5" />
          Add Segment
        </button>

        <span className={`text-sm ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
          {segmentCount} segment{segmentCount !== 1 ? "s" : ""}
          {validCount > 0 && (
            <span className="ml-2 text-teal-400">
              ({cachedCount}/{validCount} generated)
            </span>
          )}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onGenerateAll}
          disabled={busy || cachedCount === validCount}
          className="flex items-center gap-2 px-4 py-2.5 bg-amber-600 hover:bg-amber-500 disabled:bg-zinc-700 text-white disabled:text-zinc-500 rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
        >
          <RefreshCw className="w-4 h-4" />
          Generate All
        </button>

        <button
          type="button"
          onClick={onExportJson}
          disabled={busy}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border disabled:cursor-not-allowed ${
            isDark
              ? "bg-zinc-800 hover:bg-zinc-700 disabled:bg-zinc-800/50 text-zinc-300 hover:text-white disabled:text-zinc-600 border-zinc-700"
              : "bg-gray-100 hover:bg-gray-200 disabled:bg-gray-50 text-gray-700 hover:text-gray-900 disabled:text-gray-400 border-gray-300"
          }`}
        >
          <Download className="w-4 h-4" />
          Export JSON
        </button>

        <label
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors cursor-pointer border ${
            isDark
              ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
              : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
          } ${busy ? "opacity-50 cursor-not-allowed pointer-events-none" : ""}`}
        >
          <Upload className="w-4 h-4" />
          Import
          <input
            type="file"
            accept=".json"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onImportJson(file);
              e.target.value = "";
            }}
            disabled={busy}
            className="hidden"
          />
        </label>

        <SampleMenu isDark={isDark} onLoad={onLoadSample} />

        <CachePanel isDark={isDark} />
      </div>
    </div>
  );
}