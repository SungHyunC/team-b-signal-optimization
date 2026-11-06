"""FastAPI server for the digital twin.

    python -m teamb twin --port 8000            # then open http://127.0.0.1:8000

HTTP
    GET  /                 the 3D web app (teamb/twin/static)
    GET  /api/meta         controllers, scenarios, closable roads, EV routes, attack targets
    GET  /api/geometry     network geometry (works without a running simulation)
    GET  /api/state        session status (state, config, speed, t, ...)
    POST /api/session      (re)start the simulation; body = SessionConfig fields, ?wait=1 waits for SUMO
    POST /api/control      {"action": "play"|"pause"|"step"|"reset"|"speed"|"jump", "speed": 5, "t": 1200}
    POST /api/command      a SimEnv command, e.g. {"type": "dispatch_ev", "origin": "W0_J1", "destination": "J4_E5"}
    GET  /api/results      experiment reports (results/experiments/*/report.json)
    GET  /api/sandbox/schema  allowed scenarios, controllers and limits of the Scenario Sandbox JSON
    GET  /api/v1/...       signal data for navigation apps (teamb/api/signal_data.py)

WebSocket /ws
    server -> client  {"type": "hello", "status", "events", "kpi_history"}   once, on connect
                      {"type": "frame", "sid", ...SimEnv.frame()}           up to 12 per second
                      {"type": "status", "state", "speed", ...}             when something changes
                      {"type": "reply", "id", "ok", ...}                    answer to a client message
    client -> server  {"type": "control", "id": 1, "action": "pause", "speed": 5}
                      {"type": "command", "id": 2, "command": {"type": "dispatch_ev", ...}}
                      (also accepted: {"type": "command", "cmd": "dispatch_ev", "origin": ...})
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import re
import html
import os
from urllib.parse import quote
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Form, Request
from fastapi.responses import FileResponse, RedirectResponse, Response, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from teamb import config
from teamb import sandbox as sandbox_contract
from teamb.twin import meta, access
from teamb.twin.session import (
    CALL_TIMEOUT_S, Client, Hub, SessionBusy, SessionConfig, TwinSession, dumps, parse_control,
)

log = logging.getLogger("teamb.twin")

STATIC_DIR = Path(__file__).resolve().parent / "static"
THREE_VERSION = "0.160.0"  # keep in sync with the importmap in static/index.html
THREE_CDN = f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/"
VENDOR_DIR = STATIC_DIR / "vendor" / f"three@{THREE_VERSION}"  # optional offline copy (python -m teamb.twin.vendor)
# A relative path below VENDOR_DIR: no leading "/" (pathlib would make it absolute), no "..".
_VENDOR_PATH = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_./-]*")
MAX_WS_INFLIGHT = 16  # unanswered requests per WebSocket; more get a "busy" reply instead of a task


def vendor_file(path: str, base: Path | None = None) -> Path | None:
    """Where /vendor/three/<path> may be served from, or None if the path must be refused.

    The path must be relative and stay inside the vendor folder even after symlinks are
    resolved; otherwise ``VENDOR_DIR / "/etc/passwd"`` would serve any file the server can read.
    """
    if not _VENDOR_PATH.fullmatch(path) or ".." in path:
        return None
    base = (base or VENDOR_DIR).resolve()
    local = (base / path).resolve()
    if not local.is_relative_to(base):
        return None
    return local


class Superseded(Exception):
    """The queued request was cancelled before it ran (a newer restart replaced it)."""


async def await_future(fut, timeout: float):
    """Wait for a sim-thread future. Superseded if a newer restart cancelled it while it was
    queued (session.Request.superseded); the waiter's own cancellation stays a CancelledError."""
    try:
        return await asyncio.wait_for(asyncio.wrap_future(fut), timeout)
    except asyncio.CancelledError:
        if fut.cancelled() and getattr(fut, "superseded", False) and not _cancelling(asyncio.current_task()):
            raise Superseded("superseded by a newer restart request") from None
        raise


