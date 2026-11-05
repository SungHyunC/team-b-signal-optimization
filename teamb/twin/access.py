"""Optional password gate for the single-session live SUMO twin.

A hosted demo is a shared simulation, NOT a per-user isolation service.
Set TWIN_ACCESS_TOKEN (long random secret) to require login for both HTTP and WS.
"""
from __future__ import annotations

import hashlib
import hmac
import os

COOKIE = "teamb_cloud_session"


def configured_secret() -> str | None:
    return os.getenv("TWIN_ACCESS_TOKEN") or None


def expected_cookie(secret: str) -> str:
    return hmac.new(secret.encode(), b"teamb-live-sumo-session-v1", hashlib.sha256).hexdigest()


def authenticated(cookie: str | None) -> bool:
    secret = configured_secret()
    return not secret or (bool(cookie) and hmac.compare_digest(cookie, expected_cookie(secret)))


def valid_password(password: str) -> bool:
    secret = configured_secret()
    return bool(secret and hmac.compare_digest(password, secret))
