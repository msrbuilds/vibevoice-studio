import { focusRing } from "@/lib/theme";

interface Props {
  isDark: boolean;
}

/**
 * Thin attribution strip pinned at the bottom of the middle column.
 * Shows the Voice Studio mark (light/dark variant) plus the product name,
 * with "MSR Builds" linking out to the GitHub org. Logo assets live in
 * `frontend/public/` and are served from the site root.
 */
export function BrandFooter({ isDark }: Props) {
  return (
    <footer
      className={`shrink-0 border-t px-6 py-2 flex items-center justify-center gap-2 ${
        isDark ? "border-zinc-800 text-zinc-500" : "border-gray-200 text-gray-500"
      }`}
    >
      <img
        src={isDark ? "/logo-dark-sm.png" : "/logo-light-sm.png"}
        alt="Voice Studio logo"
        width={20}
        height={20}
        className="w-5 h-5 rounded shrink-0"
      />
      <span className="text-xs">
        Voice Studio by{" "}
        <a
          href="https://github.com/msrbuilds"
          target="_blank"
          rel="noopener noreferrer"
          className={`font-medium underline decoration-dotted underline-offset-2 transition-colors ${
            isDark ? "hover:text-orange-400" : "hover:text-orange-600"
          } ${focusRing}`}
        >
          MSR Builds
        </a>
      </span>
    </footer>
  );
}
