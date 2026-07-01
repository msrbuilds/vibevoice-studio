import { useState } from "react";
import { Cpu, MemoryStick, HardDrive, Zap, Database, ChevronDown, ChevronUp } from "lucide-react";
import { useSystemStats } from "@/hooks/useSystemStats";
import type { MemStat } from "@/types/models";

interface Props {
  isDark: boolean;
}

const STORAGE_KEY = "vs.statusBar.open";

function readOpen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "false"; // default open
  } catch {
    return true;
  }
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(0)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

// Color tint by pressure. Returns Tailwind classes for the bar fill.
function barColor(pct: number, isDark: boolean): string {
  if (pct >= 90) return "bg-red-500";
  if (pct >= 75) return "bg-amber-500";
  return isDark ? "bg-zinc-500" : "bg-zinc-400";
}

function textColor(pct: number, isDark: boolean): string {
  if (pct >= 90) return "text-red-500";
  if (pct >= 75) return "text-amber-500";
  return isDark ? "text-zinc-400" : "text-zinc-500";
}

interface ChipProps {
  icon: React.ReactNode;
  label: string;
  pct: number;
  value: string;
  isDark: boolean;
}

function Chip({ icon, label, pct, value, isDark }: ChipProps) {
  return (
    <div className="flex items-center gap-1.5 whitespace-nowrap">
      <span className={isDark ? "text-zinc-500" : "text-zinc-400"}>{icon}</span>
      <span className={`font-medium ${isDark ? "text-zinc-300" : "text-zinc-600"}`}>{label}</span>
      <span className={`h-1.5 w-10 rounded-full overflow-hidden ${isDark ? "bg-zinc-800" : "bg-gray-200"}`}>
        <span
          className={`block h-full rounded-full ${barColor(pct, isDark)}`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </span>
      <span className={`tabular-nums ${textColor(pct, isDark)}`}>{value}</span>
    </div>
  );
}

function memValue(m: MemStat): string {
  return `${fmtBytes(m.used_bytes)}/${fmtBytes(m.total_bytes)}`;
}

export function HardwareStatusBar({ isDark }: Props) {
  const [open, setOpen] = useState(readOpen);
  const stats = useSystemStats(open);

  const toggle = () => {
    setOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  const surface = isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200";
  const dash = <span className={isDark ? "text-zinc-600" : "text-gray-400"}>—</span>;

  if (!open) {
    // Collapsed: thin strip (no polling).
    return (
      <div className={`flex items-center justify-between gap-2 px-2.5 py-1 border-b text-[11px] ${surface}`}>
        <span className={isDark ? "text-zinc-500" : "text-zinc-500"}>System monitor</span>
        <button
          onClick={toggle}
          className={`p-0.5 rounded ${isDark ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-gray-100 text-zinc-500"}`}
          aria-label="Show system monitor"
          title="Show system monitor"
        >
          <ChevronDown size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-x-4 gap-y-1 flex-wrap px-2.5 py-1.5 border-b text-[11px] ${surface}`}>
      {stats ? (
        <>
          <Chip icon={<Cpu size={13} />} label="CPU" pct={stats.cpu_percent} value={`${stats.cpu_percent.toFixed(0)}%`} isDark={isDark} />
          <Chip icon={<MemoryStick size={13} />} label="RAM" pct={stats.ram.percent} value={memValue(stats.ram)} isDark={isDark} />
          {stats.vram && (
            <Chip icon={<Zap size={13} />} label="VRAM" pct={stats.vram.percent} value={memValue(stats.vram)} isDark={isDark} />
          )}
          <Chip icon={<HardDrive size={13} />} label="Disk" pct={stats.disk.percent} value={memValue(stats.disk)} isDark={isDark} />
          <div className="flex items-center gap-1.5 whitespace-nowrap">
            <span className={isDark ? "text-zinc-500" : "text-zinc-400"}><Database size={13} /></span>
            <span className={`font-medium ${isDark ? "text-zinc-300" : "text-zinc-600"}`}>Cache</span>
            <span className={`tabular-nums ${isDark ? "text-zinc-400" : "text-zinc-500"}`}>{fmtBytes(stats.cache_bytes)}</span>
          </div>
        </>
      ) : (
        <span className={isDark ? "text-zinc-500" : "text-zinc-500"}>Loading system stats {dash}</span>
      )}
      <button
        onClick={toggle}
        className={`ml-auto p-0.5 rounded ${isDark ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-gray-100 text-zinc-500"}`}
        aria-label="Hide system monitor"
        title="Hide system monitor"
      >
        <ChevronUp size={14} />
      </button>
    </div>
  );
}
