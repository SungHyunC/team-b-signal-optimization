"""Digital twin server: REST endpoints, a live session over the WebSocket, commands, pause/step.

Runs a real SUMO session (short and at max speed), so it takes a few seconds.
"""
from __future__ import annotations

import json
import math
import time

import anyio
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from teamb.twin.server import create_app
from teamb.twin.session import SessionConfig, parse_speed, speed_label


# --- helpers ------------------------------------------------------------------------
def recv(ws, timeout: float = 30.0) -> dict:
    """ws.receive_json() with a timeout, so a broken server fails the test instead of hanging it."""
    rx = getattr(ws, "_send_rx", None)  # Starlette's TestClient internals; plain receive if they change
    if rx is None:
        return ws.receive_json()

    async def get():
        with anyio.fail_after(timeout):
            return await rx.receive()

    message = ws.portal.call(get)
    if message["type"] == "websocket.close":
        raise WebSocketDisconnect(message.get("code", 1000))
    return json.loads(message["text"])


def recv_until(ws, predicate, what: str, timeout: float = 45.0, seen: list | None = None) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise AssertionError(f"timed out waiting for {what}")
        msg = recv(ws, left)
        if seen is not None:
            seen.append(msg)
        if predicate(msg):
            return msg


def is_frame(msg, sid=None, t_min=None) -> bool:
    return msg["type"] == "frame" and (sid is None or msg["sid"] == sid) and (t_min is None or msg["t"] >= t_min)


def is_reply(msg, mid) -> bool:
    return msg["type"] == "reply" and msg.get("id") == mid


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("twin")
    reports = tmp / "experiments"
    (reports / "demo").mkdir(parents=True)
    (reports / "demo" / "report.json").write_text(
        # NaN is valid for Python's json but not for browsers: the API must clean it.
        '{"name": "demo", "created": "2026-11-05T09:00:00", "baseline": "fixed_time", "rows": ['
        '{"scenario": "rush_hour", "controller": "fixed_time", "coverage": 1.0, "n_seeds": 3,'
        ' "mean_delay_s": {"mean": 70.1, "ci95": 7.7}, "delta_vs_baseline_pct": {"mean": 0.0, "ci95": NaN}}]}'
    )
    (reports / "broken").mkdir()
    (reports / "broken" / "report.json").write_text("{not json")
    app = create_app(runs_dir=tmp / "runs", results_dir=reports)
    with TestClient(app) as c:
        c.app_tmp = tmp
        yield c


# --- pure helpers -------------------------------------------------------------------------
def test_speed_parsing():
    assert parse_speed("max") == math.inf
    assert parse_speed(0) == math.inf
    assert parse_speed("5x") == 5
    assert parse_speed(2.5) == 2.5
    assert speed_label(math.inf) == "max" and speed_label(10.0) == 10
    for bad in ("fast", -1, None, True):
        with pytest.raises(ValueError):
            parse_speed(bad)


def test_session_config_validation():
    cfg = SessionConfig.from_dict({"scenario": "emergency", "controller": "coordinated", "seed": "3", "speed": "max"})
    assert (cfg.seed, cfg.speed) == (3, "max")
    for bad in ({"controller": "nope"}, {"scenario": "nope"}, {"coverage": 25}, {"colour": "red"}, {"speed": "warp"}):
        with pytest.raises(ValueError):
            SessionConfig.from_dict(bad)


def test_session_config_redacts_secrets():
    cfg = SessionConfig.from_dict({"controller": "ai_recommender",
                                   "controller_params": {"approval_token": "tok-XYZ", "search_at": None, "nested": {"api_key": "k-1"}}})
    shown = json.dumps(cfg.to_dict())
    assert "tok-XYZ" not in shown and "k-1" not in shown
    assert cfg.to_dict()["controller_params"]["approval_token"] == "<redacted>"
    assert cfg.to_dict()["controller_params"]["search_at"] is None
    assert cfg.controller_params["approval_token"] == "tok-XYZ"  # the sim thread still gets the real value


# --- REST -------------------------------------------------------------------------------
def test_meta(client):
    meta = client.get("/api/meta").json()
    assert {"fixed_time", "coordinated"} <= {c["name"] for c in meta["controllers"]}
    assert {"rush_hour", "emergency", "road_closure", "fake_data_attack"} <= {s["name"] for s in meta["scenarios"]}
    closable = {e["id"]: e for e in meta["closable_edges"]}
    assert closable["J2_J3"]["kind"] == "arterial" and closable["N1_N2"]["kind"] == "back"
    assert "W0_J1" not in closable and "J4_E5" not in closable  # entries/exits at dead ends
    assert meta["junctions"] == ["J1", "J2", "J3", "J4"]
    routes = {(r["origin"], r["destination"]) for r in meta["emergency_routes"]}
    assert ("W0_J1", "J4_E5") in routes and len(routes) >= 5
    assert (meta["attack_targets"][0]["junction"], meta["attack_targets"][0]["approach"]) == ("J2", "N")
    assert len(meta["attack_targets"]) == 16 and "max" in meta["speeds"]


