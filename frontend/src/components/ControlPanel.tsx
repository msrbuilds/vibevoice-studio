import { useEffect, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { defaultControlPanelOpen } from "@/lib/layout";
import type { EngineInfo } from "@/types/models";
import { EngineSelector } from "./EngineSelector";
import { CfgScaleBody } from "./CfgScaleControl";
import { getCfgHints } from "@/lib/engineHints";
import { ExaggerationBody } from "./ExaggerationControl";
import { CacheBody, useCacheData } from "./CachePanel";

const LS_KEY = "vs.controlPanel.open";

interface Props {
  isDark: boolean;
  engines: EngineInfo[];
  activeEngine: string | null;
  onSelectEngine: (name: string) => Promise<void>;
  onLoadEngine: (name: string) => Promise<void>;
  onInstallEngine: (name: string) => void;
  onDownloadEngine: (name: string) => void;
  cfgScale: number;
  onCfgScaleChange: (v: number) => void;
  exaggeration: number;
  onExaggerationChange: (v: number) => void;
}

export function ControlPanel({
  isDark,
  engines,
  activeEngine,
  onSelectEngine,
  onLoadEngine,
  onInstallEngine,
  onDownloadEngine,
  cfgScale,
  onCfgScaleChange,
  exaggeration,
  onExaggerationChange,
}: Props) {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    const stored = localStorage.getItem(LS_KEY);
    if (stored !== null) return stored === "false";
    return typeof window !== "undefined"
      ? !defaultControlPanelOpen(window.innerWidth)
      : false;
  });

  const { data: cacheData, busy: cacheBusy, refresh: cacheRefresh, onClear: onCacheClear, onDelete: onCacheDelete } = useCacheData();

  useEffect(() => {
    localStorage.setItem(LS_KEY, collapsed ? "false" : "true");
  }, [collapsed]);

  const surface = isDark ? "bg-zinc-950" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const heading = isDark ? "text-zinc-400" : "text-gray-600";
  const iconBtn = isDark
    ? "text-zinc-400 hover:text-orange-400"
    : "text-gray-600 hover:text-orange-600";

  const cfgHints = getCfgHints(activeEngine);
  const isChatterbox = activeEngine === "chatterbox";

  if (collapsed) {
    return (
      <aside
        className={`w-12 shrink-0 border-l flex flex-col items-center pt-4 transition-colors ${surface} ${border}`}
      >
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className={`p-2 rounded-lg transition-colors ${iconBtn} ${focusRing}`}
          title="Open control panel"
        >
          <PanelRightOpen className="w-5 h-5" />
        </button>
      </aside>
    );
  }

  return (
    <aside
      className={`w-80 shrink-0 border-l flex flex-col transition-colors ${surface} ${border}`}
    >
      {/* Header */}
      <div className={`p-4 xxl:p-5 border-b flex items-center justify-between ${border}`}>
        <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>
          Controls
        </h2>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className={`p-1 rounded transition-colors ${iconBtn} ${focusRing}`}
          title="Collapse control panel"
        >
          <PanelRightClose className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Engine section */}
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100 border-gray-200 rounded-lg">
          <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            Engine
          </h3>
          <EngineSelector
            isDark={isDark}
            engines={engines}
            activeName={activeEngine}
            onSelect={onSelectEngine}
            onLoad={onLoadEngine}
            onInstall={onInstallEngine}
            onDownload={onDownloadEngine}
          />
        </section>

        {/* Settings section */}
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100 border-gray-200 rounded-lg">
          <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            {isChatterbox ? "CFG weight (voice fidelity)" : "Voice fidelity (CFG)"}
          </h3>
          <CfgScaleBody
            isDark={isDark}
            value={cfgScale}
            onChange={onCfgScaleChange}
            hints={cfgHints}
          />

          {isChatterbox && (
            <>
              <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 mt-4 ${heading}`}>
                Voice expressiveness (Chatterbox)
              </h3>
              <ExaggerationBody
                isDark={isDark}
                value={exaggeration}
                onChange={onExaggerationChange}
              />
            </>
          )}
        </section>

        {/* Recent generations section (CacheBody renders its own heading + actions) */}
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100 border-gray-200 rounded-lg">
          <CacheBody
            isDark={isDark}
            data={cacheData}
            busy={cacheBusy}
            onClear={onCacheClear}
            onDelete={onCacheDelete}
          />
          <button
            type="button"
            onClick={() => void cacheRefresh()}
            disabled={cacheBusy}
            className={`w-full text-xs font-medium py-1 rounded mt-1 ${
              isDark
                ? "text-zinc-400 hover:text-zinc-200"
                : "text-gray-600 hover:text-gray-700"
            } ${focusRing}`}
          >
            Refresh list
          </button>
        </section>
      </div>
    </aside>
  );
}

