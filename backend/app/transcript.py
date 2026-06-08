"""YouTube transcript acquisition (M3).

Per `video_synopsis_final_plan.md` §3, fetching captions from our own datacenter
IP (e.g. Render) hits YouTube's bot-block ("Wall B"). So the strategy is:

  - LOCAL / residential IP  -> direct caption fetch (youtube-transcript-api) works.
  - PRODUCTION (cloud IP)   -> route through a managed transcript API (the plan's
                               PRIMARY path). Plug the provider into `_fetch_managed`
                               and set TRANSCRIPT_PROVIDER + TRANSCRIPT_API_KEY.

`fetch_transcript()` picks the provider from settings; everything above the seam
(URL parsing, error mapping, the API endpoint, the UI) is provider-agnostic.
"""
from __future__ import annotations

import re

import httpx
from fastapi.concurrency import run_in_threadpool

from .config import settings

# Matches the 11-char id in the common YouTube URL shapes.
_ID_IN_URL = re.compile(r"(?:v=|/shorts/|/embed/|/live/|/v/|youtu\.be/)([0-9A-Za-z_-]{11})")
_BARE_ID = re.compile(r"^[0-9A-Za-z_-]{11}$")


class TranscriptError(Exception):
    """Base error. `status` is the HTTP code and the message is user-safe."""

    status = 502

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class BadUrl(TranscriptError):
    status = 422


class NoTranscript(TranscriptError):
    status = 422


class VideoUnavailable(TranscriptError):
    status = 404


class TranscriptBlocked(TranscriptError):
    status = 502


def extract_video_id(url: str) -> str | None:
    """Canonicalize any YouTube URL (or a bare id) to the 11-char video id."""
    u = (url or "").strip()
    if _BARE_ID.match(u):
        return u
    m = _ID_IN_URL.search(u)
    return m.group(1) if m else None


async def fetch_title(video_id: str) -> str | None:
    """Best-effort video title via YouTube's public oEmbed (no API key)."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            )
        if r.status_code == 200:
            return (r.json().get("title") or "").strip() or None
    except Exception:
        pass
    return None


_ISO_DUR = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def _parse_iso_duration(s: str | None) -> int | None:
    """ISO-8601 duration (e.g. 'PT15M33S') -> seconds."""
    if not s:
        return None
    m = _ISO_DUR.fullmatch(s)
    if not m:
        return None
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se


async def fetch_metadata(video_id: str) -> tuple[str | None, int | None]:
    """Return (title, duration_seconds). Uses YouTube Data API v3 when a key is
    set (title + duration); otherwise falls back to oEmbed (title only)."""
    if settings.youtube_api_key:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "snippet,contentDetails", "id": video_id, "key": settings.youtube_api_key},
                )
            if r.status_code == 200:
                items = r.json().get("items") or []
                if items:
                    snip = items[0].get("snippet") or {}
                    cd = items[0].get("contentDetails") or {}
                    title = (snip.get("title") or "").strip() or None
                    return title, _parse_iso_duration(cd.get("duration"))
        except Exception:
            pass
    return await fetch_title(video_id), None


def _fetch_via_library(video_id: str) -> str:
    """Direct caption fetch (works on a residential/local IP). Runs in a thread."""
    from youtube_transcript_api import (
        YouTubeTranscriptApi,
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable as YTVideoUnavailable,
        VideoUnplayable,
        AgeRestricted,
        InvalidVideoId,
        RequestBlocked,
        IpBlocked,
    )

    api = YouTubeTranscriptApi()
    try:
        tlist = api.list(video_id)
        try:
            transcript = tlist.find_transcript(["en", "en-US", "en-GB"])
        except NoTranscriptFound:
            # No English track — take the first available, translate if possible.
            transcript = next(iter(tlist), None)
            if transcript is None:
                raise NoTranscript("This video has no transcript available.")
            if getattr(transcript, "is_translatable", False):
                try:
                    transcript = transcript.translate("en")
                except Exception:
                    pass
        fetched = transcript.fetch()
        text = " ".join(getattr(s, "text", "") for s in fetched if getattr(s, "text", "").strip())
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            raise NoTranscript("The transcript for this video was empty.")
        return text
    except (TranscriptsDisabled, NoTranscriptFound):
        raise NoTranscript("This video doesn't have captions available to transcribe.")
    except (YTVideoUnavailable, VideoUnplayable, AgeRestricted):
        raise VideoUnavailable("This video is unavailable or can't be transcribed.")
    except InvalidVideoId:
        raise BadUrl("That doesn't look like a valid YouTube video.")
    except (RequestBlocked, IpBlocked):
        raise TranscriptBlocked(
            "YouTube blocked the transcript request from this server's IP. "
            "On a cloud host, configure a managed transcript API (see the deploy notes)."
        )
    except TranscriptError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TranscriptError(f"Couldn't fetch the transcript ({type(exc).__name__}).")


async def _fetch_managed(video_id: str) -> str:
    """PROD seam: call a managed transcript provider (residential IPs + PO tokens).
    Not wired to a specific vendor yet — set TRANSCRIPT_PROVIDER and implement the
    REST call here when you pick one (e.g. Supadata). See plan §4.1."""
    raise TranscriptError(
        "No managed transcript provider is configured. Set TRANSCRIPT_PROVIDER, "
        "or run locally where a direct fetch works."
    )


async def fetch_captions(video_id: str) -> str:
    """Captions ONLY — raises NoTranscript when the video has none. No audio
    fallback, so it stays fast and is safe to call inside a request."""
    if settings.transcript_provider == "managed":
        return await _fetch_managed(video_id)
    # Default: direct caption fetch (good for local/residential IPs).
    return await run_in_threadpool(_fetch_via_library, video_id)


async def fetch_transcript(video_id: str) -> str:
    """Captions, or audio transcription as a fallback when there are none. The
    audio path is SLOW — callers that must stay responsive should call
    fetch_captions() and defer transcribe_audio() to the background worker."""
    try:
        return await fetch_captions(video_id)
    except NoTranscript:
        from .audio import transcribe_audio  # lazy import avoids a circular import

        return await transcribe_audio(video_id)
