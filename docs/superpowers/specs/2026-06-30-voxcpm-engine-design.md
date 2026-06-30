# VoxCPM2 Engine Integration — Design

**Date:** 2026-06-30
**Status:** Approved design → ready for implementation plan
**Author:** Voice Studio by MSR

## Summary

Add **VoxCPM2** (`openbmb/VoxCPM2`) as a fifth TTS engine in Voice Studio by MSR. VoxCPM2 is a 2B-parameter, tokenizer-free, diffusion-autoregressive multilingual TTS model (30 languages, 48 kHz output, Apache-2.0, ~8 GB VRAM). It supports voice **design** (natural-language voice descriptions), voice **cloning**, **controllable cloning** (clone + style steering), and **ultimate cloning** (transcript-guided max fidelity).

Because `voxcpm` requires `torch>=2.5` / CUDA ≥12 plus a heavy dependency tail (`funasr`, `modelscope`, `datasets<4`, `gradio>=6`, `torchcodec`), it cannot safely share VibeVoice's pinned main venv. It is therefore integrated as an **isolated-venv worker proxy**, identical in shape to the existing OmniVoice and Chatterbox engines.

This integration exposes VoxCPM2's **full feature parity**: all five generation modes, a CFG control, an inference-quality control, and the per-voice transcript needed for ultimate cloning. Streaming is intentionally out of scope (see Non-Goals).

## Goals

