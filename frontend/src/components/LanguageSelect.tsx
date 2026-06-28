import type { EngineLanguage } from "@/types/models";

interface Props {
  isDark: boolean;
  languages: EngineLanguage[];
  value: string | null;
  onChange: (code: string) => void;
}

export function LanguageSelect({ isDark, languages, value, onChange }: Props) {
  if (languages.length === 0) return null;
  const selectBg = isDark ? "bg-zinc-800 border-zinc-700 text-white" : "bg-white border-gray-300 text-gray-900";
  return (
    <select
      value={value ?? languages[0]!.code}
      onChange={(e) => onChange(e.target.value)}
      className={`border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-teal-500 ${selectBg}`}
    >
      {languages.map((l) => (
        <option key={l.code} value={l.code}>{l.label}</option>
      ))}
    </select>
  );
}
