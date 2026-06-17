import { Moon, Sun } from "lucide-react";

interface Props {
  theme: "light" | "dark";
  onToggle: () => void;
}

export function ThemeToggle({ theme, onToggle }: Props) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm border transition-colors
        border-zinc-700 hover:border-zinc-600 hover:bg-zinc-800
        text-zinc-300"
      title="Toggle theme"
    >
      {theme === "dark" ? (
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
