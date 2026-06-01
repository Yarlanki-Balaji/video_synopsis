# Transcript Acquisition — Final Plan

**Date:** 2026-06-01
**Scope:** How the app gets a YouTube transcript into the summarizer. Settles the
"can't we just fetch from YouTube directly / from the user's IP / without CORS / with yt-dlp" question.
**Consistent with:** `video_summarizer_build_guide.md` Part D, and `video_summarizer_system_design.md`.

---

## 1. The decision (TL;DR)

We use **three layers**, in this priority order:

1. **Managed transcript API (PRIMARY)** — backend calls a hosted provider (e.g. Supadata) that does the
   YouTube proxying + PO-token handling for us. Covers **desktop + mobile** with zero install. This is the
   NoteGPT-parity "paste a URL, no extension" path.
2. **Browser extension (OPTIONAL, desktop power-users)** — Manifest V3 extension reads captions
   **on the user's own IP, same-origin inside the YouTube tab**. Free + unlimited; used to **conserve the
   API's monthly quota**. Not required to launch.
3. **Paste (UNIVERSAL FALLBACK)** — user pastes transcript text. Always works, zero dependency. The safety
   net when the API quota is spent, the extension isn't installed, or the store rejects it.

> We do **NOT** fetch captions from our own Render server hitting YouTube directly. Reasons in §3.

---

## 2. Why not "just fetch from YouTube directly" — the four walls

There are **two independent walls**, and they trip different approaches. This is the core insight.

| Approach | Where it runs | CORS wall? | IP / PO-token wall? | Works in prod? |
|---|---|:---:|:---:|:---:|
| Web-page `fetch()` (frontend JS) | User's browser | ❌ **blocked by CORS** | (user IP, fine) | ❌ |
| Mobile / PWA `fetch()` | User's browser | ❌ **blocked by CORS** | (user IP, fine) | ❌ |
| **Our server / yt-dlp / curl** | Render (cloud) | ✅ no CORS | ❌ **datacenter IP + PO token** | ❌ |
| **Browser extension** | User's browser, *inside YouTube's origin* | ✅ no CORS | ✅ user's home IP | ✅ **yes** |
| yt-dlp on the **user's own machine** | User's PC | ✅ no CORS | ✅ user's home IP | ✅ yes, but needs a desktop install |
| Managed API (Supadata) | Provider's residential IPs | ✅ no CORS | ✅ provider handles it | ✅ **yes** |

**Wall A — CORS (browser-only).** The same-origin policy is enforced by the *browser* and the permission must
come from *YouTube's* response header (`Access-Control-Allow-Origin`), which YouTube does not send. We can't add
a header to a server we don't own, and we can't disable a security check on the user's browser. So a normal web
page can't read YouTube's caption response — even though it's on the user's IP.

**Wall B — datacenter IP + PO token (server-only).** YouTube blocks cloud/datacenter IP ranges for caption
endpoints (`Sign in to confirm you're not a bot`, 429s, empty bodies), and the caption endpoint increasingly
requires a **PO token** that only a real browser running YouTube's JS can mint. Our Render server can't reliably
produce one.

**Key realization:** CORS was never our real blocker — Wall B is. Tools that "have no CORS" (yt-dlp, curl, our
backend) all run server-side and therefore hit Wall B instead.

---

## 3. The specific "shortcut" questions, answered

- **"Send the request from our system/server IP instead of the API/extension?"**
  No. Render = datacenter IP → Wall B (bot-block + PO token). This is exactly what the API/extension exist to avoid.

- **"Use the user's system IP without proxies?"**
  Yes — but *only* code running on the user's device sees the user's IP. The only such mechanism that can also
  *read* YouTube's response is the **extension** (it runs inside YouTube's origin, so no CORS). A plain web page
  on the user's IP is still blocked by Wall A (CORS).

- **"Can't we get rid of CORS?"**
  No. CORS for a YouTube request is controlled by YouTube + the browser, not us. `no-cors` mode returns an
  unreadable opaque response; browser flags only work on our own dev machine; a "CORS proxy" moves the request
  to a datacenter IP (Wall B) and *is* a proxy. The extension is the only sanctioned cross-origin bypass.

- **"yt-dlp does the same thing and has no CORS — so use it?"**
  Correct that yt-dlp has no CORS (it's not a browser). But on our server it hits Wall B (datacenter IP + brittle
  PO-token support that breaks on YouTube updates). yt-dlp only "works" on the **user's machine** — which means
  shipping a desktop app to install. The extension is the lightweight, browser-based version of that. A managed
  API is essentially "yt-dlp on residential IPs with PO-token solving, maintained by someone else."

---

## 4. What we build (concrete)

