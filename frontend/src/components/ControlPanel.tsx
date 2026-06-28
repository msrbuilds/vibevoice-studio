import { useEffect, useState } from "react";
import { Moon, PanelRightClose, PanelRightOpen, Sun } from "lucide-react";
import type { ConfigResponse, EngineInfo } from "@/types/models";
import { EngineSelector } from "./EngineSelector";
import { CfgScaleBody } from "./CfgScaleControl";
import { ThemeToggle } from "./ThemeToggle";
import { getCfgHints } from "@/lib/engineHints";
import { ExaggerationBody } from "./ExaggerationControl";
import { CacheBody, useCacheData } from "./CachePanel";

const LS_KEY = "vs.controlPanel.open";

interface Props {
  isDark: boolean;
  theme: "light" | "dark";
  onThemeToggle: () => void;
  config: ConfigResponse | null;
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
  theme,
  onThemeToggle,
  config,
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
    return typeof window !== "undefined" ? window.innerWidth < 1200 : false;
  });

  const { data: cacheData, busy: cacheBusy, refresh: cacheRefresh, onClear: onCacheClear, onDelete: onCacheDelete } = useCacheData();

  useEffect(() => {
    localStorage.setItem(LS_KEY, collapsed ? "false" : "true");
  }, [collapsed]);

  const surface = isDark ? "bg-zinc-950" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const heading = isDark ? "text-zinc-500" : "text-gray-500";
  const subtle = isDark ? "text-zinc-500" : "text-gray-500";
  const bodyText = isDark ? "text-zinc-300" : "text-gray-700";
  const iconBtn = isDark
    ? "text-zinc-400 hover:text-teal-400"
    : "text-gray-400 hover:text-teal-600";

  const cfgHints = getCfgHints(activeEngine);
  const isChatterbox = activeEngine === "chatterbox";

  if (collapsed) {
    const ThemeIcon = theme === "dark" ? Sun : Moon;
    return (
      <aside
        className={`w-12 shrink-0 border-l flex flex-col items-center pt-4 transition-colors ${surface} ${border}`}
      >
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className={`p-2 rounded-lg transition-colors ${iconBtn}`}
          title="Open control panel"
        >
          <PanelRightOpen className="w-5 h-5" />
        </button>
        <button
          type="button"
          onClick={onThemeToggle}
          className={`p-2 rounded-lg transition-colors mt-2 ${iconBtn}`}
          title="Toggle theme"
        >
          <ThemeIcon className="w-5 h-5" />
        </button>
      </aside>
    );
  }

  return (
    <aside
      className={`w-80 shrink-0 border-l flex flex-col transition-colors ${surface} ${border}`}
    >
      {/* Header */}
      <div className={`p-4 border-b flex items-center justify-between ${border}`}>
        <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>
          Controls
        </h2>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className={`p-1 rounded transition-colors ${iconBtn}`}
          title="Collapse control panel"
        >
          <PanelRightClose className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Engine section */}
        <section>
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
        <section>
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

        {/* Cache section */}
        <section>
          <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            Cache
          </h3>
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
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            Refresh cache list
          </button>
        </section>

        {/* Appearance section */}
        <section>
          <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            Appearance
          </h3>
          <ThemeToggle theme={theme} onToggle={onThemeToggle} />
        </section>

        {/* Backend section */}
        {config && (
          <section>
            <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
              Backend
            </h3>
            <div className={`text-xs space-y-0.5 ${subtle} flex items-center gap-4`}>
              <div>device: <span className={bodyText}>{config.device}</span></div>
              <div>dtype: <span className={bodyText}>{config.dtype}</span></div>
              <div>sr: <span className={bodyText}>{config.sampling_rate} Hz</span></div>
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}

