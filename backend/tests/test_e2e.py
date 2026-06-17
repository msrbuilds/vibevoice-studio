"""End-to-end test: actually start uvicorn in a thread and hit it with httpx.

Verifies the wiring from CLI through app → routes → response, but with a stubbed
model so we don't need the 5.4 GB checkpoint downloaded.
"""

import asyncio
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND.parent))

import httpx  # noqa: E402

# Patch the from_pretrained methods so load() doesn't fetch real weights
from vibevoice.modular.modeling_vibevoice_inference import (  # noqa: E402
    VibeVoiceForConditionalGenerationInference,
)
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor  # noqa: E402


class _StubProcessor:
    audio_processor = type("AP", (), {"sampling_rate": 24000})()
    tokenizer = object()

    def __call__(self, *a, **kw):
        return {"input_ids": object(), "attention_mask": object()}


class _StubModel:
    def eval(self):
        return self

    def set_ddpm_inference_steps(self, num_steps):
        pass

    def generate(self, *a, **kw):
        import torch
        out = type(
            "Out",
            (),
            {"speech_outputs": [torch.zeros(24000, dtype=torch.float32)]},
        )()
        return out


VibeVoiceProcessor.from_pretrained = classmethod(lambda cls, *a, **kw: _StubProcessor())
VibeVoiceForConditionalGenerationInference.from_pretrained = classmethod(
    lambda cls, *a, **kw: _StubModel()
)


from backend.app import create_app  # noqa: E402
from backend.config import Settings  # noqa: E402


def _build_app():
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    settings = Settings(
        model_id="vibevoice/VibeVoice-1.5B",
        device="cpu",
        voices_dir=tmp / "v",
        uploads_dir=tmp / "u",
        log_level="warning",
    )
    return create_app(settings), tmp


def _start_uvicorn(app, port: int) -> threading.Thread:
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    # Wait for startup
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return t


async def _main() -> int:
    import tempfile

    app, tmp = _build_app()
    port = 18880  # avoid the default 8880
    _start_uvicorn(app, port)
    print(f"Server up on http://127.0.0.1:{port}")

    # Drop a fake voice file so /api/voices returns something
    import soundfile as sf
    import numpy as np
    (tmp / "v").mkdir(parents=True, exist_ok=True)
    sf.write(str(tmp / "v" / "en-test.wav"), np.zeros(24000, dtype=np.float32), 24000, subtype="PCM_16")

    base = f"http://127.0.0.1:{port}/api"
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Health
        r = await client.get(f"{base}/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok", body
        assert body["model_loaded"] is True
        print("  PASS  GET /api/health")

        # 2. Config
        r = await client.get(f"{base}/config")
        assert r.status_code == 200
        cfg = r.json()
        assert cfg["sampling_rate"] == 24000
        assert cfg["default_cfg_scale"] == 1.3
        print(f"  PASS  GET /api/config (model_id={cfg['model_id']!r}, device={cfg['device']!r})")

        # 3. Voices
        r = await client.get(f"{base}/voices")
        assert r.status_code == 200
        vs = r.json()["voices"]
        assert len(vs) == 1
        assert vs[0]["id"] == "en-test"
        assert vs[0]["source"] == "builtin"
        print(f"  PASS  GET /api/voices ({len(vs)} voice)")

        # 4. Synthesize
        r = await client.post(
            f"{base}/synthesize",
            json={
                "text": "Hello from the e2e test.",
                "speakers": [{"name": "Alice", "voice": "en-test"}],
            },
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "audio/wav"
        body = r.content
        assert body[:4] == b"RIFF", body[:8]
        print(f"  PASS  POST /api/synthesize (got {len(body)} bytes WAV)")

        # 5. Synthesize with bad voice → 404
        r = await client.post(
            f"{base}/synthesize",
            json={"text": "hi", "speakers": [{"name": "A", "voice": "nope"}]},
        )
        assert r.status_code == 404, r.text
        assert r.json()["code"] == "voice_not_found"
        print("  PASS  POST /api/synthesize (404 on bad voice)")

        # 6. Bad upload → 400
        r = await client.post(
            f"{base}/voices/upload",
            files={"file": ("x.txt", b"not audio", "text/plain")},
        )
        assert r.status_code == 400
        print("  PASS  POST /api/voices/upload (400 on bad ext)")

        # 7. Multi-speaker synthesize
        r = await client.post(
            f"{base}/synthesize",
            json={
                "text": "Alice: Hello!\nBob: Hi there.",
                "speakers": [
                    {"name": "Alice", "voice": "en-test"},
                    {"name": "Bob", "voice": "en-test"},
                ],
            },
        )
        assert r.status_code == 200, r.text
        print("  PASS  POST /api/synthesize (multi-speaker)")

    print("\nAll e2e checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
