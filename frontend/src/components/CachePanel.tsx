import { useEffect, useState } from "react";
import { Database, Trash2, X } from "lucide-react";
import { clearCache, deleteCacheEntry, listCache, type CacheListResponse } from "@/lib/api";

interface Props {
  isDark: boolean;
  onCountChange?: (count: number) => void;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(t: number): string {
  return new Date(t * 1000).toLocaleString();
}

export function CachePanel({ isDark, onCountChange }: Props) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<CacheListResponse | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const d = await listCache();
      setData(d);
      onCountChange?.(d.entry_count);
    } catch {
      // Cache endpoint may not be reachable; ignore
    }
  };

  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, 15_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onClear = async () => {
    if (!confirm("Clear all cached audio? Next synthesis will run the model again.")) return;
    setBusy(true);
    try {
      await clearCache();
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (hash: string) => {
    setBusy(true);
    try {
      await deleteCacheEntry(hash);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  if (!data) {
    return (
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border ${
          isDark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
            : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
        }`}
        title="Persistent synthesis cache"
      >
        <Database className="w-4 h-4" />
        Cache
      </button>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border ${
          isDark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
            : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
        }`}
        title="Persistent synthesis cache"
      >
        <Database className="w-4 h-4" />
        Cache
        <span className={`text-xs ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
          {data.entry_count}/{data.max_entries}
        </span>
      </button>

      {open && (
        <div
          className={`absolute right-0 top-full mt-2 w-96 rounded-lg shadow-xl border z-30 overflow-hidden ${
            isDark
              ? "bg-zinc-900 border-zinc-800"
              : "bg-white border-gray-200"
          }`}
        >
          <div className={`px-4 py-3 border-b ${isDark ? "border-zinc-800" : "border-gray-200"}`}>
            <div className="flex items-center justify-between">
              <div>
                <div className={`text-sm font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
                  Synthesis cache
                </div>
                <div className={`text-xs mt-0.5 ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
                  {data.directory}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClear}
                  disabled={busy || data.entry_count === 0}
                  className={`flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                    isDark
                      ? "bg-red-900/30 hover:bg-red-900/50 text-red-300 border border-red-800/50"
                      : "bg-red-50 hover:bg-red-100 text-red-700 border border-red-200"
                  }`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Clear all
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className={`p-1 rounded ${isDark ? "text-zinc-500 hover:text-zinc-300" : "text-gray-400 hover:text-gray-600"}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {data.entries.length === 0 ? (
              <div className={`px-4 py-6 text-center text-sm ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
                Empty. Cache hits will appear here.
              </div>
            ) : (
              <ul>
                {data.entries.map((e) => (
                  <li
                    key={e.hash}
                    className={`px-4 py-2.5 border-b last:border-b-0 flex items-start gap-2 ${
                      isDark ? "border-zinc-800" : "border-gray-100"
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <code className={`text-xs font-mono ${isDark ? "text-zinc-300" : "text-gray-700"}`}>
                          {e.hash.slice(0, 12)}…
                        </code>
                        <span className={`text-xs ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
                          {e.duration_sec.toFixed(1)}s · {formatBytes(e.size_bytes)}
                        </span>
                      </div>
                      <div className={`text-xs mt-0.5 ${isDark ? "text-zinc-600" : "text-gray-400"}`}>
                        {formatDate(e.created_at)} · {e.inference_ms > 0 ? `${e.inference_ms}ms` : "instant"}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onDelete(e.hash)}
                      disabled={busy}
                      className={`p-1 rounded shrink-0 ${isDark ? "text-zinc-500 hover:text-red-400" : "text-gray-400 hover:text-red-600"}`}
                      title="Delete this entry"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
