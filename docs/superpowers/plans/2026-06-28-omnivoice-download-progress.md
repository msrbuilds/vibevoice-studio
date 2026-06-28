# OmniVoice Download Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give OmniVoice's ~1.6 GB weight download a real progress bar by opting it into the existing in-process `ModelDownloader` + `DownloadModelDialog` system (no new infra).

**Architecture:** OmniVoice loads in an isolated worker but reads from the shared HF cache (`backend/models/`). So the main process pre-downloads `k2-fsa/OmniVoice` with the existing `ModelDownloader` (background `snapshot_download` + tqdm byte callback), and the worker finds it cached. We just register OmniVoice as downloadable: add it to the catalog + two allow-lists, give the engine a real `downloaded()` probe, and add a frontend size label. The selector's Install→Download→Switch precedence and the progress dialog are already engine-agnostic.

**Tech Stack:** Python / FastAPI / huggingface_hub (backend, tests via `backend/venv`); React + TypeScript + Vite (frontend, verified by typecheck + build).

**Reference spec:** `docs/superpowers/specs/2026-06-28-omnivoice-download-progress-design.md`

**Conventions:** Backend tests: `cd backend && ./venv/Scripts/python.exe -m pytest …`. Frontend: from `frontend/`.

---

## File Structure

- **Modify** `backend/scripts/download_models.py` — `MODEL_CATALOG` += `omnivoice`.
- **Modify** `backend/services/model_download.py` — `DOWNLOADABLE` += `omnivoice`.
- **Modify** `backend/api/engines.py` — `_DOWNLOADABLE` += `omnivoice`.
- **Modify** `backend/core/engines/omnivoice_engine.py` — override `downloaded()`.
- **Modify** `backend/tests/test_setup_helpers.py` — update the catalog-set assertion.
- **Modify** `backend/tests/test_model_download.py` — omnivoice downloadable + endpoint tests.
- **Modify** `backend/tests/test_omnivoice_proxy.py` — `downloaded()` probe test.
- **Modify** `frontend/src/components/DownloadModelDialog.tsx` — `MODEL_SIZES` += `omnivoice`.

---

## Task 1: Register OmniVoice as a downloadable engine (catalog + allow-lists)

**Files:**
- Modify: `backend/scripts/download_models.py`
- Modify: `backend/services/model_download.py`
- Modify: `backend/api/engines.py`
- Modify: `backend/tests/test_setup_helpers.py`
- Test: `backend/tests/test_model_download.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_model_download.py`:

```python
def test_start_accepts_omnivoice():
    captured = {}
    def runner(repo_id, prog):
        captured["repo_id"] = repo_id
    dl = ModelDownloader(runner=runner)
    dl.start("omnivoice")
    _wait(dl)
    s = dl.status()
    assert s["engine"] == "omnivoice"
    assert s["state"] == "done"
    assert captured["repo_id"] == "k2-fsa/OmniVoice"


def test_download_endpoint_accepts_omnivoice():
    def runner(repo_id, prog):
        prog.set_total(10)
        prog.add_bytes(10, "f")
    dl = ModelDownloader(runner=runner)
    client = _make_client(dl)
    assert client.get("/api/engines/omnivoice/download").json()["state"] == "idle"
    assert client.post("/api/engines/omnivoice/download").status_code == 200
    _wait(dl)
    assert client.get("/api/engines/omnivoice/download").json()["state"] == "done"
```

(`_wait`, `_make_client`, `ModelDownloader` are already defined earlier in this test file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_model_download.py -k omnivoice -v`
Expected: FAIL — `ValueError: omnivoice is not downloadable` (from `ModelDownloader.start`) and a 400 from the endpoint.

- [ ] **Step 3: Implement the three allow-list changes**

In `backend/scripts/download_models.py`, add an `omnivoice` entry to `MODEL_CATALOG` (after the `chatterbox` entry, before the closing `}`):

```python
    "chatterbox": {
        "repo_id": "ResembleAI/chatterbox",
        "size": "~500 MB",
        "label": "Chatterbox V3",
    },
    "omnivoice": {
        "repo_id": "k2-fsa/OmniVoice",
        "size": "~1.6 GB",
        "label": "OmniVoice",
    },
```

In `backend/services/model_download.py` (line 21), add `"omnivoice"`:

```python
DOWNLOADABLE: frozenset[str] = frozenset({"vibevoice", "kokoro", "omnivoice"})
```

In `backend/api/engines.py` (line 58), add `"omnivoice"`:

```python
_DOWNLOADABLE = {"vibevoice", "kokoro", "omnivoice"}
```

- [ ] **Step 4: Update the existing catalog-set assertion**

In `backend/tests/test_setup_helpers.py`, the test `test_catalog_has_expected_engines` currently is:

```python
def test_catalog_has_expected_engines():
    assert set(dm.MODEL_CATALOG) == {"vibevoice", "kokoro", "chatterbox"}
    assert dm.MODEL_CATALOG["kokoro"]["repo_id"] == "hexgrad/Kokoro-82M"
