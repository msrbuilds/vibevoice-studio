# Voice Studio Setup & Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce install + run of Voice Studio by MSR to two cross-platform commands, with an interactive model picker and a single launcher that runs both backend and frontend.

**Architecture:** A stdlib-only `studio.py` dispatcher at the repo root bootstraps `backend/venv`, then delegates heavy work to the venv's Python. Pure helpers (CUDA detection, model catalog, static-mount guard) are unit-tested; subprocess orchestration is thin and manually verified. A new optional static mount lets FastAPI serve the built UI + API on one port for `--prod`.

**Tech Stack:** Python 3.10+ standard library (`argparse`, `subprocess`, `venv`, `shutil`, `platform`), `huggingface_hub` (model download, in-venv), FastAPI + Starlette `StaticFiles`, pytest.

---

## Context for the implementer

- **Repo root** contains `backend/` (Python package, run as `python -m backend.cli`) and `frontend/` (Vite + React).
- The HF cache is pinned to `backend/models/` via `backend/core/hf_paths.py::configure_hf_cache(models_dir)`. Always call it **before** importing `huggingface_hub`/`transformers`.
- Existing tests (`backend/tests/test_smoke.py`) add the **repo root** to `sys.path` so `import backend.*` works:
  ```python
  BACKEND = Path(__file__).resolve().parent.parent
  sys.path.insert(0, str(BACKEND.parent))   # repo root
  ```
  Reuse this so both `backend.*` and `tools.*` import cleanly regardless of cwd.
- Run a single test with: `cd backend && python -m pytest tests/test_setup_helpers.py::<name> -v`
- `studio.py` and `tools/envdetect.py` MUST import only the standard library — they run on a bare system Python before the venv exists.

## File Structure

| Path | Responsibility |
|------|----------------|
| `tools/__init__.py` | New — marks `tools/` a package (empty). |
| `tools/envdetect.py` | New — stdlib CUDA detection + torch-index mapping (pure). |
| `backend/scripts/download_models.py` | New — model catalog, selection parsing, snapshot download. |
| `backend/app.py` | Modify — add `_mount_frontend()` + call it after routers. |
| `backend/cli.py` | Modify — rebrand `prog`/description strings. |
| `studio.py` | New — stdlib dispatcher: `setup` / `start` / `models` + pure helpers. |
| `backend/tests/test_setup_helpers.py` | New — unit tests for the pure helpers above. |
| `README.md`, `CLAUDE.md` | Modify — new two-command flow + branding. |

---

## Task 1: CUDA detection helpers (`tools/envdetect.py`)

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/envdetect.py`
- Test: `backend/tests/test_setup_helpers.py`

- [ ] **Step 1: Create the package marker**

Create `tools/__init__.py` (empty file):

```python
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_setup_helpers.py`:

```python
"""Unit tests for the Voice Studio setup/launch pure helpers."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools import envdetect  # noqa: E402

_SAMPLE_SMI = """
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 552.22       Driver Version: 552.22       CUDA Version: 12.4      |
|-------------------------------+----------------------+----------------------+
"""


def test_parse_cuda_version_found():
    assert envdetect.parse_nvidia_smi_cuda_version(_SAMPLE_SMI) == "12.4"


def test_parse_cuda_version_missing():
    assert envdetect.parse_nvidia_smi_cuda_version("no cuda here") is None


def test_cuda_version_to_tag():
    assert envdetect.cuda_version_to_tag("12.4") == "cu124"
    assert envdetect.cuda_version_to_tag("12.6") == "cu124"
    assert envdetect.cuda_version_to_tag("12.1") == "cu121"
    assert envdetect.cuda_version_to_tag("12.0") == "cu121"
    assert envdetect.cuda_version_to_tag("11.8") == "cu118"
    assert envdetect.cuda_version_to_tag("10.2") is None
    assert envdetect.cuda_version_to_tag(None) is None


def test_torch_index_url():
    assert envdetect.torch_index_url("cu124") == "https://download.pytorch.org/whl/cu124"
    assert envdetect.torch_index_url("cu118") == "https://download.pytorch.org/whl/cu118"
    assert envdetect.torch_index_url(None) is None
    assert envdetect.torch_index_url("cpu") is None
    assert envdetect.torch_index_url("mps") is None


def test_detect_cuda_tag_with_injected_runner():
    assert envdetect.detect_cuda_tag(runner=lambda: _SAMPLE_SMI) == "cu124"
    assert envdetect.detect_cuda_tag(runner=lambda: None) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_setup_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools'` or `AttributeError`.

- [ ] **Step 4: Implement `tools/envdetect.py`**

```python
"""Stdlib-only environment detection for the Voice Studio launcher.

