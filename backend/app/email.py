"""Transactional email (B6).

No provider configured -> log the message (handy for local dev: the invite /
reset link shows up in the server log). Set RESEND_API_KEY to send for real.
"""
from __future__ import annotations

import logging

import httpx

from .config import settings

logger = logging.getLogger("app.email")


async def send_email(to: str, subject: str, body: str) -> None:
    if settings.resend_api_key:
        await _send_via_resend(to, subject, body)
    else:
        # Dev-only path (production requires RESEND_API_KEY). print() so the link
        # is visible in the server console regardless of logging configuration.
        message = (
            f"\n--- EMAIL (console; no RESEND_API_KEY) ---\n"
            f"To: {to}\nSubject: {subject}\n\n{body}\n"
            f"------------------------------------------"
        )
        print(message, flush=True)
        logger.info(message)


async def _send_via_resend(to: str, subject: str, body: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "text": body,
            },
        )
        resp.raise_for_status()
