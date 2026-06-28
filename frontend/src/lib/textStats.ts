export interface TextStats {
  chars: number;
  words: number;
  seconds: number;
}

/** ~2.5 words/sec (≈150 wpm) duration estimate. */
export function textStats(text: string): TextStats {
  const chars = text.length;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const seconds = Math.ceil(words / 2.5);
  return { chars, words, seconds };
}

export function fmtDuration(seconds: number): string {
  if (seconds < 60) return `~${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `~${m}m ${String(s).padStart(2, "0")}s`;
}
