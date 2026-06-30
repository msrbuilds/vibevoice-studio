# Qwen3-TTS CustomVoice Engine Integration — Design

**Date:** 2026-06-30
**Status:** Approved design → ready for implementation plan
**Author:** Voice Studio by MSR

## Summary

Add **Qwen3-TTS-12Hz-1.7B-CustomVoice** (`Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`) as a sixth TTS engine. It is a ~1.7B-param discrete multi-codebook LM TTS from the Qwen team (Alibaba), with **9 built-in premium voices**, **free-text style instruction** control, **10 languages + auto-detect**, and the full set of **HF sampling quality knobs**. Apache-2.0.

Unlike the cloning engines (VibeVoice/Chatterbox/OmniVoice/VoxCPM), CustomVoice does **not** clone from a reference clip — it selects one of 9 curated speakers and steers it with an optional natural-language `instruct` string. In this app it therefore behaves like a **built-in-voice engine (à la Kokoro)** plus an always-available style prompt and an advanced sampling-parameter panel.

Because `qwen-tts` hard-pins `transformers==4.57.3` (incompatible with every other engine's pinned stack), it runs as an **isolated-venv worker proxy**, the established OmniVoice/VoxCPM pattern.

This integration exposes the model's full surface: all 9 voices, the style prompt, all 10 languages (+ Auto), and all quality/sampling settings. Streaming is intentionally out of scope (see Non-Goals).

## Goals

- Register `qwen` as a first-class engine, selectable from the engine picker, with the same install / download / delete-weights / uninstall lifecycle as OmniVoice/VoxCPM.
- Expose the **9 built-in voices** as a Kokoro-style built-in catalog, labeled with trait + native language.
- Expose the **free-text style prompt** (`instruct`) as an always-available optional field (new engine capability, independent of the Clone/Design/Auto voice-mode toggle).
- Expose all **10 languages + Auto** via the existing language selector.
- Expose all **quality/sampling settings** (temperature, top_p, top_k, repetition_penalty, seed) in a collapsible Advanced panel, folded into the cache key.

## Non-Goals

- **Voice cloning / reference audio.** CustomVoice has no reference-clip cloning; that is the sibling `…-Base` model. `supports_voice_cloning()` returns `False`.
- **Clone/Design/Auto voice modes.** There is no "auto" or reference mode; the engine is always "pick a built-in voice + optional style." `supports_voice_modes()` returns `False`.
- **Streaming** (`generate` streaming path). Qwen supports ~97 ms streaming, but the API is undocumented and the app's per-segment disk cache / multi-speaker concat assume whole-WAV results. `supports_streaming()` returns `False`; `/stream` stays a stub.
- **Sibling Qwen models** (VoiceDesign, Base/clone, 0.6B variants) — natural future engines, but out of scope here.
- Changing any existing engine's behavior (OmniVoice/Chatterbox/VibeVoice/Kokoro/VoxCPM untouched, except the additive capability flag + style-prompt generalization).

## Background: the Qwen3-TTS CustomVoice API

The worker drives the `qwen-tts` package (PyPI `qwen-tts`):

```python
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="sdpa",   # flash_attention_2 optional (needs flash-attn)
)

wavs, sr = model.generate_custom_voice(
    text="...",
    language="Auto",        # or one of the 10 languages
    speaker="Vivian",       # one of the 9 built-in voices
    instruct="Very happy.", # optional free-text style control
    # **gen_kwargs forwarded to HF model.generate:
    # temperature=, top_p=, top_k=, repetition_penalty=, max_new_tokens=, ...
)
sf.write("output.wav", wavs[0], sr)
```

- `generate_custom_voice` returns `(wavs, sr)` — `wavs` is a list of float numpy arrays (take `wavs[0]` for single text); `sr` is the audio sample rate (value undocumented; **"12 Hz" is the tokenizer frame rate, not the audio sample rate** — almost certainly 24000; confirmed in Task 1).
- `speaker` ∈ the 9 names below. `language` ∈ {Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian, Auto}. `instruct` is optional natural-language style/emotion/tone/prosody/speed control.
- Extra kwargs are forwarded to HF `model.generate` (sampling/quality params).

> The exact `generate_custom_voice` signature and accepted kwargs are **confirmed against the installed package in implementation Task 1** before the worker is finalized; this spec is corrected if it differs.

### The 9 built-in voices

| Speaker (id) | Trait | Native language |
|---|---|---|
| Vivian | bright, slightly edgy young female | zh |
| Serena | warm, gentle young female | zh |
| Uncle_Fu | seasoned male, low mellow timbre | zh |
| Dylan | youthful Beijing male, clear natural | zh (Beijing) |
| Eric | lively Chengdu male, husky brightness | zh (Sichuan) |
| Ryan | dynamic male, strong rhythmic drive | en |
| Aiden | sunny American male, clear midrange | en |
| Ono_Anna | playful Japanese female, light nimble | ja |
| Sohee | warm Korean female, rich emotion | ko |

Voices are cross-lingual: any speaker can speak any of the 10 languages (the `language` arg states the text's language).

## Architecture

### Isolated worker proxy (mirrors VoxCPM/OmniVoice)

- `QwenEngine` (`backend/core/engines/qwen_engine.py`) is a near-copy of `VoxCPMEngine`: lifecycle (`load`/`unload`/`is_loaded`/`installed`/`downloaded`), `_exchange`/`_start_stderr_drain`/`_kill`, temp-WAV audio handoff.
- `_ready_marker` = `backend/venv-qwen/.qwen-ready`.
- `downloaded()` probes the shared HF cache via `core/model_cache.py::model_downloaded("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")`.
- Worker (`backend/qwen_worker.py`) sets `HF_HOME`/`HUGGINGFACE_HUB_CACHE` env at `backend/models/`, like the other workers.

### Capabilities

| Capability | Value |
|---|---|
| `name` / `display_name` | `qwen` / `Qwen3-TTS CustomVoice` |
| `sample_rate()` | `24000` (confirmed in Task 1) |
| `max_speakers()` | `1` |
| `supports_voice_cloning()` | `False` |
| `supports_voice_modes()` | `False` |
| `supports_style_prompt()` | `True` (NEW capability — see below) |
| `supports_streaming()` | `False` |
| `default_cfg_scale()` | `None` (no CFG; the slider is a no-op, like Kokoro) |
| `languages()` | 10 languages + `Auto` |
| `available_voices()` | the 9 built-in voices (registered into `VoiceRegistry`) |

The 9 voices are returned by `available_voices()` as `VoiceInfo` objects (id = the bare speaker name, e.g. `Vivian`; name = "Vivian — bright young female"; gender + language from the table) and merged into the registry at startup exactly like Kokoro's catalog. They appear in the voice library only when Qwen is active (engine-tagged).

## New capability: `supports_style_prompt`

A new boolean on the `Engine` ABC + `EngineInfo`, **distinct** from `supports_voice_modes`. When true, the UI shows an **optional free-text "Style (optional)" field** next to each speaker's voice picker (in both `SpeakerRoster` and `TtsEditor`), with no Clone/Design/Auto toggle. The value rides the existing per-speaker `instruct` field → worker `instruct=`.

- `Engine.supports_style_prompt()` defaults to `False`; `QwenEngine` overrides to `True`. (OmniVoice/VoxCPM keep `False` — their style is surfaced via the voice-mode toggle / clone-style field, which is unchanged.)
- `SynthService` sends `instruct` for a `supports_style_prompt` engine whenever it is non-empty, regardless of `voice_mode` (which is `None` for Qwen). Empty/whitespace → omitted.
- Free text, no fixed vocabulary (unlike OmniVoice's `DESIGN_CHIPS`).

## Quality settings: Advanced panel (Qwen-only)

A collapsible **"Advanced generation"** section in the right `ControlPanel`, rendered only when Qwen is active:

- **temperature** (e.g. 0.1–1.5), **top_p** (0–1), **top_k** (int), **repetition_penalty** (e.g. 1.0–2.0) — sliders/inputs seeded with the model's defaults — plus an optional **seed** integer field and a **Reset to defaults** button.
- New optional fields on `EngineSynthRequest` (Qwen-only, ignored by other engines), mirroring how `cfg_weight`/`exaggeration` are Chatterbox-only:
  - `temperature: float | None`, `top_p: float | None`, `top_k: int | None`, `repetition_penalty: float | None`, `seed: int | None`.
- Threaded through `SynthRequestBody` (with Pydantic bounds) → `SynthService` → `EngineSynthRequest` → worker `generate_custom_voice(**gen_kwargs)`.
- **`max_new_tokens` is computed automatically** in the worker from the input text length with a generous ceiling (long lines never truncate; short lines aren't capped). Not a user knob.
- All quality params (plus voice, language, style) **fold into the synth cache key** so different settings never collide. Panel values persist in localStorage.
- CFG: Qwen has no CFG — `engineHints.ts` gets a `qwen` entry marking the CFG slider a no-op (like Kokoro/OmniVoice).

## Language handling

`languages()` returns the 10 languages + `Auto` (default). The selection rides the existing `language_id` field (as Chatterbox does) → worker `language=`. Default `Auto` (the model auto-detects). The frontend `LanguageSelect` is already engine-driven from `EngineInfo.languages`, so no new component is needed.

## Synthesis request flow

- **`EngineSynthRequest`** (`backend/core/engines/__init__.py`) gains the 5 Qwen quality fields above (additive, defaulted `None`).
- **`SynthService`** (`backend/services/synthesize.py`):
  - Resolve `instruct` for a `supports_style_prompt` engine (sent whenever non-empty; no voice_mode gating).
  - Pass `language_id` (the chosen language, default Auto) through as today.
  - Thread the quality fields from `SynthRequestBody` into `EngineSynthRequest`.
  - Extend `_voice_cache_key()` (or the surrounding key construction) to fold `instruct`, `language_id`, and the quality params for Qwen so cache slots never collide (additions: `|in=`, `|lang=` already exist; add `|temp=`, `|tp=`, `|tk=`, `|rp=`, `|seed=` when present).
- **`QwenEngine._build_synth_msg`**: `speaker = req.voice_id`; `language = req.language_id or "Auto"`; `instruct = req.instruct or None`; quality kwargs included only when set.

## Worker dispatch (`qwen_worker.py`)

`_build_generate_kwargs(req)` composes the `generate_custom_voice` call:

```
text       = req["text"].strip()        # required
speaker    = req["speaker"]             # required (one of the 9)
language   = req.get("language") or "Auto"
instruct   = (req.get("instruct") or "").strip() or None
kwargs = {"text": text, "language": language, "speaker": speaker}
if instruct: kwargs["instruct"] = instruct
for k in ("temperature","top_p","top_k","repetition_penalty","seed"):
    if req.get(k) is not None: kwargs[k] = req[k]
kwargs["max_new_tokens"] = _auto_max_new_tokens(text)   # computed, capped
wavs, sr = model.generate_custom_voice(**kwargs); arr = wavs[0]
```

Writes `arr` as a mono 16-bit PCM WAV at `sr` (the model's returned rate). Mirrors `voxcpm_worker.py` for the stdio protocol, fd-redirection, and WAV writing.

> `seed` handling: if the package doesn't accept `seed` directly, the worker seeds torch (`torch.manual_seed`) before generation. Confirmed in Task 1.

## Lifecycle (install / download / delete / uninstall) — all reused

- **Install** — `studio.py` gains `cmd_install_qwen` + `_ensure_qwen_env()` (copy of `_ensure_voxcpm_env`: create `backend/venv-qwen`, `pip install -r requirements-qwen.txt`, force-reinstall a CUDA-matched torch via a new `envdetect.detect_qwen_cuda_tag()`, write `.qwen-ready` last). New subcommand `install-qwen`. Wire `EngineEnvInstaller("install-qwen")` into `app.state.engine_installers`. New `backend/requirements-qwen.txt` = single line `qwen-tts` (torch installed separately).
- **Download** — add `qwen` to `DOWNLOADABLE` + `MODEL_CATALOG` (`repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"`, size confirmed at impl, estimated ~3.5 GB). Add to the frontend `DownloadModelDialog` + `DeleteWeightsDialog` size maps.
- **Delete weights** — add `qwen` to `ModelDeleter.DELETABLE`.
- **Uninstall env** — add `EngineEnvUninstaller("qwen", em=engine_manager)` to `app.state.engine_uninstallers`; add `qwen` to `engine_uninstall.UNINSTALLABLE` and the frontend `EngineSelector` uninstall gating set.

## CUDA / Python / system constraints

- `detect_qwen_cuda_tag()` mirrors `detect_voxcpm_cuda_tag()` (nvidia-smi → cu126/cu128). Pin a known-good torch in `_ensure_qwen_env`.
- **Python 3.9–3.13** (per `qwen-tts` `requires-python`). No special guard beyond the repo's existing 3.10+ baseline.
- **`attn_implementation` defaults to `sdpa`** to avoid the flash-attn build dependency on Windows; flash-attn is optional and not installed by default.
- **`sox` system dependency**: `qwen-tts` lists `sox`; if the install or model load needs the `sox` binary on PATH, document it in setup (audio I/O otherwise uses `soundfile`). Verified at impl.

## Frontend changes

- **Types** (`types/models.ts`): add `supports_style_prompt: boolean` to `EngineInfo`; add the 5 quality fields to the synth request typing/wrappers.
- **Capability gating**: a small generalization so the per-speaker style field shows for `supports_style_prompt` engines. Reuse the `instruct`/`voiceDesign` per-speaker plumbing already added for OmniVoice/VoxCPM; the difference is the field shows unconditionally (no mode toggle) when `supports_style_prompt`.
- **`SpeakerRoster` + `TtsEditor`**: when `supportsStylePrompt`, render the optional "Style (optional)" field beneath the voice picker (no toggle, no chips). For non-voice-mode engines this is the only voice-mode-adjacent control.
- **`ControlPanel`**: the Advanced generation panel (Qwen-only) with the 5 quality controls + reset; owned by `App.tsx` state + localStorage, threaded into `synthesizeWav` (and the export payload) gated on `activeEngine === "qwen"`.
- **`engineHints.ts`**: a `qwen` CFG entry marking the slider a no-op.
- **`EngineSelector` / dialogs**: qwen in the uninstall gating set + the size label maps.

## Testing

Mirrors VoxCPM, all stubbed (no weights, no GPU):

- **Worker** (`tests/test_qwen_worker.py`): `_build_generate_kwargs` table — speaker/language/instruct mapping, empty-instruct omission, quality-kwarg pass-through, `max_new_tokens` auto-cap, seed handling — with a fake `qwen_tts` model; end-to-end `_synth` writes a WAV at the model's sr.
- **Engine proxy** (`tests/test_qwen_engine.py`): capability flags (incl. `supports_style_prompt=True`, `supports_voice_cloning=False`, `supports_voice_modes=False`), `_build_synth_msg` mapping (voice_id→speaker, language_id→language default Auto, instruct, quality fields), `installed()`/`downloaded()` gating.
- **Built-in voices**: `available_voices()` returns the 9 with correct ids/metadata.
- **Capability API** (`tests/test_engines_capabilities.py` additions): `/api/engines` + `/api/config` expose `supports_style_prompt` (qwen true, others false).
- **Cache keys** (`tests/test_synthesize.py` additions): voice/language/instruct/quality combinations produce distinct keys; identical inputs collide.
- **Setup helpers**: `detect_qwen_cuda_tag` mapping.
- **Lifecycle endpoints**: extend the parametrized install/delete/uninstall tests to include `qwen`.
- **Frontend**: style-field renders for `supports_style_prompt`; Advanced panel renders Qwen-only; quality values thread into the request; capability gating.

## File inventory

**New (backend):** `core/engines/qwen_engine.py`, `qwen_worker.py`, `requirements-qwen.txt`, `tests/test_qwen_worker.py`, `tests/test_qwen_engine.py`.
**Modified (backend):** `core/engines/__init__.py` (quality fields + `supports_style_prompt` ABC method + `info()`), `core/engine_manager.py`, `config.py`, `app.py`, `services/synthesize.py`, `api/schemas.py`, `api/engines.py`, `api/health.py` (capability flag), `scripts/download_models.py`, `services/model_download.py`, `services/model_delete.py`, `services/engine_uninstall.py`, `studio.py`, `tools/envdetect.py`, `tests/test_setup_helpers.py`, `tests/test_synthesize.py`, `tests/test_engines_capabilities.py`.
**Modified (frontend):** `types/models.ts`, `lib/engineHints.ts`, `lib/api.ts`, `components/SpeakerRoster.tsx`, `components/TtsEditor.tsx`, `components/ControlPanel.tsx`, `components/EngineSelector.tsx`, `components/DownloadModelDialog.tsx`, `components/DeleteWeightsDialog.tsx`, `App.tsx`.

## Open risks (carried into the plan)

1. **Output sample rate** confirmed against the real `sr` return in Task 1 (assumed 24 kHz).
2. **`generate_custom_voice` signature + accepted gen kwargs** (esp. whether `seed` is accepted, exact quality param names) confirmed in Task 1.
3. **Model weights size** confirmed against the HF repo for the download catalog (estimated ~3.5 GB).
4. **`sox` system dependency** + flash-attn optionality validated in the install flow.
