import { useEffect, useRef, useState } from "react";
import { Download, FileDown, FileUp, Upload } from "lucide-react";
import { focusRing } from "@/lib/theme";

interface Props {
  isDark: boolean;
  busy: boolean;
  onExportJson: () => void;
  onImportJson: (file: File) => void;
}

export function ImportExportMenu({ isDark, busy, onExportJson, onImportJson }: Props) {
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

  const buttonClass = `flex items-center gap-1.5 px-3 py-2 rounded-lg font-medium text-sm transition-colors border ${
    isDark
      ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
      : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
  } ${busy ? "opacity-50 cursor-not-allowed pointer-events-none" : ""} ${focusRing}`;

  const menuItemClass = `flex items-center gap-3 w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
    isDark ? "text-zinc-200 hover:bg-zinc-800" : "text-gray-700 hover:bg-gray-100"
  } ${focusRing}`;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={buttonClass}
        title="Import or export the project as JSON"
      >
        <Download className="w-4 h-4" />
        Import/Export
      </button>

      {open && (
        <div
          className={`absolute right-0 top-full mt-2 w-56 rounded-lg shadow-xl border z-30 overflow-hidden p-1 ${
            isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
          }`}
        >
          <button
            type="button"
            onClick={() => {
              onExportJson();
              setOpen(false);
            }}
            disabled={busy}
            className={menuItemClass}
          >
            <FileDown className="w-4 h-4 text-teal-400" />
            <span>Export JSON</span>
          </button>

          <label className={menuItemClass}>
            <FileUp className="w-4 h-4 text-teal-400" />
            <span>Import JSON</span>
            <input
              type="file"
              accept=".json"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onImportJson(file);
                e.target.value = "";
                setOpen(false);
              }}
              disabled={busy}
              className="hidden"
            />
          </label>

          <div
            className={`mt-1 pt-1 border-t px-3 py-2 text-[11px] ${
              isDark
                ? "border-zinc-800 text-zinc-400"
                : "border-gray-200 text-gray-600"
            }`}
          >
            <Upload className="w-3 h-3 inline mr-1" />
            Save or load a project file.
          </div>
        </div>
      )}
    </div>
  );
}
