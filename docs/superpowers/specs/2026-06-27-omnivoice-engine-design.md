# OmniVoice Engine (Spec A — clone) — Design

**Date:** 2026-06-27
**Status:** Approved (pending spec review)
**Part of:** OmniVoice integration, split into **Spec A — engine + install + voice cloning** (this doc) and **Spec B — voice-design + auto modes + per-speaker mode toggle** (future).

## Problem / goal

Add **OmniVoice** (k2-fsa/OmniVoice) as a fourth TTS engine in Voice Studio. OmniVoice is a 0.6 B zero-shot multilingual TTS model (fine-tuned from Qwen3-0.6B, 24 kHz output, Apache-2.0) with voice cloning, voice design (speaker-attribute prompts), auto voice, 600+ languages, and non-verbal tags.

Spec A delivers a **fully working OmniVoice engine with voice cloning and zero new UI** — it drops into the existing per-speaker reference-voice flow exactly like Chatterbox. Voice design, auto voice, and the per-speaker mode toggle are deferred to Spec B (they introduce new UI/validation). The worker built here implements all three generate modes from day one, so Spec B is purely frontend + request plumbing.

## Hard constraint that drives the architecture

OmniVoice (PyPI `omnivoice`, latest 0.1.5) requires `transformers>=5.3.0` and `torch>=2.4` (its docs install `torch==2.8.0+cu128`). This is incompatible with both existing pinned engines:

| Engine | transformers | torch |
|---|---|---|
| VibeVoice | `==4.51.3` | 2.6.0+cu124 (main venv) |
| Chatterbox | `==5.2.0` | 2.6.0+cu118 (its own venv) |
| **OmniVoice** | **`>=5.3.0`** | **2.8.0+cu128** |

OmniVoice therefore **cannot share any existing venv**. It must run **out-of-process in its own `backend/venv-omnivoice`**, driven by a proxy engine — the established Chatterbox isolation pattern. This is not a discretionary choice.

## Scope

**In scope (Spec A):**
- Isolated `backend/venv-omnivoice` + out-of-process `omnivoice_worker.py` + proxy `OmniVoiceEngine`.
- On-demand install via `studio.py install-omnivoice` with a `.omnivoice-ready` marker, surfaced through the existing in-UI install dialog (generalized).
- **Voice cloning only** at the proxy/UI level: a selected reference voice → cloned output. Reuses the existing per-speaker voice dropdown; no new UI.
- The worker implements clone/design/auto so Spec B needs no worker changes.
- Light generalization of the install infra (installer service, install API, install dialog) to serve both Chatterbox and OmniVoice.

**Out of scope (→ Spec B):**
- Voice design (`instruct`) and auto voice at the UI/request level.
- The per-speaker Clone/Design/Auto toggle and the "speaker with no voice" path.
- `num_step`/`duration` UI controls (worker accepts `num_step` with a sensible default; not surfaced).

**Out of scope (entirely):**
- The in-process model-download-progress UI (that is for in-process engines; OmniVoice downloads weights lazily inside the worker, so its `downloaded` flag stays `True`, exactly like Chatterbox).
- Non-verbal tags, pronunciation correction — these work through plain text input already; no special handling needed.

## OmniVoice inference API (reference)

```python
from omnivoice import OmniVoice
model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda:0")

# clone (ref_text optional — auto-transcribed if omitted)
audio = model.generate(text="…", ref_audio="ref.wav", ref_text="…")
# design
audio = model.generate(text="…", instruct="female, low pitch, british accent")
# auto
audio = model.generate(text="…")
# control knobs: num_step (diffusion steps), speed (>1 faster), duration (fixed sec)
# returns: list[np.ndarray], each shape (T,) at 24 kHz
```

## Components

### Backend

**1. `backend/omnivoice_worker.py`** *(new — runs inside `venv-omnivoice`; stdlib + omnivoice + numpy)*
- Mirrors `backend/chatterbox_worker.py`'s stdio JSON protocol and stdout-protocol safety (reserve real stdout for replies via `os.dup`, redirect fd 1 → stderr so model-load/tqdm noise can't corrupt the JSON stream; stderr drained by the parent).
- Ops: `{"op":"load","device":…}`, `{"op":"synth", …}`, `{"op":"shutdown"}`.
- `load`: `OmniVoice.from_pretrained(model_id, device_map=<device>)` where device ∈ {cuda:0, mps, xpu, cpu}; tolerate signature differences defensively (try/except like the chatterbox worker does for `t3_model`/`watermark`).
- `synth`: dispatch on `mode`:
  - `clone` → `generate(text, ref_audio=<path>, ref_text=<text or None>)`
  - `design` → `generate(text, instruct=<str>)`
  - `auto` → `generate(text)`
  - common kwargs when present: `num_step`, `speed`.
  - Result is a `list[np.ndarray]`; take the first element (single-utterance), write a 24 kHz mono int16 WAV to `out_wav`, reply `{ok, sample_rate:24000, duration_sec, inference_ms}`.