- Register `voxcpm` as a first-class engine, selectable from the engine picker, with the same install / download / delete-weights / uninstall lifecycle as OmniVoice.
- Expose all five generation modes: **auto, design, clone, controllable clone, ultimate clone**.
- Add a CFG control (mapped to VoxCPM's `cfg_value`) and a Quality control (mapped to `inference_timesteps`).
- Add an optional per-voice **reference transcript** field that automatically upgrades clones to ultimate cloning.
- Generalize the existing OmniVoice-only Clone/Design/Auto toggle into a capability-driven, multi-engine component (no second hardcoded engine-name branch).

## Non-Goals

- **Streaming** (`generate_streaming`). The app's per-segment disk cache, multi-speaker PCM concatenation, and thread-serialized executor all assume whole-WAV results. Streaming transport is not required for "full parity" of the five generation *modes*, and the `/stream` WebSocket remains a stub. `supports_streaming()` returns `False`.
- ASR / automatic transcription of reference clips. The reference transcript is user-entered (or left blank).
- Changing how any existing engine behaves. OmniVoice/Chatterbox/VibeVoice/Kokoro are untouched except for the shared toggle generalization (which preserves OmniVoice behavior).

## Background: the VoxCPM2 API

The worker drives the `voxcpm` Python package (PyPI `voxcpm` ≥2.0.3):

```python
from voxcpm import VoxCPM
model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)

wav = model.generate(
    text="...",
    reference_wav_path=None,   # clone / controllable clone
    prompt_wav_path=None,      # ultimate clone (reference audio)
    prompt_text=None,          # ultimate clone (reference transcript)
    cfg_value=2.0,             # CFG (≈ VibeVoice cfg_scale)
    inference_timesteps=10,    # quality/speed (5 fast … 25 high)
    seed=...,
)   # -> float32 numpy array @ model.tts_model.sample_rate (48000)
```

**Critical API detail:** voice **design** and **style steering** are expressed *inline* as a parenthetical prefix in `text` — e.g. `"(A young woman, gentle and sweet)Hello!"` — **not** via a separate `instruct=` argument (this is the one structural difference from the OmniVoice worker, which uses `instruct=`). The worker composes the prefixed text.

> The exact `generate()` signature (especially the dual `prompt_wav_path` + `reference_wav_path` for ultimate cloning) is **confirmed against the installed package in implementation Task 1** before the worker is written, and this spec is corrected if the package differs.

## Architecture

### Isolated worker proxy (mirrors OmniVoice)

```
main process (FastAPI)                      backend/venv-voxcpm
┌─────────────────────────┐   JSON/stdio   ┌──────────────────────────┐
│ VoxCPMEngine (proxy)     │ ─────────────► │ voxcpm_worker.py         │
│  - spawn worker          │                │  ops: load/synth/shutdown│
│  - newline-JSON exchange │ ◄───────────── │  drives voxcpm.VoxCPM     │
│  - stderr drain thread   │   temp WAV     │  writes 48k PCM WAV       │
└─────────────────────────┘                └──────────────────────────┘
```

- `VoxCPMEngine` is a near-copy of `OmniVoiceEngine`: same lifecycle (`load`/`unload`/`is_loaded`/`installed`/`downloaded`), same `_exchange`/`_start_stderr_drain`/`_kill` internals, same temp-WAV audio handoff.
- `_ready_marker` = `backend/venv-voxcpm/.voxcpm-ready`.
- `downloaded()` probes the shared HF cache via `core/model_cache.py::model_downloaded("openbmb/VoxCPM2")` (weights live in `backend/models/`, shared between main process and worker).
- Worker passes `HF_HOME` / `HUGGINGFACE_HUB_CACHE` env pointing at `backend/models/` exactly like the OmniVoice worker.

### Capabilities

| Capability | Value |
|---|---|
| `name` / `display_name` | `voxcpm` / `VoxCPM2` |
| `sample_rate()` | `48000` |
| `max_speakers()` | `1` |
| `supports_voice_cloning()` | `True` |
| `supports_streaming()` | `False` |
| `default_cfg_scale()` | `2.0` |
| `languages()` | `[]` (auto-detected from text; no language dropdown) |
| `available_voices()` | `[]` (no built-in voices) |

## The five generation modes

The modes are **two independent toggles plus one auto-upgrade**, dispatched in the worker by `(mode, has_ref, has_style, has_transcript)`:

| UI state | Reference voice | Style text | Voice transcript | `generate(...)` arguments |
|---|---|---|---|---|
| **Auto** | – | – | – | `generate(text)` |
| **Design** | – | ✓ (`instruct`) | – | `generate("(instruct)" + text)` |
| **Clone** | ✓ | – | – | `generate(text, reference_wav_path=ref)` |
| **Controllable clone** | ✓ | ✓ (`instruct`) | – | `generate("(instruct)" + text, reference_wav_path=ref)` |
| **Ultimate clone** | ✓ | – | ✓ | `generate(text, prompt_wav_path=ref, prompt_text=transcript, reference_wav_path=ref)` |
| **Ultimate + controllable** | ✓ | ✓ | ✓ | `generate("(instruct)" + text, prompt_wav_path=ref, prompt_text=transcript, reference_wav_path=ref)` |

- The UI mode toggle is **Clone / Design / Auto** (same three as OmniVoice).
- **Controllable clone** = Clone mode with an optional inline "Style (optional)" text field.
- **Ultimate clone** is **automatic**: whenever the selected voice has a stored `reference_transcript`, the worker upgrades a clone to the prompt-guided form. No separate UI mode.
- An empty style string downgrades Design → Auto (a blank box never errors), mirroring OmniVoice's `design → auto` fallback.

### Mode resolution (worker `_build_call`)

```
mode      = req.voice_mode or ("clone" if ref else "auto")
style     = (req.instruct or "").strip()
transcript= (req.reference_text or "").strip()
if mode == "design" and not style: mode = "auto"

prefixed  = f"({style}){text}" if style and mode in ("design","clone") else text
# design  -> generate(prefixed)
# auto    -> generate(text)
# clone:
#   if transcript: generate(prefixed, prompt_wav_path=ref, prompt_text=transcript, reference_wav_path=ref)
#   else:          generate(prefixed, reference_wav_path=ref)
```

## Data model change: per-voice reference transcript

The only schema change. An optional free-text transcript of a voice's reference clip, enabling ultimate cloning.

- **`backend/services/voices.py`** — add `reference_transcript: str | None = None` to `VoiceInfo`; load/persist it in the `voices.json` sidecars (both `voices/voices.json` and `uploads/voices.json`) via `update_meta()`.
- **`backend/api/schemas.py`** — add `reference_transcript` to `VoiceInfoModel` (output) and `VoiceMetaUpdate` (input).
- **`frontend/src/types/models.ts`** — add `reference_transcript?: string | null` to the `Voice` type.
- **`VoiceLibrary`** (frontend) — add an optional "Reference transcript" textarea to the voice edit UI, saved via the existing voice-meta update path.

The transcript is a property of the **voice**, set once and reused across every segment that uses that voice.

## Synthesis request flow

- **`backend/core/engines/__init__.py`** — add `reference_text: str | None = None` to `EngineSynthRequest` (carries the per-voice transcript). Existing fields reused: `cfg_scale` → `cfg_value`, `inference_steps` → `inference_timesteps`, `voice_mode`, `instruct`, `reference_audio`.
- **`backend/services/synthesize.py`** —
  - Resolve the selected voice's `reference_transcript` (via the voice registry) and set `EngineSynthRequest.reference_text`.
  - Extend `_voice_cache_key()` to fold the transcript and the quality (timesteps) into the key, alongside the existing `|vm=` / `|in=` segments, so ultimate vs standard clones and Fast/Balanced/High results never collide. Proposed additions: `|rt=<sha8(transcript)>` and `|ts=<timesteps>`.

## Controls (right panel)

- **CFG** — reuse the existing CFG slider. `lib/engineHints.ts` gains a `voxcpm` mapping: slider → `cfg_value`, range ~1.0–3.0, default 2.0, carried by `cfg_scale`. (VibeVoice = `cfg_scale`, Chatterbox = `cfg_weight`, VoxCPM = `cfg_value`.)
- **Quality** — a new VoxCPM-only segmented control: **Fast / Balanced / High** → `inference_timesteps` **5 / 10 / 25** (default Balanced/10). Carried by the **existing** `inference_steps` field (already plumbed end-to-end). Persisted in localStorage; folded into the cache key.

## Frontend: generalize the voice-mode toggle

Today the Clone/Design/Auto toggle is gated on `activeEngine === "omnivoice"` and lives in `lib/omnivoice.ts` + `SpeakerRoster.tsx`.

- Add capability flags to `EngineInfo` (backend `engine_info`/schema): `supports_voice_modes: bool` and `supports_style_clone: bool`. OmniVoice: `voice_modes=True, style_clone=False`. VoxCPM: `voice_modes=True, style_clone=True`. Others: both `False`.
- Gate the toggle on `engine.supports_voice_modes` instead of a hardcoded name.
- Rename `lib/omnivoice.ts` → `lib/voiceModes.ts` (keep `effectiveMode`, mode types). OmniVoice's `DESIGN_CHIPS` / `NONVERBAL_TAGS` stay OmniVoice-specific; VoxCPM uses **free-text** style/design (no fixed vocab).
- When `supports_style_clone` is true and the speaker is in **Clone** mode, render the optional inline "Style (optional)" field (§ five modes).

This is the only refactor, and it directly serves this feature (avoids a divergent second hardcoded engine path).

## Install / Download / Delete / Uninstall (all reused)

- **Install** — `studio.py` gains `cmd_install_voxcpm` + `_ensure_voxcpm_env()` (copy of `_ensure_omnivoice_env`: create `backend/venv-voxcpm`, `pip install -r requirements-voxcpm.txt`, force-reinstall CUDA-matched `torch`/`torchaudio` via a new `envdetect.detect_voxcpm_cuda_tag()`, write `.voxcpm-ready` **last**). Add subcommand `install-voxcpm`. Wire `EngineEnvInstaller("install-voxcpm")` into `app.state.engine_installers`. New file `backend/requirements-voxcpm.txt` (single line `voxcpm`).
- **Download** — add `voxcpm` to `ModelDownloader.DOWNLOADABLE` and to `MODEL_CATALOG` in `backend/scripts/download_models.py` (`repo_id="openbmb/VoxCPM2"`, size confirmed at impl, estimated ~5 GB). Add to frontend `DownloadModelDialog` `MODEL_SIZES`.
- **Delete weights** — `voxcpm` auto-covered by `ModelDeleter.DELETABLE`; add to frontend `DeleteWeightsDialog` `MODEL_SIZES`.
- **Uninstall env** — add `EngineEnvUninstaller("voxcpm", em=engine_manager)` to `app.state.engine_uninstallers`; add `voxcpm` to the frontend gating set (currently `chatterbox|omnivoice`) in `EngineSelector`.

## CUDA / Python constraints

- `detect_voxcpm_cuda_tag()` mirrors `detect_omnivoice_cuda_tag()` (nvidia-smi → cu126/cu128 for torch ≥2.5/2.8). Pin a known-good torch version in `_ensure_voxcpm_env` (e.g. matching the OmniVoice torch line unless VoxCPM requires otherwise — verified at impl).
- **Python version**: `voxcpm` (via `torchcodec`/`funasr`) needs the venv's Python `<3.13`. `_ensure_voxcpm_env` must check the host Python version and fail with a clear message ("VoxCPM requires Python 3.10–3.12") rather than producing a broken venv.

## Testing

Mirrors OmniVoice's test suite, all with stubs (no weights, no GPU):

- **Worker** (`tests/test_voxcpm_worker.py`): JSON protocol (load/synth/shutdown), and a `_build_call` dispatch table asserting the correct `generate()` arguments for each of the six rows in the modes table (including the inline `(style)` prefixing and the dual `prompt_wav_path`/`reference_wav_path` for ultimate clone). Uses a fake `voxcpm` model.
- **Engine proxy** (`tests/test_voxcpm_engine.py`): fake worker Python; assert load/synth/unload, `installed()`/`downloaded()` gating, error surfacing on worker crash.
- **Install/uninstall/delete endpoints**: extend the existing parametrized engine-env tests to include `voxcpm`.
- **Cache keys** (`tests/test_synthesize.py` additions): assert the 5 modes + transcript + quality produce distinct keys and that identical inputs collide.
- **Setup helpers** (`tests/test_setup_helpers.py`): `detect_voxcpm_cuda_tag` mapping; Python-version guard.
- **Frontend**: `voiceModes` `effectiveMode` derivation; capability-flag gating renders the toggle for voxcpm/omnivoice only; Clone-mode style field appears only when `supports_style_clone`.

## File inventory

**New (backend):** `core/engines/voxcpm_engine.py`, `voxcpm_worker.py`, `requirements-voxcpm.txt`, `tests/test_voxcpm_worker.py`, `tests/test_voxcpm_engine.py`.
**New (frontend):** `lib/voiceModes.ts` (renamed from `omnivoice.ts`).
**Modified (backend):** `core/engine_manager.py`, `core/engines/__init__.py`, `config.py`, `app.py`, `services/voices.py`, `services/synthesize.py`, `api/schemas.py`, `api/engines.py` (capability flags only), `scripts/download_models.py`, `services/model_download.py`, `studio.py`, `tools/envdetect.py`, `tests/test_setup_helpers.py`, `tests/test_synthesize.py`.
**Modified (frontend):** `types/models.ts`, `lib/engineHints.ts`, `components/SpeakerRoster.tsx`, `components/ControlPanel.tsx`, `components/VoiceLibrary.tsx`, `components/EngineSelector.tsx`, `components/DownloadModelDialog.tsx`, `components/DeleteWeightsDialog.tsx`, plus the `omnivoice.ts` import sites.

## Open risks (carried into the plan)

1. `generate()` signature confirmed in Task 1 before the worker is written.
2. VoxCPM2 weights size confirmed against the HF repo for the download catalog.
3. Python `<3.13` constraint enforced in the installer with a clear error.
4. Heavy venv footprint (~several GB incl. `funasr`/`modelscope`/`datasets`/`gradio`) — acceptable, isolated, uninstallable.
