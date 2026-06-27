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

import asyncio
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


def _managed_text_from_payload(data: object) -> str:
    """Pull transcript text out of a managed-provider JSON body. Handles plain-text
    mode (`content` is a string) and segmented mode (`content` is a list of
    {text, ...} chunks); tolerates a couple of common alternate field names."""
    content = data.get("content") if isinstance(data, dict) else None
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(seg.get("text", "") for seg in content if isinstance(seg, dict))
    elif isinstance(data, dict):
        text = data.get("transcript") or data.get("text") or ""
    else:
        text = ""
    return re.sub(r"\s+", " ", text or "").strip()


def _raise_for_managed_status(status_code: int) -> None:
    """Map a managed-provider HTTP status to a user-safe TranscriptError. Always
    raises (200/202 are handled by the caller before this is reached)."""
    if status_code == 206:  # Supadata: "no transcript available for this video"
        raise NoTranscript("This video doesn't have a transcript available.")
    if status_code in (401, 403):
        # Auth/quota/config problem — keep the cause out of the user-facing message.
        raise TranscriptError("The transcript service rejected the request. Please try again later.")
    if status_code == 404:
        raise VideoUnavailable("This video is unavailable or can't be transcribed.")
    if status_code in (400, 422):
        raise BadUrl("That doesn't look like a valid YouTube video.")
    if status_code == 429:
        raise TranscriptBlocked("The transcript service is busy right now. Please try again shortly.")
    if status_code >= 500:
        raise TranscriptBlocked("The transcript service had an error. Please try again shortly.")
    raise TranscriptError(f"Transcript service error ({status_code}).")


async def _poll_managed_job(client: httpx.AsyncClient, started: object, deadline_s: int) -> dict:
    """Poll a managed-provider async transcript job (HTTP 202 + a job id) until it
    completes, within ~deadline_s seconds. Returns the completed result body."""
    job_id = ""
    if isinstance(started, dict):
        job_id = str(started.get("jobId") or started.get("id") or "").strip()
    if not job_id:  # nothing to poll — treat the initial body as the result
        return started if isinstance(started, dict) else {}
    job_url = settings.transcript_api_url.rstrip("/") + "/" + job_id
    headers = {"x-api-key": (settings.transcript_api_key or "").strip()}
    for _ in range(max(1, deadline_s // 2)):
        await asyncio.sleep(2)
        jr = await client.get(job_url, headers=headers)
        if jr.status_code != 200:
            _raise_for_managed_status(jr.status_code)
        body = jr.json()
        status_str = ((body.get("status") if isinstance(body, dict) else "") or "").lower()
        if status_str in ("completed", "complete", "done", "success", "succeeded"):
            return body
        if status_str in ("failed", "error"):
            raise TranscriptBlocked("The transcript service couldn't process this video.")
        # else: queued / active — keep waiting
    raise TranscriptBlocked("The transcript is still being prepared. Please try again shortly.")


async def _fetch_managed(video_id: str) -> str:
    """PROD path: fetch a transcript via a managed provider (Supadata-compatible).
    Works from cloud/datacenter IPs, where the direct library fetch is IP-blocked.
    Requires TRANSCRIPT_API_KEY; TRANSCRIPT_API_URL can point at a compatible vendor."""
    api_key = (settings.transcript_api_key or "").strip()
    if not api_key:
        raise TranscriptError("Transcript service is not configured (TRANSCRIPT_API_KEY is unset).")
    params = {"url": f"https://www.youtube.com/watch?v={video_id}", "text": "true", "lang": "en"}
    headers = {"x-api-key": api_key}
    timeout = settings.transcript_api_timeout
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(settings.transcript_api_url, params=params, headers=headers)
            if r.status_code == 200:
                data = await _managed_result(client, r, timeout)
            elif r.status_code == 202:  # async job for long videos — poll it
                data = await _poll_managed_job(client, r.json(), timeout)
            else:
                _raise_for_managed_status(r.status_code)
                data = {}  # unreachable; _raise_for_managed_status always raises
    except TranscriptError:
        raise
    except httpx.HTTPError as exc:
        raise TranscriptBlocked(f"Couldn't reach the transcript service ({type(exc).__name__}).")

    text = _managed_text_from_payload(data)
    if not text:
        raise NoTranscript("This video doesn't have a transcript available.")
    return text


async def _managed_result(client: httpx.AsyncClient, response: httpx.Response, timeout: int) -> dict:
    """Normalize a 200 response: usually the transcript body, but some providers
    return a job id even on 200 — poll in that case."""
    body = response.json()
    if isinstance(body, dict) and not body.get("content") and (body.get("jobId") or body.get("id")):
        return await _poll_managed_job(client, body, timeout)
    return body if isinstance(body, dict) else {}


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