- All human-readable logging → stderr.

**2. `backend/core/engines/omnivoice_engine.py`** *(new — proxy in the main venv)*
- `OmniVoiceEngine(Engine)`: `name="omnivoice"`, `display_name="OmniVoice"`, description noting 600+ languages / cloning / isolated env / ~0.6 B.
- Copies the Chatterbox proxy mechanics (spawn worker python from `venv-omnivoice`, `_exchange` with non-JSON-line tolerance, stderr drain thread, `_kill`).
- Capabilities: `sample_rate()=24000`, `max_speakers()=1`, `supports_voice_cloning()=True`, `supports_streaming()=False`, `default_cfg_scale()=None` (OmniVoice has no CFG).
- `installed()` → `.omnivoice-ready` marker in `venv-omnivoice` (mirrors Chatterbox's marker logic). `downloaded()` inherits the base `True`.
- `synthesize(req)`: **Spec A** builds a `synth` message with `mode="clone"` when `req.reference_audio` is set (passing `ref_audio`, and `ref_text=None`), and `speed=req.speed`. If no `reference_audio`, raise a clear error ("OmniVoice (Spec A) requires a reference voice; auto/design arrive in Spec B"). Reuses `EngineSynthRequest`/`EngineResult` unchanged — **no new request fields in Spec A**.

**3. `backend/requirements-omnivoice.txt`** *(new)* — `omnivoice` only (torch is installed separately with the correct CUDA wheel by the installer, exactly as `requirements-chatterbox.txt` keeps torch out).

**4. `studio.py`** *(modify)*
- `omnivoice_venv_python(repo_root)` — `venv-omnivoice/{Scripts|bin}/python[.exe]`.
- `omnivoice_ready_marker(repo_root)` — `venv-omnivoice/.omnivoice-ready`.
- `_omnivoice_torch_tag(detected_tag)` — OmniVoice needs torch 2.8.x. Map the detected CUDA tag to an available 2.8 wheel: `cu128` for modern drivers (CUDA ≥ 12.8, incl. 13.x), `cu126` for 12.6–12.7, else `None` (CPU). (cu118/cu121/cu124 drivers that report < 12.6 fall back to CPU — torch 2.8 has no cu124 build.)
- `_ensure_omnivoice_env()` — mirrors `_ensure_chatterbox_env()`: clear marker; create `venv-omnivoice`; upgrade pip; `pip install -r requirements-omnivoice.txt` (with the same `--retries/--timeout` + `--progress-bar raw`); then **force-reinstall** `torch==2.8.* torchaudio==2.8.*` from the `_omnivoice_torch_tag` index; write `.omnivoice-ready` on success.
- `install-omnivoice` subcommand dispatching to `_ensure_omnivoice_env()` (return 0/1), parallel to `install-chatterbox`.

**5. `tools/envdetect.py`** *(modify)* — extend `CUDA_TAG_TO_INDEX` with `cu126` and `cu128` PyTorch index URLs (used only by the OmniVoice torch tag; the existing `cuda_version_to_tag` for the main/Chatterbox venvs is unchanged).

**6. Installer generalization** *(modify `backend/services/chatterbox_install.py` → generic)*
- Rename the class to a generic `EngineEnvInstaller` that takes the `studio.py` subcommand (e.g. `install-chatterbox`, `install-omnivoice`); the state machine, log handling, and `_format_progress` are already engine-agnostic. Keep a thin `ChatterboxInstaller` alias (or construct `EngineEnvInstaller("install-chatterbox")`) so existing imports/tests keep working.
- `app.py` — replace the single `chatterbox_installer` with an installer **registry**: `app.state.engine_installers = {"chatterbox": EngineEnvInstaller("install-chatterbox"), "omnivoice": EngineEnvInstaller("install-omnivoice")}`.
- `api/deps.py` — `get_engine_installer(name)` resolves from the registry (keep `get_chatterbox_installer` working, or update its one caller).

**7. `backend/api/engines.py`** *(modify)* — `_INSTALLABLE = {"chatterbox", "omnivoice"}`; `GET`/`POST /{name}/install` 400 unless `name in _INSTALLABLE`, and look the installer up by `name` from the registry instead of the hard-coded Chatterbox one.

**8. `backend/core/engine_manager.py` + `backend/config.py`** *(modify)* — register `OmniVoiceEngine` in the engine dict (its position drives selector order — place after Chatterbox); add `config.py` defaults: `omnivoice_model_id="k2-fsa/OmniVoice"`, `omnivoice_num_step` (e.g. 32), device from the global `--device`.

### Frontend

**9. Generalize the install dialog** *(modify)* — `InstallChatterboxDialog.tsx` → `InstallEngineDialog.tsx` taking `engineName` + `displayName`; copy text becomes engine-generic. `lib/api.ts`: `startChatterboxInstall`/`getChatterboxInstallStatus` → `startEngineInstall(name)`/`getEngineInstallStatus(name)` hitting `/api/engines/{name}/install`. `App.tsx`: the existing `onInstall(name)` opens `InstallEngineDialog` for that `name` (currently it ignores the name and hard-opens Chatterbox). The `EngineSelector` already renders **Install** whenever `installed===false`, so OmniVoice gets the button automatically once registered.

**10. `lib/engineHints.ts`** *(modify)* — for `omnivoice`, hide the CFG slider (no CFG parameter); `speed` is retained and forwarded to the worker's `generate(speed=…)`.

## Data flow

1. Engine list now includes OmniVoice with `installed:false` on a fresh machine → selector shows **Install OmniVoice**.
2. Install → `InstallEngineDialog` POSTs `/api/engines/omnivoice/install` → `EngineEnvInstaller` runs `studio.py install-omnivoice` (venv + cu128 torch + omnivoice), streaming the log; on success the `.omnivoice-ready` marker flips `installed:true`.
3. Switch → load: the proxy spawns the worker; first `load` lazily downloads the ~0.6 B weights into the shared HF cache (`backend/models/`).
4. A segment whose speaker has a selected reference voice → `synthesize` sends `mode="clone"` → worker clones → 24 kHz WAV → existing cache/concat/playback path.

## Error handling

- Worker crash / bad load → the proxy surfaces the drained stderr tail (existing Chatterbox mechanism).
- Install failure → dialog shows the log + **Retry** (existing mechanism); marker not written, so the engine stays `installed:false`.
- Driver too old for cu128/cu126 → `_omnivoice_torch_tag` returns `None`; installer puts CPU torch in the venv and logs a clear "GPU build unavailable for your driver; using CPU (slow)" note. (OmniVoice still runs on CPU; RTF just drops.)
- No reference voice in Spec A → proxy raises a clear `BackendError` explaining auto/design come in Spec B (until B lands).
- Dependency conflicts: impossible by construction (separate venv).

## Testing

- **`backend/tests/test_omnivoice_proxy.py`** *(new)* — mirror `test_chatterbox_proxy.py`: drive the proxy against a tiny fake worker script (stdin/stdout JSON) to verify spawn, `_exchange`, `installed()` marker gating, and that `synthesize` emits `mode="clone"` with `ref_audio`/`speed` when `reference_audio` is set and raises without it. No real model/venv.
- **Installer generalization tests** — extend/clone `test_chatterbox_install.py`: `EngineEnvInstaller("install-omnivoice")` with an injected fake runner (state machine, log accumulation, coalescing); the install API returns 400 for non-installable names and resolves chatterbox **and** omnivoice from the registry.
- **`studio.py` helper tests** — `_omnivoice_torch_tag` mapping (cu128/cu126/cpu/None), `omnivoice_venv_python` path shape, `install-omnivoice` subcommand dispatch (monkeypatched `_ensure_omnivoice_env`), mirroring the existing Chatterbox helper tests.
- **`tools/envdetect.py`** — `cu126`/`cu128` entries resolve to the right index URLs.
- **Frontend** — `npm run typecheck` + `npm run build` green with the generalized `InstallEngineDialog`/api and OmniVoice in the selector.

## Open notes / risks

- **`device_map` vs `device`:** OmniVoice's `from_pretrained` takes `device_map="cuda:0"`. The worker normalizes the engine's device request (`cuda`→`cuda:0`, plus `mps`/`xpu`/`cpu`) and tolerates signature variance defensively.
- **torch 2.8 wheel availability:** confirm cu128/cu126 build tags at implementation time (`download.pytorch.org/whl/cu128`); adjust `_omnivoice_torch_tag` fallbacks if a tag is missing. CPU fallback always works.
- **Install size:** OmniVoice adds a third multi-GB venv (cu128 torch) + ~0.6 B weights. Acceptable — it's opt-in behind the Install button, same model as Chatterbox.
- **`ref_text`:** omitted in Spec A (OmniVoice auto-transcribes the reference). A future enhancement could pass the reference voice's known transcript if available.
