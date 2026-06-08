"""Audio-fallback transcription (M3): when a video has no captions, download its
audio and run speech-to-text. Free-tier path — Groq Whisper first (fast, 25MB
free cap), Gemini for larger/long audio. Output is always ENGLISH.

LOCAL ONLY in practice: yt-dlp downloads from YouTube, which is IP-blocked from
datacenter/cloud IPs (the same "Wall B" as caption fetching) — it works from a
residential IP. ffmpeg is supplied by the static-ffmpeg package (no system install).
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile

import httpx
from fastapi.concurrency import run_in_threadpool

from .config import settings
from .transcript import NoTranscript, TranscriptBlocked, TranscriptError, VideoUnavailable

logger = logging.getLogger("app.audio")

_ffmpeg_ready = False


def _ensure_ffmpeg() -> None:
    """Make a bundled ffmpeg/ffprobe available on PATH (downloaded once, cached)."""
    global _ffmpeg_ready
    if _ffmpeg_ready:
        return
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths()
    except Exception:  # noqa: BLE001 — fall back to a system ffmpeg if present
        pass
    _ffmpeg_ready = True


def _download_audio(video_id: str) -> str:
    """Download + compress the video's audio to a small 16kHz-mono mp3 and return
    its path (caller deletes its directory). Blocking — run in a thread."""
    _ensure_ffmpeg()
    import yt_dlp

    tmpdir = tempfile.mkdtemp(prefix="vsai_audio_")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        # 16kHz mono ~32kbps: tiny + plenty for ASR (Whisper resamples to 16k anyway),
        # so a ~90-min video still fits Groq's 25MB free-tier cap.
        "postprocessor_args": ["-ar", "16000", "-ac", "1", "-b:a", "32k"],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmpdir, ignore_errors=True)
        msg = str(exc).lower()
        if any(s in msg for s in ("sign in", "bot", "403", "forbidden", "confirm you")):
            raise TranscriptBlocked(
                "YouTube blocked the audio download from this server's IP. On a cloud "
                "host use a residential proxy or a managed transcript API."
            )
        if any(s in msg for s in ("unavailable", "private", "removed", "does not exist")):
            raise VideoUnavailable("This video is unavailable.")
        raise TranscriptError(f"Couldn't download the audio ({type(exc).__name__}).")

    mp3 = os.path.join(tmpdir, "audio.mp3")
    if not os.path.exists(mp3):
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise TranscriptError("Audio download produced no file (is ffmpeg available?).")
    return mp3


async def _groq_translate(path: str) -> str:
    """Groq Whisper /audio/translations -> English transcript (any source language)."""
    with open(path, "rb") as f:
        content = f.read()
    async with httpx.AsyncClient(timeout=settings.audio_transcribe_timeout) as client:
        resp = await client.post(
            f"{settings.groq_base_url}/audio/translations",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            files={"file": ("audio.mp3", content, "audio/mpeg")},
            data={"model": settings.groq_whisper_model, "response_format": "text", "temperature": "0"},
        )
    if resp.status_code != 200:
        raise TranscriptError(f"Groq transcription failed ({resp.status_code}).")
    return resp.text.strip()


async def _gemini_transcribe(path: str) -> str:
    """Gemini fallback (no size cap): upload the audio, transcribe + translate to English."""
    from .llm import gemini_client

    client = gemini_client()
    uploaded = await client.aio.files.upload(file=path)
    try:
        resp = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[
                uploaded,
                "Transcribe this audio verbatim. If it is not in English, translate it to "
                "English. Output ONLY the transcript text — no preamble, timestamps, or notes.",
            ],
        )
        try:
            return (resp.text or "").strip()
        except Exception:  # noqa: BLE001 — blocked/empty response
            return ""
    finally:
        try:
            await client.aio.files.delete(name=uploaded.name)
        except Exception:  # noqa: BLE001
            pass


async def transcribe_audio(video_id: str) -> str:
    """Download a video's audio and transcribe it to English (Whisper -> Gemini)."""
    if not settings.audio_fallback_enabled:
        raise NoTranscript("This video has no captions, and audio transcription is disabled.")
    if not (settings.groq_api_key or settings.gemini_api_key):
        raise NoTranscript("This video has no captions, and no transcription engine is configured.")

    path = await run_in_threadpool(_download_audio, video_id)
    tmpdir = os.path.dirname(path)
    try:
        size = os.path.getsize(path)
        # Whisper first when the file fits the free-tier cap.
        if settings.groq_api_key and size <= settings.groq_audio_max_bytes:
            try:
                text = await _groq_translate(path)
                if text.strip():
                    return text
            except Exception as exc:  # noqa: BLE001
                logger.warning("Groq Whisper failed (%s); trying Gemini", exc)
        # Gemini fallback (no size cap) — also covers a Whisper failure.
        if settings.gemini_api_key:
            text = await _gemini_transcribe(path)
            if text.strip():
                return text
        raise NoTranscript("Couldn't transcribe this video's audio.")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
