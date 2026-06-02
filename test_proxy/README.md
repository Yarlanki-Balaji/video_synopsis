# test_proxy — free-proxy experiment

A throwaway, standalone experiment (not part of the app) that measures whether
**free public proxies** can fetch YouTube transcripts via `youtube-transcript-api`.

For each video it runs:
1. **DIRECT** — no proxy (your residential IP) as a baseline.
2. **VIA FREE PROXY** — routed through proxies sourced by `free-proxy`, retrying
   with a fresh proxy on each YouTube block/failure.

## Run

```bash
# from the repo root, using the backend venv (has youtube-transcript-api 1.2.4)
backend/.venv/Scripts/python.exe -m pip install free-proxy
backend/.venv/Scripts/python.exe test_proxy/test_free_proxy_transcript.py
```

## What to expect

Free public proxies are overwhelmingly datacenter/flagged IPs that YouTube blocks
(the "Wall B" problem), and they're slow + short-lived. So the **DIRECT** path
typically succeeds while the **FREE PROXY** path is flaky or fails — which is the
point of the test. For production, use a managed transcript API or a paid
**residential** proxy instead (see `backend/app/transcript.py` and the plan doc).
