"""End-to-end test: fetch YouTube transcripts through FREE public proxies.

For each video it runs two paths and compares:
  1. DIRECT  — no proxy, your machine's IP (residential -> should work).
  2. PROXY   — routed through free public proxies sourced by `free-proxy`,
               retrying with a fresh proxy on each block/failure.

Uses youtube-transcript-api 1.2.4 the CORRECT way: instance API
(`YouTubeTranscriptApi(...).fetch()`) with the proxy set on a requests
Session passed as `http_client` (the deprecated `proxies=` kwarg is gone).

Honest expectation: free public proxies are mostly datacenter/flagged IPs that
YouTube blocks, and they're slow/short-lived — so the PROXY path will likely be
flaky or fail outright while DIRECT succeeds. This script proves that empirically.
"""
from __future__ import annotations

import sys
import time
import textwrap

import requests
from fp.fp import FreeProxy
from fp.errors import FreeProxyException
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    RequestBlocked,
    IpBlocked,
)

VIDEOS = ["3baWzvEDfgU", "Vnm-ycSfJx4"]
LANGS = ["en", "en-US", "en-GB"]
PROXY_ATTEMPTS = 5      # fresh free proxies to try per video before giving up
FETCH_TIMEOUT = 8       # seconds per request (so a dead proxy can't hang us)


class TimeoutSession(requests.Session):
    """requests.Session with a default per-request timeout."""

    def __init__(self, timeout: float = FETCH_TIMEOUT):
        super().__init__()
        self._timeout = timeout

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", self._timeout)
        return super().request(*args, **kwargs)


def _fetch_text(api: YouTubeTranscriptApi, video_id: str) -> str:
    """Fetch transcript text, preferring English, else first available (translated)."""
    try:
        fetched = api.fetch(video_id, languages=LANGS)
    except NoTranscriptFound:
        tlist = api.list(video_id)
        t = next(iter(tlist), None)
        if t is None:
            raise
        if getattr(t, "is_translatable", False):
            try:
                t = t.translate("en")
            except Exception:
                pass
        fetched = t.fetch()
    return " ".join(s.text for s in fetched if s.text.strip())


def run_direct(video_id: str):
    api = YouTubeTranscriptApi(http_client=TimeoutSession())
    t0 = time.time()
    try:
        text = _fetch_text(api, video_id)
        print(f"     OK: {len(text)} chars in {time.time() - t0:.1f}s | {textwrap.shorten(text, 90)!r}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"     FAIL: {type(e).__name__}: {str(e)[:120]}")
        return False


def run_via_proxy(video_id: str):
    for i in range(1, PROXY_ATTEMPTS + 1):
        try:
            proxy = FreeProxy(rand=True, https=True, timeout=1.5).get()
        except FreeProxyException as e:
            print(f"     [{i}/{PROXY_ATTEMPTS}] could not source a free proxy: {str(e)[:70]}")
            continue
        sess = TimeoutSession()
        sess.proxies = {"http": proxy, "https": proxy}
        api = YouTubeTranscriptApi(http_client=sess)
        t0 = time.time()
        try:
            text = _fetch_text(api, video_id)
            print(f"     [{i}/{PROXY_ATTEMPTS}] {proxy}  ->  OK ({len(text)} chars, {time.time() - t0:.1f}s)")
            return True, f"OK via {proxy} ({len(text)} chars)"
        except (RequestBlocked, IpBlocked):
            print(f"     [{i}/{PROXY_ATTEMPTS}] {proxy}  ->  BLOCKED by YouTube ({time.time() - t0:.1f}s)")
        except (TranscriptsDisabled, NoTranscriptFound):
            print(f"     [{i}/{PROXY_ATTEMPTS}] {proxy}  ->  reached YouTube; no transcript for this video")
            return False, "no transcript (not a proxy issue)"
        except VideoUnavailable:
            print(f"     [{i}/{PROXY_ATTEMPTS}] {proxy}  ->  video unavailable")
            return False, "video unavailable"
        except Exception as e:  # noqa: BLE001  (proxy timeout / conn error / bad payload)
            print(f"     [{i}/{PROXY_ATTEMPTS}] {proxy}  ->  {type(e).__name__}: {str(e)[:55]} ({time.time() - t0:.1f}s)")
    return False, f"all {PROXY_ATTEMPTS} proxy attempts failed/blocked"


def main():
    print("=" * 72)
    print("FREE PUBLIC PROXY + youtube-transcript-api  —  end-to-end test")
    print("=" * 72)
    summary = []
    for vid in VIDEOS:
        print(f"\n### {vid}  (https://www.youtube.com/watch?v={vid})")
        print("  -- DIRECT (no proxy, your IP) --")
        direct_ok = run_direct(vid)
        print("  -- VIA FREE PUBLIC PROXY --")
        proxy_ok, proxy_info = run_via_proxy(vid)
        summary.append((vid, direct_ok, proxy_ok, proxy_info))

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"{'video':14} {'direct':8} {'free-proxy':12} detail")
    for vid, d, p, info in summary:
        print(f"{vid:14} {'OK' if d else 'FAIL':8} {'OK' if p else 'FAIL':12} {info}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # transcripts may contain non-ascii
    except Exception:
        pass
    main()
