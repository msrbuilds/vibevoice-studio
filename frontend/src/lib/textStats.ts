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

// Strong RTL scripts: Hebrew, Arabic (incl. Urdu/Persian), Syriac, Thaana,
// NKo, and the Arabic presentation forms.
const RTL_CHARS =
  /[֐-׿؀-ۿ܀-ݏݐ-ݿހ-޿ࢠ-ࣿיִ-﷿ﹰ-﻿]/g;

/**
 * True when `text` is predominantly a right-to-left script (Urdu, Arabic,
 * Hebrew, …). Uses a simple ratio so mixed content like an Urdu sentence with
 * an embedded "[confirmation-en]" tag still reads as RTL.
 */
export function isRtlText(text: string | null | undefined): boolean {
  if (!text) return false;
  const rtl = (text.match(RTL_CHARS) || []).length;
  const ltr = (text.match(/[A-Za-z]/g) || []).length;
  return rtl > ltr;
}
