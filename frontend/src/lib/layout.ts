/**
 * Pure layout helpers: map a viewport width to a tier and derive the
 * FIRST-LOAD default open/collapsed state of each side panel. Explicit user
 * toggles (persisted in localStorage) always override these defaults.
 *
 * Tiers (px):  xl >= 1440 | lg 1180–1439 | md 1024–1179 | sm < 1024
 */
export type WidthTier = "xl" | "lg" | "md" | "sm";

export function widthTier(w: number): WidthTier {
  if (w >= 1440) return "xl";
  if (w >= 1180) return "lg";
  if (w >= 1024) return "md";
  return "sm";
}

/** Voices are primary — keep open until the middle column gets tight. */
export function defaultVoiceLibraryOpen(w: number): boolean {
  const t = widthTier(w);
  return t === "xl" || t === "lg";
}

/** Controls are secondary — only open by default on the widest tier. */
export function defaultControlPanelOpen(w: number): boolean {
  return widthTier(w) === "xl";
}

/** Below the supported floor (1024px) we show a soft notice. */
export function showNarrowBanner(w: number): boolean {
  return w < 1024;
}
