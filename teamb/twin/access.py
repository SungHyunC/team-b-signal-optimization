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
    return hmac.new(secret.encode("utf-8", "surrogateescape"), b"teamb-live-sumo-session-v1", hashlib.sha256).hexdigest()


def _same(given: str, expected: str) -> bool:
    """Constant-time comparison that also works for non-ASCII text.

    hmac.compare_digest raises TypeError for a str with non-ASCII characters (a Korean
    passphrase, a mangled cookie), which surfaced as HTTP 500. Comparing UTF-8 bytes avoids that;
    surrogateescape keeps undecodable cookie bytes comparable instead of raising.
    """
    return hmac.compare_digest(given.encode("utf-8", "surrogateescape"), expected.encode("utf-8", "surrogateescape"))


def authenticated(cookie: str | None) -> bool:
    secret = configured_secret()
    return not secret or (isinstance(cookie, str) and bool(cookie) and _same(cookie, expected_cookie(secret)))


def valid_password(password: str) -> bool:
    secret = configured_secret()
    return bool(secret and isinstance(password, str) and _same(password, secret))
