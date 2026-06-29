import { Moon, Sun } from "lucide-react";
import { focusRing } from "@/lib/theme";

interface Props {
  theme: "light" | "dark";
  onToggle: () => void;
}

export function ThemeToggle({ theme, onToggle }: Props) {
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm border transition-colors ${
        isDark
          ? "border-zinc-700 hover:border-zinc-600 hover:bg-zinc-800 text-zinc-300"
          : "border-gray-300 hover:border-gray-400 hover:bg-gray-100 text-gray-700"
      } ${focusRing}`}
      title="Toggle theme"
    >
      {isDark ? (
        <>
          <Sun className="w-4 h-4" />
          <span>Light mode</span>
        </>
      ) : (
        <>
          <Moon className="w-4 h-4" />
          <span>Dark mode</span>
        </>
      )}
    </button>
  );
}
