import { useEffect, useRef, useState } from "react";
import { ChevronDown, Sparkles } from "lucide-react";
import { SAMPLES, loadSample, type Sample } from "@/lib/samples";

interface Props {
  isDark: boolean;
  onLoad: (sample: Sample) => void;
}

export function SampleMenu({ isDark, onLoad }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border ${
          isDark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
            : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
        }`}
        title="Load a sample script"
      >
        <Sparkles className="w-4 h-4" />
        Samples
        <ChevronDown className="w-3.5 h-3.5" />
      </button>

      {open && (
        <div
          className={`absolute right-0 top-full mt-2 w-80 rounded-lg shadow-xl border z-30 overflow-hidden ${
            isDark
              ? "bg-zinc-900 border-zinc-800"
              : "bg-white border-gray-200"
          }`}
        >
          <div className={`p-2 text-xs uppercase tracking-wide font-semibold ${
            isDark ? "text-zinc-500" : "text-gray-500"
          }`}>
            Load a sample
          </div>
          <div className="max-h-96 overflow-y-auto">
            {SAMPLES.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => {
                  onLoad(s);
                  setOpen(false);
                }}
                className={`block w-full text-left p-3 border-l-2 transition-colors ${
                  isDark
                    ? "border-transparent hover:border-teal-500 hover:bg-zinc-800"
                    : "border-transparent hover:border-teal-500 hover:bg-gray-50"
                }`}
              >
                <div className={`text-sm font-medium ${isDark ? "text-white" : "text-gray-900"}`}>
                  {s.name}
                </div>
                <div className={`text-xs mt-0.5 ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
                  {s.description}
                </div>
                <div className={`text-xs mt-1 ${isDark ? "text-zinc-600" : "text-gray-400"}`}>
                  {s.speakers.length} speaker{s.speakers.length !== 1 ? "s" : ""} ·{" "}
                  {s.segments.length} segment{s.segments.length !== 1 ? "s" : ""}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export { SAMPLES, loadSample };
export type { Sample };
