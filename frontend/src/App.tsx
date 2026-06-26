import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { ActionBar } from "@/components/ActionBar";
import { InstallChatterboxDialog } from "@/components/InstallChatterboxDialog";
import { PlayerFooter } from "@/components/PlayerFooter";
import { SegmentCard } from "@/components/SegmentCard";
import { Sidebar } from "@/components/Sidebar";
import { useConfig } from "@/hooks/useConfig";
import { useVoices } from "@/hooks/useVoices";
import { useEngine } from "@/hooks/useEngine";
import { ApiError, downloadPodcast, synthesizeWav, updateVoiceMeta } from "@/lib/api";
import {
  AudioPlayer,
  wavToPcm16,
} from "@/lib/audio";
import { loadSample, type Sample } from "@/lib/samples";
import { useProject } from "@/lib/store";
import type { CachedAudio, Project, Speaker, SynthSpeaker } from "@/types/models";
import { getDefaultCfgForEngine } from "@/lib/engineHints";

type Theme = "light" | "dark";

function isSegmentCached(
  segment: { id: string; text: string; speakerId: string | null },
  cache: Record<string, CachedAudio>,
  speakers: Speaker[],
): { cached: boolean; voice: string | null; signature: string } {
  const entry = cache[segment.id];
  if (!entry) return { cached: false, voice: null, signature: "" };
  const speaker = speakers.find((s) => s.id === segment.speakerId);
  const voice = speaker?.voice ?? null;
  if (!voice) return { cached: false, voice: null, signature: "" };
  const signature = `${segment.text}::${voice}::${segment.speakerId ?? ""}`;
  return { cached: entry.text === segment.text && entry.voice === voice, voice, signature };
}

