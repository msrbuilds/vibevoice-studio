import type { ProjectMode } from "@/types/models";

interface Props {
  isDark: boolean;
  mode: ProjectMode;
  onChange: (m: ProjectMode) => void;
}

export function ModeToggle({ isDark, mode, onChange }: Props) {
  const wrap = isDark ? "bg-zinc-800" : "bg-gray-100";
  const seg = (m: ProjectMode, label: string) => (
    <button type="button" onClick={() => onChange(m)}
      className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
        mode === m ? "bg-teal-600 text-white"
        : isDark ? "text-zinc-400 hover:text-zinc-200" : "text-gray-500 hover:text-gray-700"
      }`}>
      {label}
    </button>
  );
  return <div className={`inline-flex gap-1 p-1 rounded-lg ${wrap}`}>{seg("tts", "Text-to-Voice")}{seg("podcast", "Podcast")}</div>;
}
