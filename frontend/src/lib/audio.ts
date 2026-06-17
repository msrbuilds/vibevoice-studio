// Audio helpers: WAV <-> PCM16, AudioContext playback, export concatenation.

export const DEFAULT_SAMPLE_RATE = 24_000;

export function wavToPcm16(wavData: ArrayBuffer): Int16Array {
  // Canonical PCM WAV: 44-byte header followed by little-endian int16 samples.
  // We don't try to parse the header; we just skip it. If the file is malformed
  // (different header size) the resulting Int16Array will be offset and the
  // browser will produce a brief click. That's acceptable for a debug-only
  // failure mode.
  return new Int16Array(wavData, 44);
}

export function createWavFile(samples: Int16Array, sampleRate: number): Blob {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataSize = samples.length * (bitsPerSample / 8);
  const headerSize = 44;
  const fileSize = headerSize + dataSize;

  const buffer = new ArrayBuffer(fileSize);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, fileSize - 8, true);
  writeString(view, 8, "WAVE");

  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);

  writeString(view, 36, "data");
  view.setUint32(40, dataSize, true);

  const dataView = new Int16Array(buffer, headerSize);
  dataView.set(samples);

  return new Blob([buffer], { type: "audio/wav" });
}

function writeString(view: DataView, offset: number, str: string): void {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

export function createSilence(durationMs: number, sampleRate = DEFAULT_SAMPLE_RATE): Int16Array {
  return new Int16Array(Math.floor((durationMs / 1000) * sampleRate));
}

export function pcm16ToFloat32(pcm: Int16Array): Float32Array {
  const out = new Float32Array(pcm.length);
  for (let i = 0; i < pcm.length; i++) {
    out[i] = pcm[i] / 32768;
  }
  return out;
}

export class AudioPlayer {
  private ctx: AudioContext | null = null;
  private currentSource: AudioBufferSourceNode | null = null;

  private getContext(sampleRate: number): AudioContext {
    if (!this.ctx || this.ctx.state === "closed") {
      // Try to honor the backend's sample rate, but fall back to the
      // browser default if the requested rate isn't supported.
      const Ctx = window.AudioContext;
      const supported = Ctx && sampleRate >= 8000 && sampleRate <= 96000;
      this.ctx = supported ? new Ctx({ sampleRate }) : new Ctx();
    }
    if (this.ctx.state === "suspended") {
      void this.ctx.resume();
    }
    return this.ctx;
  }

  playPcm16(pcm: Int16Array, sampleRate: number): Promise<void> {
    return new Promise((resolve) => {
      const ctx = this.getContext(sampleRate);
      const float32 = pcm16ToFloat32(pcm);
      const buffer = ctx.createBuffer(1, float32.length, sampleRate);
      buffer.getChannelData(0).set(float32);

      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      this.currentSource = source;

      source.onended = () => {
        if (this.currentSource === source) this.currentSource = null;
        resolve();
      };
      source.start();
    });
  }

  stop(): void {
    if (this.currentSource) {
      try {
        this.currentSource.stop();
        this.currentSource.disconnect();
      } catch {
        // ignore
      }
      this.currentSource = null;
    }
  }

  close(): void {
    this.stop();
    this.ctx?.close();
    this.ctx = null;
  }
}
