/**
 * Semantic color roles → AAA-tuned Tailwind class strings, the single source
 * of truth for the colors that previously failed contrast (see contrast.test.ts).
 * Each helper takes `isDark` and returns a className fragment.
 */
export const theme = {
  /** Primary body text. */
  text: (d: boolean) => (d ? "text-zinc-100" : "text-gray-900"),
  /** Secondary / label text. */
  textMuted: (d: boolean) => (d ? "text-zinc-300" : "text-gray-700"),
  /** Tertiary / meta / timestamps (was zinc-500 / gray-500 — failed). */
  textSubtle: (d: boolean) => (d ? "text-zinc-400" : "text-gray-600"),
  /** Uppercase section headings. */
  heading: (d: boolean) => (d ? "text-zinc-400" : "text-gray-600"),
  /** Icon-only buttons (was zinc-400 / gray-400 — gray-400 failed 3:1). */
  iconButton: (d: boolean) =>
    d ? "text-zinc-300 hover:text-orange-300" : "text-gray-600 hover:text-orange-700",
  /** Destructive icon buttons. */
  dangerIcon: (d: boolean) =>
    d ? "text-zinc-300 hover:text-red-300" : "text-gray-600 hover:text-red-700",
  /** Panel surface. */
  surface: (d: boolean) => (d ? "bg-zinc-950" : "bg-white"),
  /** Panel border. */
  border: (d: boolean) => (d ? "border-zinc-800" : "border-gray-200"),
} as const;

/**
 * Shared visible focus indicator (WCAG 2.4.7). Append to interactive elements.
 * The offset color is themed so the ring reads on both surfaces.
 */
export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-zinc-950";

/** Primary solid button base (orange). AA-compliant white-on-orange-700. */
export const primaryButton =
  "bg-orange-700 hover:bg-orange-600 text-white disabled:bg-zinc-700 disabled:text-zinc-400";