Imported by ``studio.py`` BEFORE any venv exists, so it must not import
any third-party package.
"""

from __future__ import annotations

import re
import shutil
import subprocess

CUDA_TAG_TO_INDEX: dict[str, str] = {
    "cu124": "https://download.pytorch.org/whl/cu124",
    "cu121": "https://download.pytorch.org/whl/cu121",
    "cu118": "https://download.pytorch.org/whl/cu118",
}


def parse_nvidia_smi_cuda_version(text: str) -> str | None:
    """Extract the ``CUDA Version: X.Y`` field from nvidia-smi output."""
    m = re.search(r"CUDA Version:\s*([0-9]+\.[0-9]+)", text)
    return m.group(1) if m else None


def cuda_version_to_tag(version: str | None) -> str | None:
    """Map a CUDA runtime version (e.g. '12.4') to a PyTorch wheel tag."""
    if not version:
        return None
    try:
        major, minor = (int(p) for p in version.split(".")[:2])
    except ValueError:
        return None
    if major >= 12:
        return "cu124" if minor >= 4 else "cu121"
    if major == 11:
        return "cu118"
    return None


def torch_index_url(tag: str | None) -> str | None:
    """Map a wheel tag to a ``--index-url``; None means the default wheel."""
    if tag in (None, "cpu", "mps"):
        return None
    return CUDA_TAG_TO_INDEX.get(tag)


def _run_nvidia_smi() -> str | None:
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def detect_cuda_tag(runner=None) -> str | None:
    """Detect the best CUDA wheel tag. ``runner`` is injectable for tests."""
    run = runner or _run_nvidia_smi
    text = run()
    if text is None:
        return None
    return cuda_version_to_tag(parse_nvidia_smi_cuda_version(text))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_setup_helpers.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add tools/__init__.py tools/envdetect.py backend/tests/test_setup_helpers.py
git commit -m "feat: add CUDA detection + torch-index helpers for launcher"
```

---

## Task 2: Model catalog + downloader (`backend/scripts/download_models.py`)

**Files:**
- Create: `backend/scripts/download_models.py`
- Test: `backend/tests/test_setup_helpers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_setup_helpers.py`:

```python
from backend.scripts import download_models as dm  # noqa: E402


def test_parse_model_selection_basic():
    assert dm.parse_model_selection("kokoro,chatterbox") == ["kokoro", "chatterbox"]


def test_parse_model_selection_dedupes_and_lowercases():
    assert dm.parse_model_selection("Kokoro, kokoro , VIBEVOICE") == ["kokoro", "vibevoice"]


def test_parse_model_selection_rejects_unknown():
    import pytest
    with pytest.raises(ValueError):
        dm.parse_model_selection("kokoro,bogus")


def test_catalog_has_expected_engines():
    assert set(dm.MODEL_CATALOG) == {"vibevoice", "kokoro", "chatterbox"}
    assert dm.MODEL_CATALOG["kokoro"]["repo_id"] == "hexgrad/Kokoro-82M"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_setup_helpers.py -k model -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.scripts.download_models'`.

- [ ] **Step 3: Implement `backend/scripts/download_models.py`**

```python
"""Voice Studio model downloader.

Pre-fetches selected TTS model weights into the project-local HF cache
(``backend/models/``). Run inside the venv:

    python -m backend.scripts.download_models --models kokoro,chatterbox
