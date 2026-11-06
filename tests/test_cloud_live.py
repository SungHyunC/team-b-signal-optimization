"""Cloud access gate and hosted sandbox contract; no SUMO processes needed."""
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest

from teamb.twin import access
from teamb.twin.server import create_app


def test_cloud_requires_login_for_http_and_websocket(monkeypatch):
    monkeypatch.setenv("TWIN_ACCESS_TOKEN", "test-only-long-secret")
    client = TestClient(create_app(), base_url="https://testserver")
    assert client.get("/healthz").json()["ok"] is True
    resp = client.get("/static/sandbox.html", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login?next=")
    assert client.get("/api/state").status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws"):
            pass


def test_cloud_login_preserves_requested_experiment(monkeypatch):
    monkeypatch.setenv("TWIN_ACCESS_TOKEN", "test-only-long-secret")
    client = TestClient(create_app(), base_url="https://testserver")
    target = "/?scenario=road_closure&controller=max_pressure&demand=1.25&seed=33"
    resp = client.get(target, follow_redirects=False)
    page = client.get(resp.headers["location"])
    assert "name=\"next_path\"" in page.text
    assert "road_closure" in page.text
    bad = client.post("/login", data={"password": "wrong"}, follow_redirects=False)
    assert bad.status_code == 401
    good = client.post("/login", data={"password": "test-only-long-secret", "next_path": target}, follow_redirects=False)
    assert good.status_code == 303 and good.headers["location"] == target
    assert good.cookies.get(access.COOKIE)
    assert client.get("/static/sandbox.html").status_code == 200
    assert client.get("/api/state").status_code == 200


def test_open_local_development_works_without_token(monkeypatch):
    monkeypatch.delenv("TWIN_ACCESS_TOKEN", raising=False)
    client = TestClient(create_app())
    assert client.get("/static/sandbox.html").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_no_external_open_redirect(monkeypatch):
    monkeypatch.setenv("TWIN_ACCESS_TOKEN", "test-only-long-secret")
    client = TestClient(create_app(), base_url="https://testserver")
    r = client.post("/login", data={"password": "test-only-long-secret", "next_path": "//evil.test"}, follow_redirects=False)
    assert r.headers["location"] == "/"


# --- /vendor/three: only files inside the vendor folder (ext-157) ------------------------
@pytest.fixture
def open_client(monkeypatch):
    """Local mode (no access token): the gate is open, so the handlers themselves must be safe."""
    monkeypatch.delenv("TWIN_ACCESS_TOKEN", raising=False)
    return TestClient(create_app())


def test_vendor_refuses_absolute_paths(open_client, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT")
    absolute = str(secret)  # starts with "/", so the URL has a double slash
    for url in (
        "/vendor/three/" + absolute,
        "/vendor/three/%2F" + absolute.lstrip("/"),  # %2F is decoded into the path parameter
        "/vendor/three//etc/hosts",
        "/vendor/three/%2Fetc/hosts",
        "/vendor/three/%2e%2e/%2e%2e/server.py",
    ):
        r = open_client.get(url, follow_redirects=False)
        assert r.status_code == 404, url
        assert "TOP-SECRET-CONTENT" not in r.text
        assert "location" not in r.headers, url


def test_vendor_serves_local_copy_and_falls_back_to_cdn(open_client, tmp_path, monkeypatch):
    from teamb.twin import server

    vendor = tmp_path / "vendor"
    (vendor / "build").mkdir(parents=True)
    (vendor / "build" / "three.module.js").write_text("export const REVISION = '160';")
    outside = tmp_path / "outside.js"
    outside.write_text("OUTSIDE-THE-VENDOR-DIR")
    (vendor / "escape.js").symlink_to(outside)
    monkeypatch.setattr(server, "VENDOR_DIR", vendor)

    local = open_client.get("/vendor/three/build/three.module.js", follow_redirects=False)
    assert local.status_code == 200 and "REVISION" in local.text
    cdn = open_client.get("/vendor/three/examples/jsm/controls/OrbitControls.js", follow_redirects=False)
    assert cdn.status_code == 307
    assert cdn.headers["location"] == server.THREE_CDN + "examples/jsm/controls/OrbitControls.js"
    escaped = open_client.get("/vendor/three/escape.js", follow_redirects=False)
    assert escaped.status_code == 404 and "OUTSIDE" not in escaped.text


def test_vendor_file_guard_unit(tmp_path):
    from teamb.twin.server import vendor_file

    assert vendor_file("build/three.module.js", tmp_path) == (tmp_path / "build" / "three.module.js").resolve()
    for bad in ("/etc/passwd", "../server.py", "build/../../x.js", "a b.js", "", ".hidden/../../x", "build\\x.js"):
        assert vendor_file(bad, tmp_path) is None, bad


# --- non-ASCII passwords and cookies (twin-security-4, ext-155) ---------------------------
def test_non_ascii_secret_password_and_cookie(monkeypatch):
    monkeypatch.setenv("TWIN_ACCESS_TOKEN", "비밀번호-long-secret")
    assert access.valid_password("비밀번호-long-secret") is True
    assert access.valid_password("ä") is False
    assert access.authenticated("ä") is False
    assert access.authenticated(access.expected_cookie("비밀번호-long-secret")) is True
    client = TestClient(create_app(), base_url="https://testserver")
    assert client.post("/login", data={"password": "é"}, follow_redirects=False).status_code == 401
    good = client.post("/login", data={"password": "비밀번호-long-secret"}, follow_redirects=False)
    assert good.status_code == 303 and good.cookies.get(access.COOKIE)
    # A raw non-ASCII cookie (Starlette decodes cookies as latin-1) is just "not logged in".
    fresh = TestClient(create_app(), base_url="https://testserver")
    raw = [(b"cookie", f"{access.COOKIE}=é".encode("utf-8"))]
    r = fresh.get("/api/state", headers=raw)
    assert r.status_code == 401


def test_ascii_secret_rejects_non_ascii_password(monkeypatch):
    monkeypatch.setenv("TWIN_ACCESS_TOKEN", "test-only-long-secret")
    client = TestClient(create_app(), base_url="https://testserver")
    assert client.post("/login", data={"password": "pässword"}, follow_redirects=False).status_code == 401


# --- malformed bodies are 400, not 500 (twin-security-5, ext-160) ---------------------------
# Rejected before anything is queued, so no sim thread (lifespan) is needed here.
@pytest.mark.parametrize("body", [
    {"action": 5}, {"action": True}, {"action": ["play"]},
    {"action": "jump", "t": []}, {"action": "jump", "t": {"a": 1}}, {"action": "jump", "t": True},
    {"action": "jump", "t": "soon"}, {"action": "jump", "t": "Infinity"}, {"action": "speed", "speed": [1]},
])
def test_malformed_control_is_400(open_client, body):
    r = open_client.post("/api/control", json=body)
    assert r.status_code == 400, (body, r.status_code, r.text)


@pytest.mark.parametrize("raw", [
    '{"seed": Infinity}', '{"seed": 1e400}', '{"seed": [1]}', '{"end_time": NaN}', '{"end_time": Infinity}',
    '{"start_at": Infinity}', '{"coverage": "lots"}',
])
def test_malformed_session_is_400(open_client, raw):
    r = open_client.post("/api/session", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 400, (raw, r.status_code, r.text)


def test_parse_control_unit():
    from teamb.twin.session import parse_control

    assert parse_control(None) == ("speed", None, None)
    assert parse_control(" Jump ", None, "120") == ("jump", None, 120.0)
    assert parse_control("jump", 5, -3) == ("jump", 5.0, 0.0)
    assert parse_control("play", "max")[1] == float("inf")
    for bad in ((5,), ("jump", None, []), ("jump", None, float("nan")), ("speed", "warp")):
        with pytest.raises(ValueError):
            parse_control(*bad)


# --- WebSocket robustness (twin-security-6) ----------------------------------------------
def test_binary_websocket_frame_gets_an_error_reply(open_client):
    with open_client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        ws.send_bytes(b"\x00binary")
        reply = ws.receive_json()
        assert reply["type"] == "reply" and reply["ok"] is False and "binary" in reply["error"]
        ws.send_text('{"type": "ping", "id": 7}')  # the connection is still usable
        pong = ws.receive_json()
        assert pong["type"] == "reply" and pong["id"] == 7 and pong["ok"] is True


# --- WebSocket Origin check (twin-security-8) ----------------------------------------------
def _ws_hello(client, **headers):
    with client.websocket_connect("/ws", headers=headers) as ws:
        return ws.receive_json()["type"]


def test_websocket_rejects_foreign_origin_without_token(open_client):
    with pytest.raises(WebSocketDisconnect) as exc:
        _ws_hello(open_client, origin="https://evil.example")
    assert exc.value.code == 1008
    with pytest.raises(WebSocketDisconnect):
        _ws_hello(open_client, origin="null")  # file:// pages and sandboxed iframes
    assert _ws_hello(open_client, origin="http://testserver") == "hello"  # the twin's own pages
    assert _ws_hello(open_client) == "hello"  # scripts send no Origin


def test_websocket_origin_behind_proxy_and_allow_list(open_client, monkeypatch):
    # A proxy (Render) may forward the public host separately.
    assert _ws_hello(open_client, origin="https://twin.example.org",
                     **{"x-forwarded-host": "twin.example.org"}) == "hello"
    monkeypatch.setenv("TWIN_ALLOWED_ORIGINS", "https://team-b.github.io, http://localhost:5173")
    assert _ws_hello(open_client, origin="https://team-b.github.io") == "hello"
    assert _ws_hello(open_client, origin="http://localhost:5173") == "hello"
    with pytest.raises(WebSocketDisconnect):
        _ws_hello(open_client, origin="https://evil.example")


def test_origin_allowed_unit(monkeypatch):
    monkeypatch.delenv("TWIN_ALLOWED_ORIGINS", raising=False)
    ok = access.origin_allowed
    assert ok(None, ("anything",))
    assert ok("http://127.0.0.1:8000", ("127.0.0.1:8000",))
    assert ok("https://Twin.Example.org", ("twin.example.org:443",))
    assert not ok("http://127.0.0.1:9999", ("127.0.0.1:8000",))
    assert not ok("http://localhost:8000", ("127.0.0.1:8000",))
    assert not ok("https://evil.example", ("127.0.0.1:8000", None))
    assert not ok("not a url", ("127.0.0.1:8000",))
    monkeypatch.setenv("TWIN_ALLOWED_ORIGINS", "*")
    assert ok("https://evil.example", ("127.0.0.1:8000",))


# --- login cookie (twin-security-10) ---------------------------------------------------------
def test_login_cookie_is_lax_httponly_and_secure(monkeypatch):
    monkeypatch.setenv("TWIN_ACCESS_TOKEN", "test-only-long-secret")
    client = TestClient(create_app(), base_url="https://testserver")
    good = client.post("/login", data={"password": "test-only-long-secret"}, follow_redirects=False)
    cookie = good.headers["set-cookie"].lower()
    assert "samesite=lax" in cookie and "httponly" in cookie and "secure" in cookie
    # Lax sends the cookie on cross-site GET navigations, so no GET may change the simulation.
    for path in ("/api/session", "/api/control", "/api/command"):
        assert client.get(path).status_code == 405, path
