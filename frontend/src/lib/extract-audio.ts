// Browser-side audio extraction via ffmpeg.wasm. We strip a compact 16 kHz-mono
// mp3 from the chosen video/audio file IN THE BROWSER, so only the small audio
// (a few MB) is uploaded — not the whole video. Uses the single-threaded core,
// which needs no COOP/COEP headers (those would break the Google sign-in popup).
import { FFmpeg } from "@ffmpeg/ffmpeg";
import { fetchFile, toBlobURL } from "@ffmpeg/util";

// Pinned, immutable version (matches the installed @ffmpeg/core).
const CORE_BASE = "https://unpkg.com/@ffmpeg/core@0.12.10/dist/umd";

let _ffmpeg: FFmpeg | null = null;
let _loading: Promise<FFmpeg> | null = null;
let _onProgress: ((p: number) => void) | null = null;

async function getFFmpeg(): Promise<FFmpeg> {
  if (_ffmpeg) return _ffmpeg;
  if (!_loading) {
    _loading = (async () => {
      const ff = new FFmpeg();
      ff.on("progress", ({ progress }) => {
        if (_onProgress) _onProgress(Math.max(0, Math.min(1, progress)));
      });
      await ff.load({
        coreURL: await toBlobURL(`${CORE_BASE}/ffmpeg-core.js`, "text/javascript"),
        wasmURL: await toBlobURL(`${CORE_BASE}/ffmpeg-core.wasm`, "application/wasm"),
      });
      _ffmpeg = ff;
      return ff;
    })();
  }
  return _loading;
}

/** Extract a small 16 kHz-mono mp3 from a media file. onProgress is 0..1. */
export async function extractAudio(file: File, onProgress?: (p: number) => void): Promise<Blob> {
  const ff = await getFFmpeg();
  _onProgress = onProgress ?? null;
  try {
    await ff.writeFile("input", await fetchFile(file));
    await ff.exec(["-i", "input", "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", "out.mp3"]);
    const data = (await ff.readFile("out.mp3")) as Uint8Array;
    const bytes = new Uint8Array(data.length); // fresh (non-shared) buffer for Blob
    bytes.set(data);
    const blob = new Blob([bytes], { type: "audio/mpeg" });
    ff.deleteFile("input").catch(() => {});
    ff.deleteFile("out.mp3").catch(() => {});
    if (blob.size === 0) throw new Error("No audio track found");
    return blob;
  } finally {
    _onProgress = null;
  }
}
