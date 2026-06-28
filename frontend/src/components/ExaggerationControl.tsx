/**
 * Voice expressiveness / exaggeration slider body — only relevant for
 * the Chatterbox Multilingual V3 engine. Shared between ControlPanel and
 * any other consumer that wants this knob.
 */
export function ExaggerationBody({
  isDark,
  value,
  onChange,
}: {
  isDark: boolean;
  value: number;
  onChange: (v: number) => void;
}) {
  const set = (n: number) => {
    // Clamp to a safe range so a runaway slider doesn't crash generation.
    onChange(Math.max(0.0, Math.min(2.0, n)));
  };
  const summary = value.toFixed(2);
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span
          className={`text-xs font-medium ${
            isDark ? "text-zinc-400" : "text-gray-600"
          }`}
        >
          Value
        </span>
        <span className="text-sm font-mono text-teal-400">{summary}</span>
      </div>
      <input
        type="range"
        min={0.0}
        max={1.5}
        step={0.05}
        value={value}
        onChange={(e) => set(Number(e.target.value))}
        className="w-full accent-teal-500"
      />
      <div
        className={`flex justify-between text-[10px] ${
          isDark ? "text-zinc-600" : "text-gray-400"
        }`}
      >
        <span>neutral</span>
        <span>expressive</span>
        <span>very dramatic</span>
      </div>

      <div className="flex items-center gap-2 pt-1">
        {[0.0, 0.3, 0.5, 0.7, 1.0].map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => set(preset)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
              Math.abs(value - preset) < 0.025
                ? "bg-teal-600 text-white border-teal-500"
                : isDark
                  ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border-zinc-700"
                  : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
            }`}
          >
            {preset.toFixed(1)}
          </button>
        ))}
      </div>

      <p className={`text-xs ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
        Chatterbox-only. Higher values make the speaker sound more
        dramatic; lower values are calmer. Pairs with the
        <span className="text-teal-400"> CFG weight</span> slider above.
      </p>
    </div>
  );
}