### 4.1 Managed transcript API (D2) — PRIMARY, build first
- Backend endpoint calls the provider's REST API with the canonical **11-char video id** and gets back transcript text.
- **Provider:** Supadata as the default (~100 free/month). **Pick during build** — keep a thin adapter interface so
  we can swap providers / add a backup without touching callers. *(Supadata is the example, not yet locked in.)*
- **Monthly credit counter** in our DB: when the free quota is exhausted, **fall back to paste** (clear message,
  no error).
- Tag provenance `source = "api"` → this is the **trusted** source allowed to populate the **shared** cache.

### 4.2 Browser extension (D1) — OPTIONAL, build second
- Chrome **Manifest V3**, host permission for `youtube.com`.
- Content script (page context) reads the player's caption track → fetches text **same-origin** → hands to the
  background **service worker** → service worker POSTs to backend with the user's Bearer token.
- Caveats baked in: **verify captured video id matches the page** (avoid SPA wrong-video race, R16); treat an
  **empty caption body as failure**, not a transcript (R4); **nonce/origin-check** the page↔extension bridge (R35).
- Provenance `source = "extension"` → **user-scoped** (untrusted), not auto-shared.
- Desktop only. Chrome Web Store review can take days–weeks and may reject scraping-style extensions (R36) — which
  is exactly why paste must work without it.

### 4.3 Paste (D3) — UNIVERSAL FALLBACK, always available
- Textarea → same validate → enqueue path. Provenance `source = "paste"` → **user-scoped** (untrusted).

### 4.4 Cross-cutting guards (apply to all three)
- **D4 Provenance + content-binding:** store `source` + `sha256(transcript)` with every cached summary. A shared
  cross-user summary is reused **only if the requester's transcript hash matches**. Only `api` (trusted) populates
  the shared cache; `paste`/`extension` stay user-scoped. Canonicalize to the **11-char video id** as the key.
- **D5 Empty/invalid floors:** before creating a job, reject empty / too-short-for-duration / mostly-timestamps /
  single-repeated-token transcripts — clear error, **no quota spent**.

---

## 5. Request flow (end state)

```
Desktop + extension installed?  ──► extension captures on user IP ──► POST text ──┐
Mobile / no extension?          ──► backend calls managed API (user pastes URL) ──┤
Anyone, anything failed?        ──► user pastes transcript text ──────────────────┤
                                                                                  ▼
                                          validate (D5) → provenance+hash (D4) →
                                          cache check (G4) → enqueue job → Groq
```

---

## 6. Build order (fits guide milestone M3)

1. **Managed API path first** — it's just one REST call; gets mobile + desktop working day one.
2. **Provenance + content-binding (D4) + empty/invalid floors (D5)** — wire these in *with* the API path, not after.
3. **Chrome extension (D1)** — desktop quota-saver; submit to Web Store early (review latency).
4. **Paste (D3)** — trivial, but confirm it's the fallback for *every* failure branch (quota out, store reject,
   no captions).

---

## 7. Open items to decide during build

- **Final provider + backup** for D2 (Supadata vs alternatives; confirm free quota, reliability, language support).
- **Quota-exhaustion UX** — exact message + when to nudge desktop users to install the extension.
- **Extension store risk** — have paste-only flow fully working before/independent of store approval.

---

## 8. Full build workflow (end-to-end task checklist)

This is the *whole app* build order, not just transcripts. Build the **engine before the dashboard** — each
milestone ends with something you can demo. Maps to `video_summarizer_build_guide.md` Part J (M0–M5) and the
A/B/D/F section refs.

### M0 — Scaffold (½ day) — *foundations*
- [ ] FastAPI backend app skeleton (Render) + Next.js frontend app skeleton (Vercel).
- [ ] Connect **Aiven Postgres + Valkey** (Redis-compatible) from the backend.
- [ ] `/healthz` endpoint; confirm both deploys are live and talk to each other.
- **Demo:** both deploys up, frontend reaches backend.

