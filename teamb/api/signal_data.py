"""Signal-data API for navigation apps (Busan-style sharing of live signal timing).

Owner: Scenarios & analysis (Aditya) — the optional back-end extra from the prototype plan.
The twin server mounts this router; `get_env` returns the live SimEnv or None.
"""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException


def build_router(get_env: Callable[[], object | None]) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["signal data"])

    def _env():
        env = get_env()
        if env is None or getattr(env, "conn", None) is None:
            raise HTTPException(status_code=503, detail="no simulation running")
        return env

    @router.get("/spat")
    def spat():
        """Signal phase and timing for every junction."""
        return _env().spat()

    return router
