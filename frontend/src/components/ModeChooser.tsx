import { Mic2, FileText } from "lucide-react";
import type { ProjectMode } from "@/types/models";
import { focusRing } from "@/lib/theme";

interface Props {
  isDark: boolean;
  onPick: (m: ProjectMode) => void;
}

export function ModeChooser({ isDark, onPick }: Props) {
  const card = isDark
    ? "bg-zinc-900 border-zinc-800 hover:border-orange-500"
    : "bg-white border-gray-200 hover:border-orange-500";
  const title = isDark ? "text-white" : "text-gray-900";
  const sub = isDark ? "text-zinc-400" : "text-gray-600";
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-3xl w-full">
        <button type="button" onClick={() => onPick("tts")}
          className={`text-left p-6 rounded-xl border transition-colors ${card} ${focusRing}`}>
          <FileText className="w-8 h-8 text-orange-400 mb-3" />
          <div className={`font-semibold ${title}`}>Text-to-Voice</div>
          <p className={`text-sm mt-1 ${sub}`}>Type or paste text and generate with a single voice.</p>
        </button>
        <button type="button" onClick={() => onPick("podcast")}
          className={`text-left p-6 rounded-xl border transition-colors ${card} ${focusRing}`}>
          <Mic2 className="w-8 h-8 text-orange-400 mb-3" />
          <div className={`font-semibold ${title}`}>Podcast</div>
          <p className={`text-sm mt-1 ${sub}`}>Build a multi-speaker conversation from segments.</p>
        </button>
      </div>
    </div>
  );
}