"""

from __future__ import annotations

import argparse
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent  # backend/

# Ordered: drives display order in the picker.
MODEL_CATALOG: dict[str, dict[str, str]] = {
    "vibevoice": {
        "repo_id": "vibevoice/VibeVoice-1.5B",
        "size": "~5.4 GB",
        "label": "VibeVoice-1.5B",
    },
    "kokoro": {
        "repo_id": "hexgrad/Kokoro-82M",
        "size": "~350 MB",
        "label": "Kokoro-82M",
    },
    "chatterbox": {
        "repo_id": "ResembleAI/chatterbox",
        "size": "~500 MB",
        "label": "Chatterbox V3",
    },
}


def parse_model_selection(value: str) -> list[str]:
    """Parse a comma-separated list of engine keys; validate + de-dupe."""
    keys = [k.strip().lower() for k in value.split(",") if k.strip()]
    unknown = [k for k in keys if k not in MODEL_CATALOG]
    if unknown:
        raise ValueError(
            f"unknown model(s): {', '.join(unknown)}. "
            f"Valid keys: {', '.join(MODEL_CATALOG)}"
        )
    deduped: dict[str, None] = {}
    for k in keys:
        deduped.setdefault(k, None)
    return list(deduped)


def download_models(keys: list[str], models_dir: Path | str | None = None) -> None:
    """Download each selected engine's weights into the HF cache."""
    from backend.core.hf_paths import configure_hf_cache

    cache_dir = Path(models_dir) if models_dir else _BACKEND_ROOT / "models"
    configure_hf_cache(cache_dir)

    from huggingface_hub import snapshot_download

    for key in keys:
        spec = MODEL_CATALOG[key]
        print(f"[models] Downloading {spec['label']} ({spec['size']}) …", flush=True)
        snapshot_download(repo_id=spec["repo_id"])
        print(f"[models] {spec['label']} ready.", flush=True)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="download_models",
        description="Voice Studio by MSR — model downloader",
    )
    p.add_argument(
        "--models",
        required=True,
        help="comma-separated engine keys: " + ", ".join(MODEL_CATALOG),
    )
    p.add_argument("--models-dir", default=None, help="HF cache dir (default: backend/models)")
    args = p.parse_args(argv)
    download_models(parse_model_selection(args.models), args.models_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_setup_helpers.py -k model -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/download_models.py backend/tests/test_setup_helpers.py
git commit -m "feat: add model catalog + downloader for setup picker"
```

---

## Task 3: Optional static mount for `--prod` (`backend/app.py`)

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_setup_helpers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_setup_helpers.py`:

```python
def test_mount_frontend_serves_index_when_dist_present(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app import _mount_frontend

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>voice studio</html>", encoding="utf-8")

    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    _mount_frontend(app, dist)
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}
    root = client.get("/")
    assert root.status_code == 200
    assert "voice studio" in root.text


def test_mount_frontend_noop_when_dist_absent(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app import _mount_frontend

    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    _mount_frontend(app, tmp_path / "missing-dist")
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_setup_helpers.py -k mount -v`
Expected: FAIL — `ImportError: cannot import name '_mount_frontend' from 'backend.app'`.

- [ ] **Step 3: Add `_mount_frontend` to `backend/app.py`**

Add this function near the top of `backend/app.py`, after `_configure_logging` (around line 52):

```python
def _mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serve the built frontend at / when a Vite build exists.

    No-op in dev mode (no dist). Must be called AFTER the API routers so
    the catch-all static mount never shadows /api/*.
    """
    if not (dist_dir / "index.html").is_file():
        return
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
```

Note: `Path` is already imported at the top of `app.py` as `from pathlib import Path as _Path` — use the public name by adding a plain import. At the top of `app.py`, in the stdlib import block (after `import logging`), add:

```python
from pathlib import Path
```

- [ ] **Step 4: Call it after the routers in `create_app`**

In `backend/app.py`, immediately after the last `app.include_router(...)` line (`app.include_router(stream_router)`, around line 166) and before the exception handlers, add:

```python
    # ---- static frontend (prod mode only; no-op if frontend/dist is absent)
    _frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    _mount_frontend(app, _frontend_dist)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_setup_helpers.py -k mount -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full smoke suite to confirm no regression**

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS (existing smoke tests + new helper tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/tests/test_setup_helpers.py
git commit -m "feat: optionally serve built frontend for single-port prod mode"
```

---

## Task 4: The `studio.py` dispatcher

**Files:**
- Create: `studio.py`
- Test: `backend/tests/test_setup_helpers.py` (append — pure helpers only)

- [ ] **Step 1: Write the failing tests for the pure helpers**

Append to `backend/tests/test_setup_helpers.py`:

```python
import studio  # noqa: E402


def test_venv_python_path_shape():
    repo = Path("/repo")
    p = studio.venv_python(repo)
    # Either Scripts/python.exe (Windows) or bin/python (POSIX)
    assert p.name in ("python.exe", "python")
    assert "venv" in p.parts


def test_build_backend_cmd_forwards_passthrough():
    cmd = studio.build_backend_cmd(Path("/repo/backend/venv/bin/python"),
                                   ["--device", "cuda", "--port", "9000"])
    assert cmd[:3] == ["/repo/backend/venv/bin/python", "-m", "backend.cli"]
    assert cmd[-4:] == ["--device", "cuda", "--port", "9000"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_setup_helpers.py -k "venv_python or build_backend" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'studio'`.

- [ ] **Step 3: Implement `studio.py`**

Create `studio.py` at the repo root:

```python
#!/usr/bin/env python3
"""Voice Studio by MSR — one-stop setup & launch dispatcher.

Stdlib only: this runs on a bare system Python before the venv exists.

    python studio.py setup            # one-time install + model picker
    python studio.py start            # run the app (mode auto-selected)
    python studio.py start --dev      # force dev (two processes, hot reload)
    python studio.py start --prod     # force prod (one server, one port)
    python studio.py models           # re-open the model picker
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
VENV_DIR = BACKEND_DIR / "venv"

sys.path.insert(0, str(REPO_ROOT))
from tools import envdetect  # noqa: E402

IS_WINDOWS = os.name == "nt"
BANNER = "=== Voice Studio by MSR ==="


# --------------------------------------------------------------- helpers --
def venv_python(repo_root: Path) -> Path:
    """Path to the venv's Python interpreter for the current OS."""
    venv = repo_root / "backend" / "venv"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def build_backend_cmd(py: Path, passthrough: list[str]) -> list[str]:
    """Command to launch the backend server via the venv Python."""
    return [str(py), "-m", "backend.cli", *passthrough]


def _which(name: str) -> str | None:
    return shutil.which(name)


def _npm() -> str | None:
    # On Windows npm is npm.cmd; shutil.which resolves it.
    return shutil.which("npm")


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"  $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None).returncode


def _confirm(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    ans = input(prompt + suffix).strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


# ----------------------------------------------------------------- setup --
def cmd_setup(_args: argparse.Namespace) -> int:
    print(BANNER)
    print("Setup — installing the backend, frontend, and (optionally) models.\n")

    if sys.version_info < (3, 10):
        print("ERROR: Python 3.10+ is required. You have "
              f"{sys.version_info.major}.{sys.version_info.minor}.")
        return 1

    # 1. venv
    py = venv_python(REPO_ROOT)
    if not py.is_file():
        print("[1/5] Creating virtual environment at backend/venv …")
        if _run([sys.executable, "-m", "venv", str(VENV_DIR)]) != 0:
            print("ERROR: failed to create venv.")
            return 1
    else:
        print("[1/5] venv already exists — reusing it.")

    # 2. PyTorch (auto-detect + confirm)
    print("\n[2/5] Selecting a PyTorch build …")
    tag = envdetect.detect_cuda_tag()
    index = envdetect.torch_index_url(tag)
    if tag:
        print(f"  Detected NVIDIA GPU → CUDA wheel '{tag}'.")
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        print("  Apple Silicon detected → default (MPS-capable) wheel.")
    else:
        print("  No NVIDIA GPU detected → CPU-only wheel (slower).")
    if not _confirm("  Install this PyTorch build?"):
        print("  Choose a build:  1) CUDA 12.4  2) CUDA 12.1  3) CUDA 11.8  4) CPU/MPS")
        choice = input("  > ").strip()
        index = {
            "1": envdetect.torch_index_url("cu124"),
            "2": envdetect.torch_index_url("cu121"),
            "3": envdetect.torch_index_url("cu118"),
            "4": None,
        }.get(choice, index)
    pip_torch = [str(py), "-m", "pip", "install", "torch", "torchaudio"]
    if index:
        pip_torch += ["--index-url", index]
    if _run(pip_torch) != 0:
        print("ERROR: torch install failed. Re-run setup or install torch manually.")
        return 1

    # 3. backend requirements
    print("\n[3/5] Installing backend dependencies …")
    if _run([str(py), "-m", "pip", "install", "-r",
             str(BACKEND_DIR / "requirements.txt")]) != 0:
        print("ERROR: backend dependency install failed.")
        return 1

    # 4. system deps + frontend
    print("\n[4/5] Checking system dependencies …")
    _check_system_deps()
    if _npm():
        print("  Installing frontend dependencies (npm install) …")
        _run([_npm(), "install"], cwd=FRONTEND_DIR)
    else:
        print("  WARNING: npm not found. Install Node.js 18+ "
              "(https://nodejs.org) then run: cd frontend && npm install")

    # 5. model picker
    print("\n[5/5] Model download")
    _interactive_model_picker(py)

    print("\nSetup complete. Start the app with:  python studio.py start")
    return 0


def _check_system_deps() -> None:
    mgr = (
        "winget install eSpeak-NG.eSpeak-NG" if IS_WINDOWS
        else "brew install espeak-ng" if platform.system() == "Darwin"
        else "sudo apt-get install espeak-ng"
    )
    ff = (
        "winget install Gyan.FFmpeg" if IS_WINDOWS
        else "brew install ffmpeg" if platform.system() == "Darwin"
        else "sudo apt-get install ffmpeg"
    )
    if _which("espeak-ng") is None:
        print(f"  NOTE: espeak-ng not found (needed by Kokoro). Install: {mgr}")
    if _which("ffmpeg") is None:
        print(f"  NOTE: ffmpeg not found (some audio I/O). Install: {ff}")


def _interactive_model_picker(py: Path) -> None:
    # Import the catalog via the venv is overkill; mirror keys here for the
    # prompt, and let download_models validate.
    catalog = [
        ("vibevoice", "VibeVoice-1.5B", "~5.4 GB"),
        ("kokoro", "Kokoro-82M", "~350 MB"),
        ("chatterbox", "Chatterbox V3", "~500 MB"),
    ]
    print("  Select models to download now (others download lazily on first use):")
    for i, (_key, label, size) in enumerate(catalog, 1):
        print(f"    {i}) {label:<16} {size}")
    print("  Enter numbers separated by commas (e.g. 2,3), or blank to skip.")
    raw = input("  > ").strip()
    if not raw:
        print("  Skipping model download.")
        return
    picked: list[str] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if tok.isdigit() and 1 <= int(tok) <= len(catalog):
            picked.append(catalog[int(tok) - 1][0])
    if not picked:
        print("  Nothing valid selected — skipping.")
        return
    _run([str(py), "-m", "backend.scripts.download_models",
          "--models", ",".join(picked)], cwd=REPO_ROOT)


# --------------------------------------------------------------- models --
def cmd_models(_args: argparse.Namespace) -> int:
    py = venv_python(REPO_ROOT)
    if not py.is_file():
        print("No venv found. Run:  python studio.py setup")
        return 1
    _interactive_model_picker(py)
    return 0


# ---------------------------------------------------------------- start --
def cmd_start(args: argparse.Namespace) -> int:
    print(BANNER)
    py = venv_python(REPO_ROOT)
    if not py.is_file():
        if _confirm("No venv found. Run setup now?"):
            rc = cmd_setup(args)
            if rc != 0:
                return rc
        else:
            return 1

    mode = _resolve_mode(args)
    if mode == "prod":
        return _start_prod(py, args.passthrough)
    return _start_dev(py, args.passthrough)


def _resolve_mode(args: argparse.Namespace) -> str:
    if args.prod:
        return "prod"
    if args.dev:
        return "dev"
    if _npm():
        return "dev"
    if (FRONTEND_DIR / "dist" / "index.html").is_file():
        return "prod"
    print("ERROR: npm not found and no frontend/dist build present.\n"
          "Install Node.js 18+ (then re-run), or build once with --prod.")
    sys.exit(1)


def _start_dev(py: Path, passthrough: list[str]) -> int:
    print("Mode: DEV (backend :8880 + Vite :5173, hot reload). Ctrl+C to stop.\n")
    procs: list[subprocess.Popen] = []
    popen_kwargs: dict = {}
    if IS_WINDOWS:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    backend = subprocess.Popen(
        build_backend_cmd(py, passthrough), cwd=str(REPO_ROOT), **popen_kwargs
    )
    procs.append(backend)
    if _npm():
        frontend = subprocess.Popen(
            [_npm(), "run", "dev"], cwd=str(FRONTEND_DIR), **popen_kwargs
        )
        procs.append(frontend)

    try:
        while True:
            for p in procs:
                rc = p.poll()
                if rc is not None:
                    print(f"\nA process exited (code {rc}); shutting the rest down.")
                    _terminate_all(procs)
                    return rc
            try:
                procs[0].wait(timeout=1)
            except subprocess.TimeoutExpired:
                continue
    except KeyboardInterrupt:
        print("\nStopping …")
        _terminate_all(procs)
        return 0


def _start_prod(py: Path, passthrough: list[str]) -> int:
    dist = FRONTEND_DIR / "dist" / "index.html"
    if not dist.is_file():
        if _npm() is None:
            print("ERROR: need to build the frontend but npm is not installed.")
            return 1
        print("Building frontend (npm run build) …")
        if _run([_npm(), "run", "build"], cwd=FRONTEND_DIR) != 0:
            print("ERROR: frontend build failed.")
            return 1
    print("Mode: PROD (single server on :8880). Ctrl+C to stop.\n")
    return subprocess.run(
        build_backend_cmd(py, passthrough), cwd=str(REPO_ROOT)
    ).returncode


def _terminate_all(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is not None:
            continue
        try:
            if IS_WINDOWS:
                p.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
    for p in procs:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()


# ------------------------------------------------------------------ main --
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="studio.py", description="Voice Studio by MSR — setup & launch"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="one-time install + model picker")

    p_start = sub.add_parser("start", help="run the app")
    p_start.add_argument("--dev", action="store_true", help="force dev mode")
    p_start.add_argument("--prod", action="store_true", help="force prod mode")
    p_start.add_argument(
        "passthrough", nargs=argparse.REMAINDER,
        help="flags forwarded to backend.cli (e.g. --device cuda --port 9000)",
    )

    sub.add_parser("models", help="re-open the model picker")

    args = parser.parse_args(argv)
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "models":
        return cmd_models(args)
    if args.command == "start":
        return cmd_start(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_setup_helpers.py -k "venv_python or build_backend" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Smoke-check the CLI parses without running the server**

Run: `python studio.py --help` and `python studio.py start --help`
Expected: help text prints, exit 0; no traceback.

- [ ] **Step 6: Commit**

```bash
git add studio.py backend/tests/test_setup_helpers.py
git commit -m "feat: add studio.py setup/start/models dispatcher"
```

---

## Task 5: Rebrand `backend/cli.py` strings

**Files:**
- Modify: `backend/cli.py:43-46`

- [ ] **Step 1: Update the argparse prog/description**

In `backend/cli.py`, change the `ArgumentParser` construction (around line 43):

```python
    p = argparse.ArgumentParser(
        prog="voice-studio",
        description="Voice Studio by MSR — local multi-engine TTS server",
    )
```

- [ ] **Step 2: Verify the CLI still starts parsing**

Run: `python -m backend.cli --help`
Expected: help header shows `voice-studio` and the new description; exit 0.

- [ ] **Step 3: Commit**

```bash
git add backend/cli.py
git commit -m "chore: rebrand backend CLI to Voice Studio by MSR"
```

---

## Task 6: Update docs (`README.md`, `CLAUDE.md`)

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a Quick Start to `README.md`**

Replace the top heading line `# VibeVoice Studio` with:

```markdown
# Voice Studio by MSR
```

Immediately after the intro paragraph/diagram, insert a new section before `## Features`:

```markdown
## Quick Start

Requires Python 3.10+ (and Node.js 18+ for the dev UI). From the repo root:

```bash
python studio.py setup     # creates the venv, installs deps, auto-picks a PyTorch/CUDA build,
                           # checks system deps, and lets you choose which models to download
python studio.py start     # launches backend + frontend together (Ctrl+C stops both)
```

- `python studio.py start --dev` — backend (:8880) + Vite dev server (:5173), hot reload.
- `python studio.py start --prod` — builds the UI and serves it + the API on a single port (:8880); no Node needed at runtime.
- `python studio.py models` — re-open the model picker anytime.
- Flags after `start` pass through to the server, e.g. `python studio.py start --dev --device cuda --port 9000`.

The manual two-terminal setup below still works and remains the underlying primitive.
```

- [ ] **Step 2: Update the `CLAUDE.md` Commands section**

In `CLAUDE.md`, replace the `## Commands` intro and backend block's first lines so the launcher is the primary path. Insert at the top of the `## Commands` section (before the "Backend (run from repo root…" block):

```markdown
Primary entry point (cross-platform, from repo root):
```bash
python studio.py setup            # one-time: venv, deps, PyTorch/CUDA auto-detect, system-dep checks, model picker
python studio.py start            # run backend + frontend together (auto dev/prod)
python studio.py start --dev      # force dev (uvicorn :8880 + Vite :5173, hot reload)
python studio.py start --prod     # force prod (single server :8880 serving UI + API)
python studio.py models           # re-open the interactive model picker
```
`studio.py` is stdlib-only and bootstraps `backend/venv`; it forwards `start` flags (`--device`, `--port`, …) to `backend.cli`. The raw commands below are the underlying primitives.
```

- [ ] **Step 3: Add the launcher to the CLAUDE.md architecture section**

In `CLAUDE.md`, append a bullet to the Architecture list:

```markdown
- **`studio.py` + `tools/envdetect.py` (repo root)** — the cross-platform launcher. `studio.py` is **stdlib-only** (runs before the venv exists) and orchestrates setup/start/models; `tools/envdetect.py` does CUDA detection → PyTorch wheel-index mapping. Model pre-download lives in `backend/scripts/download_models.py`. Prod mode is enabled by `_mount_frontend()` in `app.py`, which serves `frontend/dist` at `/` when present.
```

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document the studio.py two-command flow and rebrand"
```

---

## Task 7: Final manual verification

**No code — run-through and record results.**

- [ ] **Step 1: Full test suite green**

Run: `cd backend && python -m pytest tests/ -v`
Expected: all tests PASS (smoke + setup helpers).

- [ ] **Step 2: Dispatcher help & dry parse**

Run: `python studio.py --help`, `python studio.py start --help`, `python studio.py models` (then blank-enter to skip).
Expected: no tracebacks; `models` skips cleanly when given blank input and a venv exists.

- [ ] **Step 3: Dev launch (interactive, optional but recommended)**

Run: `python studio.py start --dev`
Expected: both `[backend]`-side uvicorn (`Uvicorn running on http://0.0.0.0:8880`) and Vite (`localhost:5173`) come up; opening http://localhost:5173 loads the UI; one Ctrl+C stops both and returns to the prompt.

- [ ] **Step 4: Prod launch (interactive, optional)**

Run: `python studio.py start --prod`
Expected: `npm run build` runs (if no dist), then a single uvicorn on :8880; http://localhost:8880 serves the UI and http://localhost:8880/api/health returns JSON. Ctrl+C stops it.

- [ ] **Step 5: Commit any fixes found during verification, then finish**

Use the `superpowers:finishing-a-development-branch` skill to decide how to integrate the work.

---

## Self-Review Notes

- **Spec coverage:** entry points (T4), setup flow incl. PyTorch auto-detect (T1/T4), system-dep guidance (T4), frontend install (T4), model picker + downloader (T2/T4), dev/prod start + mode resolution (T4), static mount (T3), CLI rebrand (T5), docs+branding (T6), tests for pure helpers (T1–T4). All spec sections map to a task.
- **Type/name consistency:** `venv_python`, `build_backend_cmd`, `_mount_frontend`, `parse_model_selection`, `MODEL_CATALOG`, `detect_cuda_tag`, `torch_index_url`, `cuda_version_to_tag`, `parse_nvidia_smi_cuda_version` are used identically across tasks and tests.
- **Known limitation (acceptable):** the model picker labels/sizes are mirrored in `studio.py` for the prompt while `download_models.py` owns the canonical catalog + validation. If the catalog changes, update both — called out here intentionally rather than coupling the stdlib launcher to an in-venv import.
