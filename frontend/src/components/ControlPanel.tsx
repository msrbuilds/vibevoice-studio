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
  onDeleteWeights: (name: string) => void;
  onUninstallEngine: (name: string) => void;
  cfgScale: number;
  onCfgScaleChange: (v: number) => void;
  exaggeration: number;
  onExaggerationChange: (v: number) => void;
  quality?: "fast" | "balanced" | "high";
  onQualityChange?: (q: "fast" | "balanced" | "high") => void;
  qwenParams?: { temperature: number; topP: number; topK: number; repetitionPenalty: number; seed: number | null };
  onQwenParamsChange?: (p: { temperature: number; topP: number; topK: number; repetitionPenalty: number; seed: number | null }) => void;
  qwenDefaults?: { temperature: number; topP: number; topK: number; repetitionPenalty: number; seed: number | null };
}

export function ControlPanel({
  isDark,
  engines,
  activeEngine,
  onSelectEngine,
  onLoadEngine,
  onInstallEngine,
  onDownloadEngine,
  onDeleteWeights,
  onUninstallEngine,
  cfgScale,
  onCfgScaleChange,
  exaggeration,
  onExaggerationChange,
  quality,
  onQualityChange,
  qwenParams,
  onQwenParamsChange,
  qwenDefaults,
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
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100/80 border border-gray-200 rounded-lg">
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
            onDeleteWeights={onDeleteWeights}
            onUninstall={onUninstallEngine}
          />
        </section>

        {/* Settings section */}
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100/80 border border-gray-200 rounded-lg">
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

          {activeEngine === "voxcpm" && onQualityChange && (
            <div className="space-y-1.5 mt-4">
              <div className={`text-xs font-medium ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
                Quality
              </div>
              <div className="flex gap-1">
                {(["fast", "balanced", "high"] as const).map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => onQualityChange(q)}
                    className={`flex-1 px-2 py-1.5 text-xs font-medium rounded border transition-colors ${
                      (quality ?? "balanced") === q
                        ? "bg-orange-600 text-white border-orange-500 hover:bg-orange-500"
                        : isDark
                          ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700 border-zinc-700"
                          : "bg-gray-100 text-gray-600 hover:bg-gray-200 border-gray-300"
                    } ${focusRing}`}
                  >
                    {q[0].toUpperCase() + q.slice(1)}
                  </button>
                ))}
              </div>
              <p className={`text-[11px] ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
                Diffusion steps: Fast 5 · Balanced 10 · High 25. Higher = better quality, slower.
              </p>
            </div>
          )}

          {activeEngine === "qwen" && qwenParams && onQwenParamsChange && (
            <div className="space-y-2 mt-4">
              <div className={`text-xs font-medium ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
                Advanced generation
              </div>
              {([
                { key: "temperature", label: "Temperature", min: 0.1, max: 2.0, step: 0.05 },
                { key: "topP", label: "Top-p", min: 0.0, max: 1.0, step: 0.05 },
                { key: "topK", label: "Top-k", min: 0, max: 200, step: 1 },
                { key: "repetitionPenalty", label: "Repetition penalty", min: 1.0, max: 2.0, step: 0.05 },
              ] as const).map((f) => (
                <label key={f.key} className={`block text-[11px] ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
                  <span className="flex justify-between"><span>{f.label}</span><span>{qwenParams[f.key]}</span></span>
                  <input
                    type="range" min={f.min} max={f.max} step={f.step}
                    value={qwenParams[f.key]}
                    onChange={(e) => onQwenParamsChange({ ...qwenParams, [f.key]: Number(e.target.value) })}
                    className="w-full accent-orange-600"
                  />
                </label>
              ))}
              <label className={`block text-[11px] ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
                Seed (optional)
                <input
                  type="number"
                  value={qwenParams.seed ?? ""}
                  onChange={(e) => onQwenParamsChange({ ...qwenParams, seed: e.target.value === "" ? null : Number(e.target.value) })}
                  placeholder="random"
                  className={`mt-1 w-full border rounded-md px-2 py-1 text-xs focus:outline-none focus:border-orange-500 ${
                    isDark ? "bg-zinc-800 border-zinc-700 text-white" : "bg-white border-gray-300 text-gray-900"
                  }`}
                />
              </label>
              {qwenDefaults && (
                <button
                  type="button"
                  onClick={() => onQwenParamsChange(qwenDefaults)}
                  className={`text-[11px] underline ${isDark ? "text-zinc-400 hover:text-orange-400" : "text-gray-600 hover:text-orange-600"} ${focusRing}`}
                >
                  Reset to defaults
                </button>
              )}
            </div>
          )}
        </section>

        {/* Recent generations section (CacheBody renders its own heading + actions) */}
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100/80 border border-gray-200 rounded-lg">
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