```

Replace it with:

```python
def test_catalog_has_expected_engines():
    assert set(dm.MODEL_CATALOG) == {"vibevoice", "kokoro", "chatterbox", "omnivoice"}
    assert dm.MODEL_CATALOG["kokoro"]["repo_id"] == "hexgrad/Kokoro-82M"
    assert dm.MODEL_CATALOG["omnivoice"]["repo_id"] == "k2-fsa/OmniVoice"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_model_download.py -k omnivoice tests/test_setup_helpers.py::test_catalog_has_expected_engines -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite (no regressions)**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS, 0 failures (the catalog-set test was the only one pinned to the old set).

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/download_models.py backend/services/model_download.py backend/api/engines.py backend/tests/test_setup_helpers.py backend/tests/test_model_download.py
git commit -m "feat: register OmniVoice as a downloadable engine"
```

---

## Task 2: `OmniVoiceEngine.downloaded()` cache probe

**Files:**
- Modify: `backend/core/engines/omnivoice_engine.py`
- Test: `backend/tests/test_omnivoice_proxy.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_omnivoice_proxy.py`:

```python
def test_downloaded_probes_model_id(monkeypatch):
    from backend.core import model_cache

    seen = {}

    def fake_model_downloaded(repo_id):
        seen["repo_id"] = repo_id
        return True

    monkeypatch.setattr(model_cache, "model_downloaded", fake_model_downloaded)
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    assert eng.downloaded() is True
    assert seen["repo_id"] == "k2-fsa/OmniVoice"
    assert eng.info()["downloaded"] is True


def test_downloaded_false_when_not_cached(monkeypatch):
    from backend.core import model_cache

    monkeypatch.setattr(model_cache, "model_downloaded", lambda repo_id: False)
    eng = OmniVoiceEngine(worker_python=Path("x"), worker_script=Path("y"))
    assert eng.downloaded() is False
    assert eng.info()["downloaded"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py::test_downloaded_probes_model_id -v`
Expected: FAIL — `eng.downloaded()` returns the inherited base `True` without calling `model_downloaded`, so `seen` stays empty → `KeyError: 'repo_id'`.

- [ ] **Step 3: Implement the override**

In `backend/core/engines/omnivoice_engine.py`, add a `downloaded()` method directly after the existing `_ready_marker()` method (around line 126), mirroring the VibeVoice/Kokoro pattern. The lazy import keeps the HF cache-config ordering intact:

```python
    def downloaded(self) -> bool:
        # OmniVoice weights live in the shared HF cache (backend/models/), which
        # both the main process and the isolated worker read. Probe it so the UI
        # can offer a Download (with progress) before the first worker load.
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_omnivoice_proxy.py -v`
Expected: PASS (all, including the two new `downloaded` tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/engines/omnivoice_engine.py backend/tests/test_omnivoice_proxy.py
git commit -m "feat: OmniVoiceEngine.downloaded() probes the shared HF cache"
```

---

## Task 3: Frontend size label

**Files:**
- Modify: `frontend/src/components/DownloadModelDialog.tsx`

- [ ] **Step 1: Add the OmniVoice size**

In `frontend/src/components/DownloadModelDialog.tsx`, the `MODEL_SIZES` constant (around line 15) currently is:

```typescript
const MODEL_SIZES: Record<string, string> = {
  vibevoice: "~5.4 GB",
  kokoro: "~350 MB",
};
```

Add the `omnivoice` line:

```typescript
const MODEL_SIZES: Record<string, string> = {
  vibevoice: "~5.4 GB",
  kokoro: "~350 MB",
  omnivoice: "~1.6 GB",
};
```

- [ ] **Step 2: Typecheck + build**

Run: `cd frontend && npm run typecheck`
Expected: PASS.
Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DownloadModelDialog.tsx
git commit -m "feat: OmniVoice size label in the download dialog"
```

---

## Final verification

- [ ] **Backend suite green:** `cd backend && ./venv/Scripts/python.exe -m pytest tests/ -q` → all pass.
- [ ] **Frontend green:** `cd frontend && npm run typecheck && npm run build` → both pass.
- [ ] **Manual smoke (needs a machine without OmniVoice weights cached):** install the OmniVoice venv, then the engine menu shows **Download OmniVoice**; clicking it opens the progress dialog (confirm "~1.6 GB" → bar with %/speed/ETA), and on completion it switches + loads OmniVoice. With the weights already cached, the button reads **Switch to OmniVoice** directly.
- [ ] **Update `CLAUDE.md`:** in the model-download bullet, note OmniVoice now uses the in-process download-progress flow for its main repo (with the ~11 MB Qwen tokenizer slice still streaming on first load), so it is no longer "lazy in-worker only" like Chatterbox.

---

## Self-Review (completed by plan author)

**Spec coverage:**
- `MODEL_CATALOG` += omnivoice → Task 1. ✓
- `DOWNLOADABLE` (service) + `_DOWNLOADABLE` (api) += omnivoice → Task 1. ✓
- `OmniVoiceEngine.downloaded()` probe → Task 2. ✓
- Frontend `MODEL_SIZES` += omnivoice → Task 3. ✓
- Install→Download→Switch flow: no code change (existing `EngineSelector` precedence + engine-agnostic dialog) — confirmed in spec; nothing to implement. ✓
- Tests: catalog, downloadable + endpoint (Task 1); downloaded() probe (Task 2); frontend typecheck/build (Task 3). ✓
- Existing `test_catalog_has_expected_engines` updated for the new set → Task 1 Step 4. ✓

**Placeholder scan:** none — every step has full code/commands.

**Type/name consistency:** `repo_id "k2-fsa/OmniVoice"` is identical across `MODEL_CATALOG` (Task 1), the `downloaded()` probe via `self._model_id` (Task 2, where the engine's constructor default `model_id="k2-fsa/OmniVoice"` sets `self._model_id`), and the `test_start_accepts_omnivoice` assertion. `"omnivoice"` key consistent across catalog/`DOWNLOADABLE`/`_DOWNLOADABLE`/`MODEL_SIZES`. The `model_downloaded` lazy-import + monkeypatch target (`backend.core.model_cache.model_downloaded`) matches the VibeVoice/Kokoro override pattern.
