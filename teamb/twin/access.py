"""Optional password gate for the single-session live SUMO twin.

A hosted demo is a shared simulation, NOT a per-user isolation service.
Set TWIN_ACCESS_TOKEN (long random secret) to require login for both HTTP and WS.

WebSocket handshakes are also checked for their Origin (in every mode): browsers let any web
page open a WebSocket to http://127.0.0.1:8000, and CORS does not apply to WebSockets. Allowed
are requests without an Origin (scripts, tests), pages served by the twin itself (same host),
and the origins listed in TWIN_ALLOWED_ORIGINS (comma-separated, e.g.
"https://team-b.github.io,http://localhost:5173"; "*" allows every origin).
"""
from __future__ import annotations

import hashlib
import hmac
import os
from urllib.parse import urlsplit

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


_DEFAULT_PORTS = {"http": "80", "https": "443", "ws": "80", "wss": "443"}


def _normalize_origin(origin: str) -> str | None:
    """'HTTPS://Example.org:443' -> 'https://example.org'; None for anything that is not an origin."""
    try:
        parts = urlsplit(origin.strip())
        host, port = parts.hostname, parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS or not host:
        return None
    netloc = host.lower() if port is None or str(port) == _DEFAULT_PORTS[scheme] else f"{host.lower()}:{port}"
    return f"{scheme}://{netloc}"


def allowed_origins() -> set[str]:
    raw = os.getenv("TWIN_ALLOWED_ORIGINS", "")
    out = set()
    for item in raw.split(","):
        item = item.strip()
        if item == "*":
            out.add("*")
        elif item:
            norm = _normalize_origin(item)
            if norm:
                out.add(norm)
    return out


def origin_allowed(origin: str | None, hosts: tuple[str | None, ...]) -> bool:
    """May a WebSocket handshake with this Origin header proceed?

    `hosts` are the Host header (and X-Forwarded-Host behind a proxy) the browser connected to.
    Page JavaScript cannot set these headers on a WebSocket, so a match means the page was served
    by this server.
    """
    if origin is None:
        return True  # not a browser (scripts, curl, tests)
    allowed = allowed_origins()
    if "*" in allowed:
        return True
    norm = _normalize_origin(origin)
    if norm is None:  # "null" (file://, sandboxed iframes) or garbage
        return False
    if norm in allowed:
        return True
    scheme, _, netloc = norm.partition("://")
    for host in hosts:
        for candidate in (host or "").split(","):
            candidate = candidate.strip().lower()
            if candidate and _normalize_origin(f"{scheme}://{candidate}") == norm:
                return True
    return False