export default function App() {
  const project = useProject();
  const { config, loading: configLoading, error: configError } = useConfig();
  const {
    voices,
    loading: voicesLoading,
    upload: uploadVoice,
    remove: removeVoice,
  } = useVoices();
  const {
    engines,
    activeName: activeEngine,
    setActive: setActiveEngine,
    ensureLoaded: ensureEngineLoaded,
    refresh: refreshEngines,
  } = useEngine();
  const supportsVoiceCloning =
    engines.find((e) => e.name === activeEngine)?.supports_voice_cloning ?? true;

  const [theme, setTheme] = useState<Theme>("dark");
  const [cfgScale, setCfgScale] = useState<number>(1.3);
  // Chatterbox Multilingual V3 only — voice expressiveness / dramatization.
  // Ignored by VibeVoice and Kokoro. Range 0.0–1.0+ (clamped to 0–2 server-side).
  const [exaggeration, setExaggeration] = useState<number>(0.5);
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [isPlayingAll, setIsPlayingAll] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(-1);
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState("");
  const [stopExport, setStopExport] = useState(false);
  const [toast, setToast] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const [installEngineOpen, setInstallEngineOpen] = useState(false);
  // Measured heights of the fixed top/bottom bars, so the segment list can
  // pad itself by exactly the rendered heights (avoids overlap if a bar
  // wraps to a second row at narrow viewport widths). Bumped initial
  // guesses to the largest plausible single-row value, and we add a
  // safety buffer below so a 1-2 px rounding error never causes overlap.
  const [actionBarH, setActionBarH] = useState<number>(88);
  const [playerFooterH, setPlayerFooterH] = useState<number>(96);

  const playerRef = useRef<AudioPlayer>(new AudioPlayer());
  const stopAllRef = useRef(false);

  // Default the first speaker's voice to the first available voice once loaded
  useEffect(() => {
    if (voices.length > 0 && project.speakers[0] && !project.speakers[0].voice) {
      project.setSpeakerVoice(project.speakers[0].id, voices[0]!.id);
    }
  }, [voices, project]);

  // Apply theme to <html> so Tailwind dark: variants work
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4500);
    return () => clearTimeout(t);
  }, [toast]);

  // Snap cfgScale to the active engine's default when the engine
  // changes (or on first mount if the persisted last-engine wasn't
  // VibeVoice). This keeps the slider visually centered in its new
  // range — e.g. switching from VibeVoice (1.3 in a 0.5–5.0 range)
  // to Chatterbox (default 0.5 in a 0.0–1.0 range) lands near the
  // middle instead of pinned at the right edge.
  useEffect(() => {
    if (!activeEngine) return;
    setCfgScale((current) => {
      const target = getDefaultCfgForEngine(activeEngine);
      // Only snap if the current value is way outside the new range —
      // i.e. it was clearly tuned for a different engine. This way
      // a deliberate user tweak on engine A still survives a quick
      // toggle to engine B and back.
      const otherEngines: Record<string, [number, number]> = {
        vibevoice: [0.5, 5.0],
        kokoro: [0.5, 5.0],
        chatterbox: [0.0, 1.0],
      };
      const [, max] = otherEngines[activeEngine] ?? [0.5, 5.0];
      // If current value is more than 10% beyond the new engine's max,
      // snap. Otherwise leave it (the user already dialed something in).
      return current > max * 1.1 ? target : current;
    });
  }, [activeEngine]);

  useEffect(() => {
    return () => {
      playerRef.current.close();
    };
  }, []);

  const showError = useCallback((err: unknown, fallback: string) => {
    const text = err instanceof ApiError ? err.message : err instanceof Error ? err.message : fallback;
    setToast({ kind: "error", text });
  }, []);

  // Filter the global voice catalog down to the active engine. The
  // sidebar shouldn't offer Kokoro's voices when VibeVoice is active
  // (and vice versa) — the backend will reject cross-engine requests
  // anyway.
  // Filter the global voice catalog down to voices the active engine can use.
  // - Kokoro: only its own built-in voice catalog (no voice cloning).
  // - VibeVoice and Chatterbox: both support voice cloning from arbitrary
  //   reference audio, so filesystem voices (tagged engine="vibevoice"
  //   by the registry) are usable by either. We show the same set of
  //   voices when either voice-cloning engine is active.
  // - If a future Chatterbox release ships a built-in voice catalog,
  //   those voices (engine="chatterbox") will also appear here.
  const displayedVoices = voices.filter((v) => {
    if (!activeEngine) return true;
    if (activeEngine === "kokoro") return v.engine === "kokoro";
    // Both VibeVoice and Chatterbox support cloning → show any voice
    // tagged with a voice-cloning engine. Today that's only "vibevoice"
    // (filesystem voices); if Chatterbox adds built-ins later, those
    // show up too.
    return v.engine === "vibevoice" || v.engine === "chatterbox";
  });

  // ---- generation ----

  const generateFor = useCallback(
    async (segmentId: string, options: { forceRegenerate?: boolean } = {}) => {
      const seg = project.segments.find((s) => s.id === segmentId);
      if (!seg || !seg.text.trim()) return;
      const speaker = project.speakers.find((s) => s.id === seg.speakerId);
      if (!speaker || !speaker.voice) {
        showError("No voice assigned to the speaker. Pick one in the sidebar.", "No voice");
        return;
      }
      const speakers: SynthSpeaker[] = [
        { name: speaker.name, voice: speaker.voice },
      ];

      setGeneratingId(segmentId);
      try {
        // The CFG slider is engine-aware: it maps to VibeVoice's
        // cfg_scale (range ~0.5–5.0) or Chatterbox's cfg_weight
        // (range 0.0–1.0, clamped server-side). Other engines ignore it.
        const isChatterbox = activeEngine === "chatterbox";
        const { audioData, cacheHash } = await synthesizeWav(seg.text, speakers, cfgScale, {
          forceRegenerate: options.forceRegenerate,
          cfgWeight: isChatterbox ? cfgScale : null,
          exaggeration: isChatterbox ? exaggeration : null,
        });
        project.cacheAudio(segmentId, {
          audioData,
          text: seg.text,
          voice: speaker.voice,
          ...(cacheHash ? { cacheHash } : {}),
        });
      } catch (err: unknown) {
        showError(err, "Synthesis failed");
      } finally {
        setGeneratingId(null);
      }
    },
    [project, showError, cfgScale, activeEngine],
  );

  // ---- playback ----

  const playCached = useCallback(
    async (segmentId: string) => {
      const cached = project.audioCache[segmentId];
      if (!cached) return;
      const pcm = wavToPcm16(cached.audioData);
      // Sample rate from cache; defaults to config's value.
      const sr = config?.sampling_rate ?? 24000;
      await playerRef.current.playPcm16(pcm, sr);
    },
    [project.audioCache, config],
  );

  const handlePlay = useCallback(
    async (segmentId: string) => {
      setPlayingId(segmentId);
      try {
        const seg = project.segments.find((s) => s.id === segmentId);
        if (!seg) return;
        const { cached } = isSegmentCached(seg, project.audioCache, project.speakers);
        if (!cached) {
          await generateFor(segmentId);
        }
        await playCached(segmentId);
      } catch (err) {
        showError(err, "Playback failed");
      } finally {
        setPlayingId((id) => (id === segmentId ? null : id));
      }
    },
    [project, generateFor, playCached, showError],
  );

  const handleStop = useCallback(() => {
    playerRef.current.stop();
    setPlayingId(null);
  }, []);

  const handleDownloadSegment = useCallback(
    (segmentId: string) => {
      const cached = project.audioCache[segmentId];
      if (!cached || cached.audioData.byteLength === 0) return;
      const blob = new Blob([cached.audioData], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vibevoice-segment-${segmentId.slice(0, 8)}.wav`;
      a.click();
      URL.revokeObjectURL(url);
    },
    [project.audioCache],
  );

  const handleUpdateVoiceMeta = useCallback(
    async (voiceId: string, meta: { name?: string; gender?: string; language?: string }) => {
      try {
        await updateVoiceMeta(voiceId, meta);
        window.location.reload();
      } catch (err) {
        showError(err, "Failed to update voice");
      }
    },
    [showError],
  );

  const handlePlayAll = useCallback(async () => {
    setIsPlayingAll(true);
    stopAllRef.current = false;
    try {
      for (let i = 0; i < project.segments.length; i++) {
        if (stopAllRef.current) break;
        const seg = project.segments[i]!;
        if (!seg.text.trim()) continue;
        setCurrentIndex(i);
        setPlayingId(seg.id);
        try {
          const { cached } = isSegmentCached(seg, project.audioCache, project.speakers);
          if (!cached) {
            setGeneratingId(seg.id);
            try {
              await generateFor(seg.id);
            } finally {
              setGeneratingId(null);
            }
          }
          await playCached(seg.id);
        } catch (err) {
          showError(err, "Playback failed");
        }
      }
    } finally {
      setIsPlayingAll(false);
      setCurrentIndex(-1);
      setPlayingId(null);
    }
  }, [project, generateFor, playCached, showError]);

  const handleStopAll = useCallback(() => {
    stopAllRef.current = true;
    playerRef.current.stop();
    setIsPlayingAll(false);
    setCurrentIndex(-1);
    setPlayingId(null);
  }, []);

  // ---- generation all ----

  const handleGenerateAll = useCallback(async () => {
    // Iterate per-segment so each segment's cache is populated with audio
    // that matches its own text+voice signature. This is N round-trips to
    // the model (slower than a single combined call) but it keeps the
    // cache consistent: per-segment Play won't re-generate.
    const valid = project.segments.filter((s) => s.text.trim());
    if (valid.length === 0) return;

    // Pre-check that all speakers are configured
    const speakersUsed = new Set<string>();
    for (const seg of valid) {
      if (!seg.speakerId) {
        showError("Some segments have no speaker assigned.", "Missing speaker");
        return;
      }
      const sp = project.speakers.find((s) => s.id === seg.speakerId);
      if (!sp || !sp.voice) {
        showError(
          "Some segments have no voice. Assign voices in the sidebar first.",
          "Missing voice",
        );
        return;
      }
      speakersUsed.add(sp.voice);
    }
    if (speakersUsed.size > 4) {
      showError(
        `This project uses ${speakersUsed.size} distinct voices; the 1.5B model supports up to 4.`,
        "Too many speakers",
      );
      return;
    }

    setIsExporting(true);
    setExportProgress("Starting…");
    try {
      for (let i = 0; i < valid.length; i++) {
        const seg = valid[i]!;
        // Skip already-cached segments
        const { cached } = isSegmentCached(seg, project.audioCache, project.speakers);
        if (cached) continue;

        setExportProgress(`Segment ${i + 1}/${valid.length}`);
        setGeneratingId(seg.id);
        try {
          await generateFor(seg.id);
        } finally {
          setGeneratingId(null);
        }
      }
    } catch (err: unknown) {
      showError(err, "Generate-all failed");
    } finally {
      setIsExporting(false);
      setExportProgress("");
    }
  }, [project, generateFor, showError]);

  // ---- import / export json ----

  const handleExportJson = useCallback(() => {
    const data = project.exportProject();
    const speakers = project.speakers;
    const blob = new Blob(
      [JSON.stringify({ project: data, speakers }, null, 2)],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `vibevoice-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [project]);

  const handleImportJson = useCallback(
    async (file: File) => {
      const text = await file.text();
      try {
        const data = JSON.parse(text) as {
          project?: Project;
          speakers?: Speaker[];
        };
        const proj = data.project ?? (data as unknown as Project);
        const speakers = data.speakers ?? project.speakers;
        project.loadProject(proj, speakers);
      } catch (err) {
        showError(err, "Invalid project file");
      }
    },
    [project, showError],
  );

  const handleLoadSample = useCallback(
    (sample: Sample) => {
      const { segments, speakers } = loadSample(sample);
      project.loadProject(
        { segments, createdAt: new Date().toISOString(), version: "1.0.0" },
        speakers,
      );
    },
    [project],
  );

  // ---- export audio ----

  const handleExportAudio = useCallback(async () => {
    const valid = project.segments.filter((s) => s.text.trim());
    if (valid.length === 0) {
      showError("No segments with text", "Nothing to export");
      return;
    }
    const payload: {
      text: string;
      voice: string;
      cfg_scale?: number;
      cache_hash?: string;
      cfg_weight?: number;
      exaggeration?: number;
      language_id?: string;
    }[] = [];
    const isChatterbox = activeEngine === "chatterbox";
    for (const seg of valid) {
      const speaker = project.speakers.find((s) => s.id === seg.speakerId);
      const voiceId = speaker?.voice;
      if (!voiceId) {
        showError(
          `Segment has no voice assigned (text: "${seg.text.slice(0, 40)}…").`,
          "Missing voice",
        );
        return;
      }
      // Pass the per-segment cache hash so the backend can detect when a
      // segment was regenerated and avoid serving a stale joined WAV.
      const cached = project.audioCache[seg.id];
      const cache_hash = cached?.cacheHash || undefined;
      payload.push({
        text: seg.text,
        voice: voiceId,
        cfg_scale: cfgScale,
        ...(cache_hash ? { cache_hash } : {}),
        ...(isChatterbox && cfgScale != null ? { cfg_weight: cfgScale } : {}),
        ...(isChatterbox ? { exaggeration } : {}),
      });
    }

    setIsExporting(true);
    setStopExport(false);
    setExportProgress("Preparing…");
    try {
      const { audioData, cacheHit, cacheHash } = await downloadPodcast(payload, 150);
      if (stopExport) return;
      setExportProgress(cacheHit ? "Using cached download" : "Encoding WAV…");
      const blob = new Blob([audioData], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vibevoice-podcast-${Date.now()}.wav`;
      a.click();
      URL.revokeObjectURL(url);
      setExportProgress(
        cacheHit
          ? `Done (cache hit · ${cacheHash?.slice(0, 12)}…)`
          : "Done",
      );
    } catch (err) {
      showError(err, "Download failed");
    } finally {
      setIsExporting(false);
      setExportProgress("");
    }
  }, [project, showError, cfgScale, activeEngine]);

  // ---- derived state ----

  const isDark = theme === "dark";
  const validCount = project.segments.filter((s) => s.text.trim()).length;
  const cachedCount = useMemo(
    () =>
      project.segments.filter((s) => {
        const { cached } = isSegmentCached(s, project.audioCache, project.speakers);
        return cached;
      }).length,
    [project.segments, project.audioCache, project.speakers],
  );
  const busy = isPlayingAll || isExporting || generatingId !== null;

  // ---- loading state ----

  if (configLoading || voicesLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="flex items-center gap-3 text-zinc-300">
          <Loader2 className="w-5 h-5 animate-spin text-teal-400" />
          Loading VibeVoice backend…
        </div>
      </div>
    );
  }

  if (configError) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
        <div className="max-w-md text-center">
          <h1 className="text-xl font-semibold text-white mb-2">Backend not reachable</h1>
          <p className="text-sm text-zinc-400 mb-4">
            Could not reach <code className="text-teal-300">/api/config</code>: {configError}
          </p>
          <p className="text-xs text-zinc-500">
            Start the backend in another terminal:
            <br />
            <code className="text-zinc-300">cd backend &amp;&amp; python cli.py --device cpu</code>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex min-h-screen ${isDark ? "bg-zinc-950" : "bg-gray-50"}`}>
      <Sidebar
        speakers={project.speakers}
        voices={displayedVoices}
        config={config}
        theme={theme}
        onThemeToggle={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        onAddSpeaker={project.addSpeaker}
        onUpdateSpeaker={project.updateSpeaker}
        onRemoveSpeaker={project.removeSpeaker}
        onSetSpeakerVoice={project.setSpeakerVoice}
        onUploadVoice={uploadVoice}
        onRemoveVoice={removeVoice}
        onUpdateVoiceMeta={handleUpdateVoiceMeta}
        supportsVoiceCloning={supportsVoiceCloning}
        activeEngine={activeEngine}
      />

      <main className="flex-1 ml-80 relative">
        <ActionBar
          segmentCount={project.segments.length}
          validCount={validCount}
          cachedCount={cachedCount}
          busy={busy}
          isDark={isDark}
          cfgScale={cfgScale}
          onCfgScaleChange={setCfgScale}
          exaggeration={exaggeration}
          onExaggerationChange={setExaggeration}
          engines={engines}
          activeEngine={activeEngine}
          onSelectEngine={async (name) => {
            try {
              await setActiveEngine(name);
            } catch (err) {
              showError(err, "Engine switch failed");
            }
          }}
          onLoadEngine={async (name) => {
            try {
              await ensureEngineLoaded(name);
            } catch (err) {
              showError(err, "Engine load failed");
            }
          }}
          onInstallEngine={() => setInstallEngineOpen(true)}
          onAddSegment={project.addSegment}
          onGenerateAll={handleGenerateAll}
          onExportJson={handleExportJson}
          onImportJson={handleImportJson}
          onLoadSample={handleLoadSample}
          onHeightChange={setActionBarH}
        />

        <div
          style={{
            paddingTop: actionBarH + 16,
            paddingBottom: playerFooterH + 16,
          }}
          className="px-6"
        >
          <div className="max-w-5xl mx-auto">
            {isExporting && (
              <div className="mb-6 p-4 bg-teal-900/30 rounded-xl border border-teal-600/30 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-5 h-5 text-teal-400 animate-spin" />
                  <div>
                    <p className="text-white font-medium">Exporting audio</p>
                    <p className="text-teal-300 text-sm">{exportProgress}</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setStopExport(true)}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg font-medium"
                >
                  Cancel
                </button>
              </div>
            )}

            {toast && (
              <div
                className={`mb-6 p-3 rounded-lg border text-sm ${
                  toast.kind === "error"
                    ? isDark
                      ? "bg-red-900/30 border-red-600/40 text-red-200"
                      : "bg-red-50 border-red-200 text-red-700"
                    : isDark
                      ? "bg-zinc-800 border-zinc-700 text-zinc-200"
                      : "bg-amber-50 border-amber-200 text-amber-800"
                }`}
              >
                {toast.text}
              </div>
            )}

            <div className="space-y-4">
              {project.segments.map((segment, index) => {
                const { cached } = isSegmentCached(segment, project.audioCache, project.speakers);
                return (
                  <SegmentCard
                    key={segment.id}
                    segment={segment}
                    index={index}
                    speakers={project.speakers}
                    busy={busy}
                    isPlaying={playingId === segment.id}
                    isGenerating={generatingId === segment.id}
                    isCached={cached}
                    canDelete={project.segments.length > 1}
                    theme={theme}
                    speakerColor={project.speakerColor}
                    onUpdate={project.updateSegment}
                    onRemove={project.removeSegment}
                    onGenerate={() => generateFor(segment.id)}
                    onRegenerate={() => generateFor(segment.id, { forceRegenerate: true })}
                    onPlay={() => handlePlay(segment.id)}
                    onStop={handleStop}
                    onDownload={() => handleDownloadSegment(segment.id)}
                  />
                );
              })}
            </div>
          </div>
        </div>

        <PlayerFooter
          segmentCount={project.segments.length}
          validCount={validCount}
          cachedCount={cachedCount}
          isPlayingAll={isPlayingAll}
          currentIndex={currentIndex}
          isExporting={isExporting}
          isDark={isDark}
          onPlayAll={handlePlayAll}
          onStopAll={handleStopAll}
          onExportAudio={handleExportAudio}
          onHeightChange={setPlayerFooterH}
        />
        {installEngineOpen && (
          <InstallChatterboxDialog
            isDark={isDark}
            onClose={() => setInstallEngineOpen(false)}
            onInstalled={() => {
              void refreshEngines();
            }}
          />
        )}
      </main>
    </div>
  );
}
