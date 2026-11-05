"""Cloud access gate and hosted sandbox contract; no SUMO processes needed."""
from urllib.parse import urlparse, parse_qs

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