def test_geometry(client):
    geo = client.get("/api/geometry").json()
    assert {"bounds", "lanes", "edges", "junctions", "tls"} <= set(geo)
    assert sorted(geo["tls"]) == ["J1", "J2", "J3", "J4"]
    assert set(geo["tls"]["J2"]["approaches"]) == {"W", "E", "N", "S"}
    assert all(len(lane["shape"]) >= 2 and lane["width"] > 0 for lane in geo["lanes"])


def test_web_app_is_served(client):
    page = client.get("/")
    assert page.status_code == 200 and 'type="importmap"' in page.text and "/static/js/main.js" in page.text
    for path in ("/static/js/main.js", "/static/js/vehicles.js", "/static/css/twin.css"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "no-cache"
    three = client.get("/vendor/three/build/three.module.js", follow_redirects=False)
    assert three.status_code in (200, 307)  # local copy, or the pinned CDN
    if three.status_code == 307:
        assert three.headers["location"].startswith("https://cdn.jsdelivr.net/npm/three@0.160.0/")
    # httpx collapses a literal "../" before sending, so send the dots percent-encoded: Starlette
    # decodes them into the path parameter and the handler itself must refuse the traversal.
    for bad in ("/vendor/three/%2e%2e/%2e%2e/%2e%2e/server.py", "/vendor/three/build/%2e%2e/%2e%2e/%2e%2e/server.py"):
        r = client.get(bad, follow_redirects=False)
        assert r.status_code == 404, bad
        assert "location" not in r.headers  # refused, not forwarded to the CDN


def test_results(client):
    reports = client.get("/api/results").json()
    assert [r["name"] for r in reports] == ["demo"]  # the broken report is skipped
    row = reports[0]["rows"][0]
    assert row["mean_delay_s"] == {"mean": 70.1, "ci95": 7.7}
    assert row["delta_vs_baseline_pct"]["ci95"] is None  # NaN cleaned for browsers


def test_idle_until_started(client):
    assert client.get("/api/state").json()["state"] == "idle"
    assert client.get("/api/v1/spat").status_code == 503
    assert client.post("/api/session", json={"controller": "nope"}).status_code == 400
    assert client.post("/api/command", json={"type": "dispatch_ev"}).json()["ok"] is False


# --- a live session ----------------------------------------------------------------------
def test_live_session_over_websocket(client):
    started = client.post(
        "/api/session?wait=1",
        json={"scenario": "rush_hour", "controller": "fixed_time", "seed": 3, "speed": "max", "end_time": 900},
    ).json()
    assert started["ok"], started
    with client.websocket_connect("/ws") as ws:
        hello = recv_until(ws, lambda m: m["type"] == "hello", "hello")
        status = hello["status"]
        sid = status["sid"]
        assert status["state"] == "running" and status["config"]["scenario"] == "rush_hour"
        assert status["end_time"] == 900 and status["warmup"] > 0

        # Frames stream in and follow the SimEnv.frame() contract.
        frame = recv_until(ws, lambda m: is_frame(m, sid, t_min=40), "a frame at t >= 40")
        assert frame["vehicles"] and all(len(v) == 6 for v in frame["vehicles"])
        assert sorted(frame["signals"]) == ["J1", "J2", "J3", "J4"]
        assert set(frame["signals"]["J1"]["colors"]) == {"W", "E", "N", "S"}
        assert {"kpi", "events", "phantoms", "alerts", "closures", "attack", "recommendation", "preempting"} <= set(frame)

        # dispatch_ev: reply with the vehicle id, then the event and the ambulance itself.
        seen: list = []
        ws.send_json({"type": "command", "id": 1, "command": {"type": "dispatch_ev", "origin": "W0_J1", "destination": "J4_E5", "kind": "ambulance"}})
        reply = recv_until(ws, lambda m: is_reply(m, 1), "dispatch reply", seen=seen)
        assert reply["ok"] and reply["result"].startswith("ambulance_")
        ev_id = reply["result"]
        recv_until(ws, lambda m: is_frame(m, sid) and any(v[0] == ev_id and v[5] == "ambulance" for v in m["vehicles"]), "the ambulance on the road", seen=seen)
        events = [e for m in seen if m["type"] == "frame" for e in m["events"]]
        assert any(e["type"] == "ev_dispatched" and e["vehicle"] == ev_id for e in events)

        # Flat command form works too.
        ws.send_json({"type": "command", "id": 2, "cmd": "close_road", "edge": "J2_J3", "cause": "flood"})
        assert recv_until(ws, lambda m: is_reply(m, 2), "close_road reply")["ok"]
        recv_until(ws, lambda m: is_frame(m, sid) and any(c["edge"] == "J2_J3" for c in m["closures"]), "the closure in a frame")

        # Pause: time stops. Step: exactly one second. Play: time moves again.
        ws.send_json({"type": "control", "id": 3, "action": "pause"})
        paused = recv_until(ws, lambda m: is_reply(m, 3), "pause reply")
        assert paused["ok"] and paused["state"] == "paused"
        t0 = client.get("/api/state").json()["t"]
        time.sleep(0.4)
        assert client.get("/api/state").json()["t"] == t0
        assert client.get("/api/v1/spat").json()["junctions"].keys() == {"J1", "J2", "J3", "J4"}
        ws.send_json({"type": "control", "id": 4, "action": "step"})
        stepped = recv_until(ws, lambda m: is_reply(m, 4), "step reply")
        assert stepped["t"] == t0 + 1
        recv_until(ws, lambda m: is_frame(m, sid) and m["t"] == t0 + 1, "the stepped frame")
        ws.send_json({"type": "control", "id": 5, "action": "play", "speed": 20})
        played = recv_until(ws, lambda m: is_reply(m, 5), "play reply")
        assert played["state"] == "running" and played["speed"] == 20
        recv_until(ws, lambda m: is_frame(m, sid, t_min=t0 + 3), "frames after resuming")

        # Commands the controller does not know are answered, not fatal.
        assert client.post("/api/command", json={"type": "approve", "id": "x"}).json()["ok"] is False
        bad = client.post("/api/control", json={"action": "speed", "speed": "warp"})
        assert bad.status_code == 400
        # A malformed control is refused as a whole: the valid speed in it is not applied either.
        ws.send_json({"type": "control", "id": 50, "action": "jump", "t": [1], "speed": 1})
        refused = recv_until(ws, lambda m: is_reply(m, 50), "malformed jump reply")
        assert refused["ok"] is False and "invalid time" in refused["error"]
        assert client.get("/api/state").json()["speed"] == 20

        # Jump ahead: fast-forward, then keep going.
        target = t0 + 80
        ws.send_json({"type": "control", "id": 6, "action": "jump", "t": target})
        assert recv_until(ws, lambda m: is_reply(m, 6), "jump reply")["ok"]
        recv_until(ws, lambda m: is_frame(m, sid, t_min=target), "the jump target")


def test_approval_token_never_reaches_clients(client):
    """twin-security-1: the token is in no reply, status or hello, yet the controller still uses it."""
    secret = "tok-XYZ-approver"
    started = client.post("/api/session?wait=1", json={
        "scenario": "rush_hour", "controller": "ai_recommender", "speed": "max", "end_time": 120, "autoplay": False,
        "controller_params": {"approval_token": secret, "search_at": None},
    })
    assert started.status_code == 200 and started.json()["ok"], started.text
    assert secret not in started.text
    assert secret not in client.get("/api/state").text
    with client.websocket_connect("/ws") as ws:
        hello = recv_until(ws, lambda m: m["type"] == "hello", "hello")
        assert hello["status"]["config"]["controller"] == "ai_recommender"
        assert secret not in json.dumps(hello)
    wrong = client.post("/api/command", json={"type": "approve", "token": "wrong"}).json()
    assert wrong["ok"] is False and "not authorized" in wrong["error"]
    right = client.post("/api/command", json={"type": "approve", "token": secret}).json()
    assert right["ok"] is False and "no recommendation" in right["error"]  # got past the token check


def test_run_finishes_cleanly(client):
    client.post("/api/session?wait=1", json={"scenario": "emergency", "controller": "coordinated", "speed": "max", "end_time": 60})
    deadline = time.monotonic() + 45
    state = {}
    while time.monotonic() < deadline:
        state = client.get("/api/state").json()
        if state["state"] == "finished":
            break
        time.sleep(0.2)
    assert state["state"] == "finished", state
    assert state["summary"]["sim_time_s"] == 60.0
    assert (client.app_tmp / "runs" / state["run_id"] / "summary.json").exists()
    assert client.get("/api/v1/spat").status_code == 503
    reply = client.post("/api/control", json={"action": "play"}).json()
    assert reply["ok"] is False and "finished" in reply["error"]
