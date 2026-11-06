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
