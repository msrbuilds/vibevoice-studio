import { useLayoutEffect, useRef } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { SampleMenu } from "./SampleMenu";
import { ImportExportMenu } from "./ImportExportMenu";
import { EngineSelector } from "./EngineSelector";
import { SettingsMenu } from "./SettingsMenu";
import { useIsNarrow } from "@/hooks/useIsNarrow";
import type { EngineInfo } from "@/types/models";
import type { Sample } from "@/lib/samples";

interface Props {
  segmentCount: number;
  validCount: number;
  cachedCount: number;
  busy: boolean;
  isDark: boolean;
  cfgScale: number;
  onCfgScaleChange: (v: number) => void;
  // Chatterbox Multilingual V3 only — voice expressiveness. Forwarded
  // to SettingsMenu; ignored when the active engine isn't Chatterbox.
  exaggeration?: number;
  onExaggerationChange?: (v: number) => void;
  engines: EngineInfo[];
  activeEngine: string | null;
  onSelectEngine: (name: string) => Promise<void>;
  onLoadEngine: (name: string) => Promise<void>;
  onInstallEngine: (name: string) => void;
  onAddSegment: () => void;
  onGenerateAll: () => void;
  onExportJson: () => void;
  onImportJson: (file: File) => void;
  onLoadSample: (sample: Sample) => void;
  /**
   * Emitted whenever the bar's measured height changes. App.tsx uses this
   * to push the segment list down by exactly the bar's actual height, so
   * the bar can wrap to a second row on narrow viewports without overlapping.
   */
  onHeightChange?: (h: number) => void;
}

export function ActionBar({
  validCount,
  cachedCount,
  busy,
  isDark,
  cfgScale,
  onCfgScaleChange,
  exaggeration,
  onExaggerationChange,
  engines,
  activeEngine,
  onSelectEngine,
  onLoadEngine,
  onInstallEngine,
  onAddSegment,
  onGenerateAll,
  onExportJson,
  onImportJson,
  onLoadSample,
  onHeightChange,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const narrow = useIsNarrow();

  // ResizeObserver → push measured height to parent so content below can
  // pad itself by exactly the bar's rendered height. Avoids the overlap
  // bug when the bar wraps onto a second row at narrow widths.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !onHeightChange) return;
    const ro = new ResizeObserver(([entry]) => {
      // Use borderBoxSize when available — it includes borders + padding,
      // matching the bar's actual visual footprint. Falls back to
      // offsetHeight which has the same semantics.
      const h =
        entry.borderBoxSize?.[0]?.blockSize ??
        el.offsetHeight;
      onHeightChange(h);
    });
    ro.observe(el);
    // Fire once with initial measurement (ResizeObserver only fires on changes).
    onHeightChange(el.offsetHeight);
    return () => ro.disconnect();
  }, [onHeightChange]);

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
      ref={ref}
      className={`fixed top-0 right-0 left-80 z-20 flex flex-wrap items-center justify-between gap-3 p-4 border-b ${
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

        <EngineSelector
          isDark={isDark}
          engines={engines}
          activeName={activeEngine}
          onSelect={onSelectEngine}
          onLoad={onLoadEngine}
          onInstall={onInstallEngine}
        />

        <SettingsMenu
          isDark={isDark}
          cfgScale={cfgScale}
          onCfgScaleChange={onCfgScaleChange}
          activeEngine={activeEngine}
          exaggeration={exaggeration}
          onExaggerationChange={onExaggerationChange}
        />
      </div>
    </div>
  );
}