def _cancelling(task) -> bool:
    """Whether `task` itself is being cancelled. Task.cancelling() is new in 3.11; on 3.10 the
    request's superseded flag alone decides."""
    cancelling = getattr(task, "cancelling", None)
    return bool(cancelling and cancelling())


def create_app(*, runs_dir: str | Path | None = None, results_dir: str | Path | None = None) -> FastAPI:
    """Build the app. Nothing heavy happens until the lifespan starts (no SUMO, no threads)."""
    hub = Hub()
    session = TwinSession(hub, runs_dir=runs_dir)
    reports_dir = Path(results_dir) if results_dir else config.RESULTS / "experiments"

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        await asyncio.to_thread(meta.geometry)  # builds the network on first use (netconvert)
        hub.bind(asyncio.get_running_loop())
        session.start_thread()
        try:
            yield
        finally:
            await asyncio.to_thread(session.shutdown)

    app = FastAPI(title="Team B Signal Twin", version="1.0", lifespan=lifespan)
    app.state.session = session
    app.state.hub = hub

    async def wait_for(fut, timeout: float = CALL_TIMEOUT_S) -> dict:
        try:
            result = await await_future(fut, timeout)
        except asyncio.TimeoutError:
            raise HTTPException(504, "timed out waiting for the simulation thread") from None
        except Superseded as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:  # bad parameters, e.g. an invalid speed
            raise HTTPException(400, str(exc)) from None
        return result if isinstance(result, dict) else {"ok": True, "result": result}

    @app.exception_handler(SessionBusy)
    async def session_busy(request: Request, exc: SessionBusy):
        return JSONResponse({"detail": str(exc)}, status_code=503, headers={"Retry-After": "2"})

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        # If the sim thread died, every request would queue forever: report it so the platform
        # (Render's health check) restarts the instance.
        if session.thread_alive() is False:
            return JSONResponse({"ok": False, "service": "team-b-live-sumo", "error": "simulation thread stopped"},
                                status_code=503)
        return {"ok": True, "service": "team-b-live-sumo"}

    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        next_path = request.query_params.get("next", "/")
        if not next_path.startswith("/") or next_path.startswith("//") or "\\\\" in next_path:
            next_path = "/"
        if not access.configured_secret():
            return RedirectResponse("/", status_code=303)
        page = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Team B · Live SUMO</title>