### M1 — Auth & accounts (2–3 days) — *frontend login/auth + backend auth* `[A2, A3, B1–B7]`
**Frontend**
- [ ] **Signup page** `/signup` with **invite/allowlist gate** (closed beta) `[A2]`.
- [ ] **Login page** `/login` `[A3]`.
- [ ] Logout (incl. "log out everywhere").
- [ ] Wire auth state + protected routes (redirect unauth'd users to `/login`).
**Backend**
- [ ] **Password hashing** with bcrypt/passlib `[B1]`.
- [ ] **Access token** = JWT in an **httpOnly cookie**, **algorithm-pinned** `[B2]`.
- [ ] **Refresh tokens**: hashed at rest, **rotated**, reuse-detected `[B3]` *(critical)*.
- [ ] **Session revocation** via `token_version` (log-out-everywhere) `[B4]`.
- [ ] **Allowlist + invites checked on *every* request** `[B5]`.
- [ ] **Email provider** (Resend/Postmark) for invites + password reset `[B6]`.
- [ ] **CSRF protection** (required because auth is cookie-based) `[B7]`.
- **Demo:** invited user signs up → verifies email → logs in → logs out everywhere.

### M2 — Job engine + Groq (3–5 days) — *the engine, do this early (riskiest)* `[F1–F6]`
- [ ] Postgres **job ledger** (`jobs` table: id, user_id, video_hash, transcript_sha256,
      idempotency_key UNIQUE, status, phase, attempts, lease_owner, lease_expires_at, …).
- [ ] In-process **worker** + **reaper** (reclaim expired leases).
- [ ] **Groq client** → `openai/gpt-oss-120b` (OpenAI-compatible API) `[F1]`.
- [ ] **Hybrid call**: 5 light summaries + 1 optional notes `[F2]`.
- [ ] **Token budgeting** incl. reasoning tokens `[F3]`; **robust JSON parsing** `[F4]`.
- [ ] **Circuit breaker + per-user/global quotas**, Postgres-authoritative `[F5]` *(critical)*.
- [ ] **Prompt-injection defense** — wrap transcript as DATA, strip invented URLs `[F6]`.
- [ ] **Idempotency key** = `hash(user_id, sha256(transcript), summary_types)`; `INSERT … ON CONFLICT DO NOTHING`.
- **Demo:** `POST /summarize` with a pasted transcript → poll → 5 summaries; hit the cap → clean "daily cap" message.

### M3 — Transcript capture (3–5 days) — *this plan, §4* `[D1–D5]`
- [ ] **Managed API path first** (mobile + desktop): call provider with canonical 11-char video id `[D2]`.
- [ ] **Monthly credit counter** → fall back to paste when quota out.
- [ ] **Provenance + content-binding**: store `source` + `sha256(transcript)`; only `api` populates shared cache `[D4]`.
- [ ] **Empty/invalid floors**: reject empty / too-short / mostly-timestamps before spending quota `[D5]`.
- [ ] **Chrome MV3 extension** (desktop, optional): content script reads captions same-origin → service worker
      POSTs to backend `[D1]`; verify video id matches page (R16), empty body = failure (R4), nonce/origin-check bridge (R35).
- [ ] **Paste fallback** wired as the recovery branch for *every* failure `[D3]`.
- **Demo:** mobile URL → summary; desktop one-click → summary.

### M4 — Frontend pages (3–4 days) — *the rest of the UI* `[A1, A4–A9]`
- [ ] **Landing page** `/` `[A1]`.
- [ ] **Summarize page** `/summarize` — 3 input modes (extension / URL→API / paste) + summary-type picker `[A4]`.
- [ ] **Result page** `/result/[job_id]` — progress + **safe rendering** (`react-markdown` + `rehype-sanitize`) `[A5, A9]`.
- [ ] **Dashboard / history** `/dashboard` `[A6]`.
- [ ] **Bounded polling** with react-query (stop when hidden / on terminal status) `[A7]`.
- [ ] **CSP header** (forbid inline scripts) `[A9]` *(do not skip — stored-XSS guard, R2)*.
- [ ] **PWA + Android share-target** for one-tap mobile capture `[A8]`.
- **Demo:** full happy path in the browser, desktop + phone.

### M5 — Hardening + launch (2–3 days)
- [ ] Rate limits, ownership checks (user can only see own jobs), typed errors.
- [ ] **Sentry** with `send_default_pii=false` + `before_send` scrubber (drop transcripts/tokens/secrets) `[H2]`.
- [ ] Admin endpoints, runbook, DB backups, disk-prune-on-startup `[G5]`.
- [ ] **Privacy policy + sub-processors + erasure/DSAR** `[I2]`, **Terms + DMCA/takedown** `[I3]`, content/minors stance `[I4]`.
- [ ] Confirm Deepgram/ASR + file upload are **disabled** for beta.
- **Demo:** pre-launch punch-list green → send first invites.

> **Dependency order that matters:** M1 auth must exist before M2's per-user quota means anything; M2 engine must
> exist before M3 has somewhere to send transcripts; M3 + M4 can overlap once the `/summarize` contract is fixed.
> Transcript work (this plan) is **M3** — do **not** start it before the engine (M2) is demoable.

---

## Appendix — one-line summary

> The only ways to legally read YouTube captions are **on the user's device inside YouTube's origin** (the
> extension), **via a provider on residential IPs** (the managed API), or **from the user's own paste**. Our
> server can't do it directly because of the datacenter-IP + PO-token wall, and a plain web page can't because of
> CORS. yt-dlp avoids CORS but not the IP wall. Hence: **API primary, extension optional, paste fallback.**
