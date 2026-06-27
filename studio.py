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


def chatterbox_venv_python(repo_root: Path) -> Path:
    """Path to the ISOLATED Chatterbox venv's Python interpreter."""
    venv = repo_root / "backend" / "venv-chatterbox"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def chatterbox_ready_marker(repo_root: Path) -> Path:
    """Sentinel written only after a FULL successful Chatterbox install.

    The venv's Python exists after `python -m venv` (step 1), long before the
    packages are installed, so its mere presence can't mean "installed". This
    marker is created last, so an interrupted install never looks complete.
    """
    return repo_root / "backend" / "venv-chatterbox" / ".chatterbox-ready"


def _ensure_chatterbox_env() -> bool:
    """Create backend/venv-chatterbox and install chatterbox-tts into it.

    Chatterbox can't share the main venv (transformers pin conflict), so it
    gets its own environment with a CUDA-matched torch + chatterbox-tts.
    Returns True on success, False on any failure.
    """
    # Clear any stale "ready" marker up front so a half-finished re-install
    # never reports as complete; it's re-created only on full success below.
    marker = chatterbox_ready_marker(REPO_ROOT)
    try:
        marker.unlink()
    except OSError:
        pass
    cpy = chatterbox_venv_python(REPO_ROOT)
    if not cpy.is_file():
        print("  Creating isolated Chatterbox environment (backend/venv-chatterbox) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-chatterbox")]) != 0:
            print("  ERROR: failed to create venv-chatterbox.")
            return False
    # Upgrade pip so we can stream download progress: pip's machine-readable
    # `--progress-bar raw` (which works when output is piped, unlike the
    # animated bar) needs pip >= 23.1, but a fresh venv ships an older one.
    # Best effort — if the upgrade fails (e.g. offline), fall back to no bar.
    print("  Upgrading pip in the Chatterbox env …")
    raw_ok = _run([str(cpy), "-m", "pip", "install", "--upgrade", "pip"]) == 0
    progress = ["--progress-bar", "raw"] if raw_ok else []
    # CUDA-matched torch first (same detection as the main setup).
    tag = envdetect.detect_cuda_tag()
    index = envdetect.torch_index_url(tag)
    pip_torch = [str(cpy), "-m", "pip", "install", *progress, "torch", "torchaudio"]
    if index:
        pip_torch += ["--index-url", index]
    print("  Installing PyTorch into the Chatterbox env …")
    if _run(pip_torch) != 0:
        print("  ERROR: torch install into venv-chatterbox failed.")
        return False
    print("  Installing chatterbox-tts into the Chatterbox env …")
    if _run([str(cpy), "-m", "pip", "install", *progress, "-r",
             str(BACKEND_DIR / "requirements-chatterbox.txt")]) != 0:
        print("  ERROR: chatterbox-tts install failed.")
        return False
    # Mark the install complete (written last, after both pip steps succeed).
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print("  Chatterbox environment ready.")
    return True


def build_backend_cmd(py: Path, passthrough: list[str]) -> list[str]:
    """Command to launch the backend server via the venv Python."""
    return [py.as_posix(), "-m", "backend.cli", *passthrough]


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
    if "chatterbox" in picked:
        print("  Chatterbox selected — setting up its isolated environment …")
        _ensure_chatterbox_env()


# --------------------------------------------------------------- models --
def cmd_models(_args: argparse.Namespace) -> int:
    py = venv_python(REPO_ROOT)
    if not py.is_file():
        print("No venv found. Run:  python studio.py setup")
        return 1
    _interactive_model_picker(py)
    return 0


# ------------------------------------------------ install-chatterbox --
def cmd_install_chatterbox(_args: argparse.Namespace) -> int:
    """Non-interactive: build/refresh the isolated Chatterbox env. Used by the
    backend's in-UI installer. Returns 0 on success, 1 on failure."""
    print(BANNER)
    ok = _ensure_chatterbox_env()
    return 0 if ok else 1


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
    sub.add_parser("install-chatterbox", help="build the isolated Chatterbox env (non-interactive)")

    args = parser.parse_args(argv)
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "models":
        return cmd_models(args)
    if args.command == "install-chatterbox":
        return cmd_install_chatterbox(args)
    if args.command == "start":
        return cmd_start(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
