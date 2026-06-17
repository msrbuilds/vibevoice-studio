# Taste (Continuously Learned by [CommandCode][cmd])

[cmd]: https://commandcode.ai/

# Environment
- User is on Windows using PowerShell; `&&` is not a valid statement separator in PowerShell — use `;` or separate commands. Confidence: 0.95

# Project Structure
- Backend is a Python package with relative imports — run CLI as `python -m cli` from `backend/` (or `python -m backend.cli` from project root), not `python cli.py`. Confidence: 0.95
- Built-in voice registry glob is in `backend/services/voices.py` `_scan_builtin` — accepts `.wav`, `.mp3`, `.flac`, `.ogg`. After adding new files to `backend/voices/`, the backend MUST be restarted to re-scan (the scan only happens at startup). Confidence: 0.90
- Sample scripts in `frontend/src/lib/samples.ts` reference voice IDs by filename stem. Use the `DEFAULT_FEMALE_VOICE` / `DEFAULT_MALE_VOICE` constants at the top of that file to change which voices the built-in samples use, rather than hard-coding voice IDs throughout. Confidence: 0.85

# Architecture
- Persist the audio cache on the backend (not as an in-memory browser-side React reducer state) so cache survives browser refreshes. Confidence: 0.85