<style>body{background:#0c1727;color:#e9f2ff;font:16px system-ui;max-width:420px;margin:12vh auto;padding:24px}
input,button{font:inherit;padding:12px;border-radius:8px;width:100%;box-sizing:border-box;margin:10px 0}
button{background:#215b90;color:white;border:0;cursor:pointer}small{color:#acbdd5}</style></head><body>
<h1>Live SUMO Sandbox</h1><p>Access-controlled, shared research simulator</p>
<form method="post" action="/login"><input type="hidden" name="next_path" value="__SAFE_NEXT__"><label>Access password<input name="password" type="password" required autocomplete="current-password"></label>
<button type="submit">Enter live sandbox</button></form><small>This is a shared research instance; only approved testers should enter.</small>
</body></html>"""
        return HTMLResponse(page.replace("__SAFE_NEXT__", html.escape(next_path, quote=True)))

    @app.post("/login", include_in_schema=False)
    async def login_submit(password: str = Form(...), next_path: str = Form("/")):
        if not access.valid_password(password):
            return HTMLResponse("<h1>Incorrect access password</h1><a href='/login'>Try again</a>", status_code=401)
        if not next_path.startswith("/") or next_path.startswith("//") or "\\\\" in next_path:
            next_path = "/"
        response = RedirectResponse(next_path, status_code=303)
        # Lax, not Strict: the GitHub Pages sandbox (and shared links) open the twin with a
        # cross-site top-level navigation, which Strict would answer with a fresh login every time.
        # Lax still keeps the cookie off cross-site POSTs, fetches and WebSocket handshakes, and
        # every state-changing endpoint here is a POST or the WebSocket.
        response.set_cookie(
            access.COOKIE, access.expected_cookie(access.configured_secret()),
            httponly=True, secure=os.getenv("TWIN_COOKIE_INSECURE") != "1",
            samesite="lax", max_age=60 * 60 * 12, path="/",
        )
        return response

    @app.middleware("http")
    async def cloud_access_gate(request, call_next):
        if request.url.path in ("/healthz", "/login") or access.authenticated(request.cookies.get(access.COOKIE)):
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "login required"}, status_code=401)
        next_path = request.url.path + ("?" + request.url.query if request.url.query else "")
        return RedirectResponse("/login?next=" + quote(next_path, safe=""), status_code=303)

    @app.middleware("http")
    async def no_stale_frontend(request, call_next):
        # Teammates edit the JS/CSS while the server runs: always revalidate (cheap 304s).
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # --- web app ---------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/vendor/three/{path:path}", include_in_schema=False)
    def vendor_three(path: str):
        """three.js for the importmap: a local copy if one was downloaded, else the pinned CDN."""
        local = vendor_file(path)
        if local is None:
            raise HTTPException(404)
        # A copy the server cannot read (vendored by another user) would fail mid-response: use the CDN.
        if local.is_file() and os.access(local, os.R_OK):
            return FileResponse(local, media_type="text/javascript")
        return RedirectResponse(THREE_CDN + path, status_code=307)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # --- REST API ----------------------------------------------------------------
    @app.get("/api/meta")
    def get_meta():
        return meta.build_meta()

    @app.get("/api/geometry")
    def get_geometry():
        return Response(meta.geometry_json(), media_type="application/json")

    @app.get("/api/state")
    def get_state():
        return session.status()

    @app.post("/api/session")
    async def post_session(body: dict = Body(default_factory=dict), wait: bool = False):
        try:
            cfg = SessionConfig.from_dict(body)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from None
        if access.configured_secret():
            # Guard expensive hosted simulations against accidental unbounded inputs.
            if type(cfg.seed) is not int or not 0 <= cfg.seed <= 2_147_483_647:
                raise HTTPException(400, "seed must be a nonnegative 32-bit integer")
            if cfg.end_time is not None and (not math.isfinite(cfg.end_time) or not 60 <= cfg.end_time <= 10800):
                raise HTTPException(400, "end_time must be 60–10800 simulated seconds")
            if not set(cfg.scenario_params) <= {"demand_scale"}:
                raise HTTPException(400, "hosted sandbox supports demand_scale scenario override only")
            scale = cfg.scenario_params.get("demand_scale", 1.0)
            if type(scale) not in (int, float) or not math.isfinite(scale) or not 0.1 <= scale <= 3:
                raise HTTPException(400, "demand_scale must be between 0.1 and 3")
            if cfg.start_at > 10800:
                raise HTTPException(400, "start_at exceeds hosted run limit")
            if cfg.controller_params:
                raise HTTPException(400, "custom controller parameters are not available on the shared hosted sandbox")
        fut = session.restart(cfg)
        if wait:  # scripts and tests: block until SUMO is up
            result = await wait_for(fut, timeout=120)
            return {**result, "config": cfg.to_dict()}
        return {"ok": True, "state": "loading", "config": cfg.to_dict()}

    @app.post("/api/control")
    async def post_control(body: dict = Body(...)):
        try:
            parse_control(body.get("action"), body.get("speed"), body.get("t"))  # 400 before queueing
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return await wait_for(session.control(body.get("action"), body.get("speed"), body.get("t")), timeout=120)

    @app.post("/api/command")
    async def post_command(body: dict = Body(...)):
        if not isinstance(body.get("type"), str):
            raise HTTPException(400, "a command needs a 'type', e.g. 'dispatch_ev'")
        return await wait_for(session.command(body))

    @app.get("/api/results")
    def get_results():
        return meta.list_reports(reports_dir)

    @app.get("/api/sandbox/schema")
    def get_sandbox_schema():
        """The Scenario Sandbox contract (teamb/sandbox.py): what the builder may export."""
        return sandbox_contract.schema()

    # --- signal data for navigation apps (owned by teamb/api) ---------------------------
    try:
        from teamb.api.signal_data import build_router

        app.include_router(build_router(session.get_env))
    except Exception:  # the twin must still start if that module is mid-edit
        log.exception("could not mount the signal-data API (teamb.api.signal_data)")

    # --- WebSocket ------------------------------------------------------------------
    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        if not access.origin_allowed(ws.headers.get("origin"), (ws.headers.get("host"), ws.headers.get("x-forwarded-host"))):
            # Another website trying to drive this twin from a visitor's browser (no CORS for WebSockets).
            await ws.close(code=1008, reason="origin not allowed")
            return
        if not access.authenticated(ws.cookies.get(access.COOKIE)):
            await ws.close(code=1008, reason="login required")
            return
        await ws.accept()
        client = Client(ws)
        hub.add(client)
        client.offer(dumps(session.hello()), droppable=False)
        if session.last_frame_text:
            client.offer(session.last_frame_text, droppable=True)
        pump = asyncio.create_task(_pump(client))
        tasks: set[asyncio.Task] = set()
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                text = message.get("text")
                if text is None:  # a binary frame: answer it instead of crashing the handler (KeyError)
                    client.offer(dumps({"type": "reply", "id": None, "ok": False,
                                        "error": "binary frames are not supported; send JSON text"}), droppable=False)
                    continue
                if len(tasks) >= MAX_WS_INFLIGHT:
                    client.offer(dumps({"type": "reply", "id": _message_id(text), "ok": False,
                                        "error": "busy: too many requests in flight on this connection"}), droppable=False)
                    continue
                task = asyncio.create_task(_handle(client, text))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.remove(client)
            pump.cancel()
            for task in tasks:
                task.cancel()

    async def _pump(client: Client) -> None:
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await client.pump()

    async def _handle(client: Client, text: str) -> None:
        import json

        try:
            msg = json.loads(text)
            if not isinstance(msg, dict):
                raise ValueError("expected a JSON object")
        except ValueError as exc:
            client.offer(dumps({"type": "reply", "id": None, "ok": False, "error": f"bad message: {exc}"}), droppable=False)
            return
        kind = msg.get("type")
        try:
            if kind == "control":
                fut = session.control(msg.get("action"), msg.get("speed"), msg.get("t"))
            elif kind == "command":
                command = msg.get("command")
                if command is None:  # flat form: {"type": "command", "cmd": "dispatch_ev", ...params}
                    command = {k: v for k, v in msg.items() if k not in ("type", "id", "cmd")}
                    command["type"] = msg.get("cmd")
                if not isinstance(command, dict) or not isinstance(command.get("type"), str):
                    raise ValueError("a command needs a 'type', e.g. {'type': 'dispatch_ev', ...}")
                fut = session.command(command)
            elif kind == "ping":
                fut = None
            else:
                raise ValueError(f"unknown message type '{kind}' (expected 'control' or 'command')")
            result = {"ok": True} if fut is None else await await_future(fut, 120)
        except asyncio.TimeoutError:
            result = {"ok": False, "error": "timed out waiting for the simulation thread"}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        if not isinstance(result, dict):
            result = {"ok": True, "result": result}
        client.offer(dumps({**result, "type": "reply", "id": msg.get("id"), "request": kind}), droppable=False)

    return app


def _message_id(text: str):
    """The "id" of a client message, for a reply to a message that is not processed."""
    import json

    try:
        msg = json.loads(text)
    except ValueError:
        return None
    return msg.get("id") if isinstance(msg, dict) else None


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Entry point for `python -m teamb twin`."""
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(f"\n  Team B signal twin  ->  http://{host}:{port}\n", flush=True)
    uvicorn.run(create_app(), host=host, port=port, log_level="info", access_log=False)


app = create_app()  # for `uvicorn teamb.twin.server:app --reload` while working on the frontend

if __name__ == "__main__":
    main()
