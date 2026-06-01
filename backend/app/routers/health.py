"""Liveness and readiness endpoints.

/healthz  -> liveness: the process is up. No external deps, so the M0 demo works
             before Aiven is wired.
/readyz   -> readiness: reports optional Postgres/Valkey status.
"""
from fastapi import APIRouter

from ..config import settings
from ..db import check_database, check_valkey

router = APIRouter(tags=["health"])


def _state(value: bool | None) -> str:
    if value is None:
        return "not_configured"
    return "ok" if value else "error"


@router.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.get("/readyz")
async def readyz() -> dict:
    db = await check_database()
    valkey = await check_valkey()
    # "not_configured" deps don't make us unready at M0; only real errors do.
    ready = db in (True, None) and valkey in (True, None)
    return {
        "status": "ready" if ready else "degraded",
        "checks": {"database": _state(db), "valkey": _state(valkey)},
    }
