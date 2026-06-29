import { useEffect, useRef, useState } from "react";

interface Props {
  url: string;
  progress: number; // 0..1 fraction of playback
  isDark: boolean;
  onSeek?: (fraction: number) => void;
  height?: number;
}

const NUM_BARS = 128;

/** Fetch + Web-Audio-decode a WAV, extract per-bucket peak amplitudes. */
async function computePeaks(url: string): Promise<number[]> {
  const res = await fetch(url);
  const buf = await res.arrayBuffer();
  const ctx = new AudioContext();
  try {
    const decoded = await ctx.decodeAudioData(buf);
    const data = decoded.getChannelData(0);
    const bucketSize = Math.floor(data.length / NUM_BARS);
    const peaks: number[] = [];
    for (let i = 0; i < NUM_BARS; i++) {
      let max = 0;
      const start = i * bucketSize;
      const end = start + bucketSize;
      for (let j = start; j < end; j++) {
        const abs = Math.abs(data[j]);
        if (abs > max) max = abs;
      }
      peaks.push(max);
    }
    // Normalize so the tallest bar = 1.0
    const globalMax = Math.max(...peaks, 1e-6);
    return peaks.map((p) => p / globalMax);
  } finally {
    void ctx.close();
  }
}

export function Waveform({ url, progress, isDark, onSeek, height = 140 }: Props) {
  const [peaks, setPeaks] = useState<number[] | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setPeaks(null);
    computePeaks(url)
      .then((p) => {
        if (!cancelled) setPeaks(p);
      })
      .catch(() => {
        if (!cancelled) setPeaks([]); // empty = flat baseline fallback
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onSeek || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    onSeek(fraction);
  };

  // Flat baseline while loading or on error
  const bars = peaks ?? Array(NUM_BARS).fill(0.08) as number[];

  return (
    <div
      ref={containerRef}
      className="relative flex items-end gap-[2px] cursor-pointer w-full select-none"
      style={{ height }}
      onClick={handleClick}
      role="slider"
      aria-label="Waveform seek"
      aria-valuenow={Math.round(progress * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {bars.map((peak, i) => {
        const played = i / NUM_BARS < progress;
        const barHeight = Math.max(peak * height, 3); // min 3 px so silence shows
        return (
          <div
            key={i}
            className={`flex-1 rounded-full transition-colors ${
              played
                ? "bg-teal-500"
                : isDark
                  ? "bg-zinc-600"
                  : "bg-gray-300"
            }`}
            style={{ height: barHeight }}
          />
        );
      })}
    </div>
  );
}
