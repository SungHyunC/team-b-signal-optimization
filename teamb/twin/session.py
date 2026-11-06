"""The one live simulation behind the digital twin.

Why a dedicated thread
----------------------
TraCI is a single TCP connection with a strict request/response protocol. If two threads
talk to it at the same time the replies get mixed up and the run dies. So every call that may
touch TraCI (env.start / step / frame / handle_command / close) runs on ONE "sim thread" owned
by TwinSession. Web handlers never touch the env: they `submit()` a function and get a
concurrent.futures.Future back, and the sim thread runs it between two steps.

Pacing
------
`speed` is simulated seconds per wall-clock second (1, 2, 5, 10, 20 or "max"). In paced mode
the thread steps whenever a step is due; at "max" (and while fast-forwarding) it steps as fast
as SUMO allows. Frames go out at most `fps` times per wall second, so at high speed one frame
covers several steps. The browser interpolates between frames, so 1x still looks smooth.

Broadcasting
------------
A frame is serialized once on the sim thread and handed to the asyncio loop with
call_soon_threadsafe (Hub). A slow browser only ever gets the newest frame (older unsent frames
are dropped), but status messages and command replies are never dropped.

`env.frame()` drains the env's event list, so it is called in exactly one place
(`_publish_frame`); the session keeps the drained events for browsers that connect later.
"""
from __future__ import annotations

import asyncio
import collections
import concurrent.futures
import json
import logging
import math
import queue
import threading
import time
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, Callable

from teamb import config

log = logging.getLogger("teamb.twin")

FPS = 12  # max frames per wall second sent to browsers
STATUS_EVERY_S = 2.0  # refresh the status message (clients, step time) this often while running
EVENT_HISTORY = 300  # events kept for browsers that connect later
KPI_HISTORY = 720  # KPI samples (one per 5 sim-s, so one hour) for the sparklines
KPI_KEYS = ("t", "vehicles", "arrived", "halting", "mean_speed", "mean_delay", "current_mean_delay")
SPEEDS = (1, 2, 5, 10, 20, "max")
CALL_TIMEOUT_S = 10.0


# --- small helpers -------------------------------------------------------------
def parse_speed(value) -> float:
    """1, 2.5, "5", "5x", "max" -> float. "max" (or 0 / inf) means as fast as SUMO can go."""
    if value is None or isinstance(value, bool):
        raise ValueError(f"invalid speed {value!r}")
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("max", "inf", "fastest"):
            return math.inf
        if text.endswith(("x", "×")):  # "5x"
            text = text[:-1].strip()
        value = text
    try:
        speed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid speed {value!r} (use a number of sim seconds per second, or 'max')") from None
    if math.isnan(speed) or speed < 0:
        raise ValueError(f"invalid speed {value!r}")
    if speed == 0 or math.isinf(speed):
        return math.inf
    return min(speed, 1000.0)


def speed_label(speed: float):
    """Inverse of parse_speed for JSON: inf -> "max", 2.0 -> 2."""
    if math.isinf(speed):
        return "max"
    return int(speed) if float(speed).is_integer() else speed


def jsonable(obj):
    """Make an object safe for browsers' JSON.parse: NaN/inf -> None, numpy -> python, sets -> lists."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset, collections.deque)):
        return [jsonable(v) for v in obj]
    if is_dataclass(obj) and not isinstance(obj, type):
        return jsonable(asdict(obj))
    if hasattr(obj, "tolist"):  # numpy arrays and scalars
        try:
            return jsonable(obj.tolist())
        except Exception:
            pass
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def dumps(obj) -> str:
    """Fast path: plain json.dumps. Slow path only when something needs cleaning (NaN, numpy...)."""
    try:
        return json.dumps(obj, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return json.dumps(jsonable(obj), separators=(",", ":"), allow_nan=False)


SECRET_PARAM_KEYS = frozenset(("approval_token", "token", "password", "secret", "api_key"))
REDACTED = "<redacted>"


def is_secret_key(key) -> bool:
    """Controller parameters that must never reach a browser (status, replies, hello)."""
    k = str(key).lower()
    return k in SECRET_PARAM_KEYS or k.endswith(("_token", "_secret", "_password"))


def redact_secrets(value):
    """A copy of `value` with every secret-looking key's value replaced by "<redacted>"."""
    if isinstance(value, dict):
        return {k: (REDACTED if is_secret_key(k) and v is not None else redact_secrets(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    return value


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


# --- session configuration --------------------------------------------------------
@dataclass
class SessionConfig:
    """What POST /api/session accepts. Everything has a default."""

    scenario: str = "rush_hour"
    controller: str = "fixed_time"
    seed: int = 1
    coverage: float | None = None  # share of vehicles whose navigation app reports (0-1]; None = scenario default
    ev_preemption: bool = True
    sampling: str = "uniform"
    end_time: float | None = None  # None = the scenario's duration
    controller_params: dict = field(default_factory=dict)
    scenario_params: dict = field(default_factory=dict)
    speed: float | str = 2  # sim seconds per wall second, or "max"
    autoplay: bool = True
    start_at: float = 0.0  # fast-forward to this sim time before showing it at `speed`

    @classmethod
    def from_dict(cls, data: dict | None) -> "SessionConfig":
        from teamb.controllers import REGISTRY as CONTROLLERS
        from teamb.scenarios import REGISTRY as SCENARIOS

        data = dict(data or {})
        unknown = sorted(set(data) - {f.name for f in fields(cls)})
        if unknown:
            raise ValueError(f"unknown session option(s) {unknown}")
        cfg = cls(**data)
        if cfg.scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario '{cfg.scenario}'. Available: {sorted(SCENARIOS)}")
        if cfg.controller not in CONTROLLERS:
            raise ValueError(f"unknown controller '{cfg.controller}'. Available: {sorted(CONTROLLERS)}")
        try:
            cfg.seed = int(cfg.seed)
            cfg.start_at = max(0.0, float(cfg.start_at or 0.0))
            if cfg.coverage is not None:
                cfg.coverage = float(cfg.coverage)
            if cfg.end_time is not None:
                cfg.end_time = float(cfg.end_time)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid session option: {exc}") from None
        if cfg.coverage is not None and not 0.0 < cfg.coverage <= 1.0:
            raise ValueError("coverage must be a share in (0, 1], e.g. 0.25 for 25 %")
        if cfg.end_time is not None and cfg.end_time <= 0:
            raise ValueError("end_time must be positive")
        if not isinstance(cfg.controller_params, dict) or not isinstance(cfg.scenario_params, dict):
            raise ValueError("controller_params and scenario_params must be objects")
        cfg.ev_preemption = _as_bool(cfg.ev_preemption)
        cfg.autoplay = _as_bool(cfg.autoplay)
        cfg.sampling = str(cfg.sampling)
        cfg.speed = speed_label(parse_speed(cfg.speed))
        return cfg

    def to_dict(self) -> dict:
        """JSON for browsers and API replies. Secrets such as the AI recommender's approval_token
        are redacted: the sim thread builds SimEnv from the object itself, never from this dict."""
        d = jsonable(asdict(self))
        d["controller_params"] = redact_secrets(d["controller_params"])
        d["scenario_params"] = redact_secrets(d["scenario_params"])
        return d


# --- fan-out to browsers --------------------------------------------------------
class Client:
    """One WebSocket connection. Only touched from the event-loop thread."""

    def __init__(self, ws):
        self.ws = ws
        self.messages: collections.deque[str] = collections.deque()
        self.frame: str | None = None
        self.wake = asyncio.Event()
        self.closed = False

    def offer(self, text: str, droppable: bool) -> None:
        if droppable:
            self.frame = text  # a newer frame replaces one that was not sent yet
        else:
            self.messages.append(text)
        self.wake.set()

    async def pump(self) -> None:
        """Send queued messages first, then the newest frame, until the socket closes."""
        while not self.closed:
            await self.wake.wait()
            self.wake.clear()
            while self.messages and not self.closed:
                await self.ws.send_text(self.messages.popleft())
            if self.frame is not None and not self.closed:
                text, self.frame = self.frame, None
                await self.ws.send_text(text)


class Hub:
    """Hands messages from the sim thread to every connected browser."""

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: set[Client] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def publish(self, text: str, droppable: bool = False) -> None:
        """Thread-safe. droppable=True for frames (only the newest matters)."""
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._fanout, text, droppable)
        except RuntimeError:  # loop is shutting down
            pass

    def _fanout(self, text: str, droppable: bool) -> None:
        for client in list(self.clients):
            client.offer(text, droppable)

    def add(self, client: Client) -> None:
        self.clients.add(client)

    def remove(self, client: Client) -> None:
        self.clients.discard(client)
        client.closed = True
        client.wake.set()


# --- the session ------------------------------------------------------------------
class TwinSession:
    """Owns the live SimEnv and the sim thread. Public methods are safe to call from any thread."""

    def __init__(self, hub: Hub, runs_dir: str | Path | None = None, fps: int = FPS):
        self.hub = hub
        self.runs_dir = Path(runs_dir) if runs_dir else config.RESULTS / "twin"
        self.fps = fps
        self._requests: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # Everything below is written only by the sim thread; other threads just read it.
        self.env = None
        self.config: SessionConfig | None = None
        self.state = "idle"  # idle | loading | running | paused | finished | error
        # Session id, bumped on every (re)start; frames carry it so browsers can drop stale frames.
        # It starts from the clock so a browser that reconnects to a restarted server sees a new id.
        self.sid = (int(time.time()) % 1_000_000) * 100
        self.speed = parse_speed(SessionConfig.speed)
        self.playing = False
        self.ff_target: float | None = None  # fast-forward target (sim seconds)
        self._play_after_ff = True
        self.message: str | None = None
        self.error: str | None = None
        self.summary: dict | None = None
        self.run_info: dict = {}
        self.events: collections.deque = collections.deque(maxlen=EVENT_HISTORY)
        self.kpi_history: collections.deque = collections.deque(maxlen=KPI_HISTORY)
        self.last_frame_text: str | None = None
        self.last_t = 0.0
        self.step_ms: float | None = None
        self._status: dict = {}
        self._next_step_at = 0.0
        self._last_publish = 0.0
        self._last_status = 0.0
        self._last_kpi_t = None
        self._build_status()

    # --- thread lifecycle -----------------------------------------------------
    def start_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="teamb-sim", daemon=True)
        self._thread.start()

    def shutdown(self, timeout: float = 20.0) -> None:
        """Stop stepping, close SUMO (writes the run outputs) and join the thread."""
        self._stop.set()
        self._requests.put(None)  # wake the thread if it is waiting
        if self._thread:
            self._thread.join(timeout)

    # --- public API (any thread) --------------------------------------------------
    def submit(self, fn: Callable[[], Any]) -> concurrent.futures.Future:
        """Run fn() on the sim thread between two steps."""
        fut: concurrent.futures.Future = concurrent.futures.Future()
        if threading.current_thread() is self._thread:  # already on the sim thread: no queue round trip
            try:
                fut.set_result(fn())
            except Exception as exc:
                fut.set_exception(exc)
            return fut
        self._requests.put((fn, fut))
        return fut

    def call(self, fn: Callable[[], Any], timeout: float = CALL_TIMEOUT_S):
        """Blocking version of submit() for synchronous callers (e.g. FastAPI's thread pool)."""
        return self.submit(fn).result(timeout)

    def restart(self, cfg: SessionConfig) -> concurrent.futures.Future:
        return self.submit(lambda: self._restart(cfg))

    def control(self, action: str, speed=None, t=None) -> concurrent.futures.Future:
        return self.submit(lambda: self._control(action, speed, t))

    def command(self, command: dict) -> concurrent.futures.Future:
        return self.submit(lambda: self._command(command))

    def status(self) -> dict:
        status = dict(self._status)
        status["t"] = self.last_t
        status["clients"] = len(self.hub.clients)
        return status

    def hello(self) -> dict:
        """First message for a browser that just connected: status plus recent history."""
        return {
            "type": "hello",
            "status": self.status(),
            "events": _snapshot(self.events),
            "kpi_history": _snapshot(self.kpi_history),
        }

    def get_env(self):
        """What the signal-data router gets: a sim-thread proxy of the live env, or None."""
        env = self.env
        if env is None or self.state in ("loading", "idle", "finished", "error"):
            return None
        return EnvProxy(self, env)

    # --- the sim thread -----------------------------------------------------------
    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._drain(self._wait_time())
                if self._stop.is_set():
                    break
                if self._stepping():
                    self._advance()
                if self.state == "running" and time.monotonic() - self._last_status > STATUS_EVERY_S:
                    self._publish_status()
        except Exception:  # never expected; keep the server alive and say so
            log.exception("twin sim thread crashed")
            self.state, self.error = "error", "the simulation thread crashed (see server log)"
            self._publish_status()
        finally:
            self._close_env()

    def _stepping(self) -> bool:
        return self.env is not None and self.state != "loading" and (self.playing or self.ff_target is not None)

    def _wait_time(self) -> float:
        """How long to block waiting for requests before the next step is due."""
        if not self._stepping():
            return 0.5
        if self.ff_target is not None or math.isinf(self.speed):
            return 0.0
        return max(0.0, min(0.25, self._next_step_at - time.monotonic()))

    def _drain(self, timeout: float) -> None:
        items = []
        try:
            items.append(self._requests.get(timeout=timeout) if timeout > 0 else self._requests.get_nowait())
            while True:
                items.append(self._requests.get_nowait())
        except queue.Empty:
            pass
        for item in items:
            if item is None:  # shutdown wake-up
                continue
            fn, fut = item
            if not fut.set_running_or_notify_cancel():
                continue
            try:
                fut.set_result(fn())
            except Exception as exc:
                log.exception("twin request failed")
                fut.set_exception(exc)

    def _advance(self) -> None:
        now = time.monotonic()
        if self.ff_target is not None or math.isinf(self.speed):
            # As fast as SUMO goes: one frame per 1/fps time slice, and stay responsive to requests.
            deadline = now + 1.0 / self.fps
            while True:
                if not self._step_once():
                    return  # finished or failed (already published)
                if not self._stepping() or not self._requests.empty() or time.monotonic() >= deadline:
                    break
                if self.ff_target is None and not math.isinf(self.speed):
                    break  # fast-forward just ended: back to paced mode
            self._publish_frame()
            return
        interval = self.env.step_length / self.speed
        if self._next_step_at <= 0 or now - self._next_step_at > 1.0:
            # First step, or SUMO cannot keep up with this speed: don't try to catch up in a burst.
            self._next_step_at = now
        stepped = 0
        while now >= self._next_step_at and stepped < 100:
            if not self._step_once():
                return
            stepped += 1
            self._next_step_at += interval
            if not self._requests.empty() or not self._stepping():
                break
            now = time.monotonic()
        if stepped and time.monotonic() - self._last_publish >= 1.0 / self.fps - 1e-3:
            self._publish_frame()

    def _step_once(self) -> bool:
        """One env.step(). Returns False if the run ended (finished or failed)."""
        env = self.env
        t0 = time.perf_counter()
        try:
            env.step()
        except Exception as exc:
            self._fail("simulation step failed", exc)
            return False
        ms = (time.perf_counter() - t0) * 1000.0
        self.step_ms = ms if self.step_ms is None else 0.9 * self.step_ms + 0.1 * ms
        self.last_t = env.t
        if self.ff_target is not None and env.t >= self.ff_target - 1e-9:
            self.ff_target = None
            self.playing = self._play_after_ff
            self.state = "running" if self.playing else "paused"
            self._next_step_at = 0.0
            self._publish_frame()
            self._publish_status(message=f"Fast-forward done at t = {env.t:.0f} s")
        if env.finished:
            self._finish()
            return False
        return True

    # --- requests (run on the sim thread) ---------------------------------------------
    def _restart(self, cfg: SessionConfig) -> dict:
        from teamb.sim.env import SimEnv

        self._close_env()
        self.sid += 1
        self.config = cfg
        self.state = "loading"
        self.error = self.summary = None
        self.playing, self.ff_target = False, None
        self.events.clear()
        self.kpi_history.clear()
        self._last_kpi_t = None
        self.last_frame_text, self.last_t, self.step_ms = None, 0.0, None
        self.run_info = {}
        self._publish_status(message=f"Starting SUMO: {cfg.scenario} / {cfg.controller} / seed {cfg.seed}")
        try:
            env = SimEnv(
                cfg.scenario,
                cfg.controller,
                seed=cfg.seed,
                coverage=cfg.coverage,
                sampling=cfg.sampling,
                ev_preemption=cfg.ev_preemption,
                controller_params=cfg.controller_params or None,
                scenario_params=cfg.scenario_params or None,
                end_time=cfg.end_time,
                frames=True,
            )
            env.output_dir = self.runs_dir / env.run_id  # keep twin runs apart from experiment runs
            self.env = env  # set before start() so a failed start still gets closed
            env.start()
        except Exception as exc:
            self._fail("could not start the simulation", exc)
            return {"ok": False, "error": self.error}
        self.run_info = {
            "run_id": env.run_id,
            "end_time": env.end_time,
            "warmup": env.scenario.warmup,
            "step_length": env.step_length,
            "output_dir": str(env.output_dir),
            "scenario": jsonable(env.scenario.describe()),
            "controller": jsonable(env.controller.describe()),
        }
        self.speed = parse_speed(cfg.speed)
        self._play_after_ff = cfg.autoplay
        self.ff_target = min(cfg.start_at, env.end_time) if cfg.start_at > env.t else None
        self.playing = cfg.autoplay
        self.state = "running" if (self.playing or self.ff_target is not None) else "paused"
        self._next_step_at = 0.0
        self.last_t = env.t
        self._publish_frame()
        what = f"fast-forwarding to t = {self.ff_target:.0f} s" if self.ff_target is not None else self.state
        self._publish_status(message=f"Simulation ready ({what})")
        return {"ok": True, "sid": self.sid, "run_id": env.run_id}

    def _control(self, action: str | None, speed=None, t=None) -> dict:
        action = (action or "speed").lower()
        if speed is not None:
            self.speed = parse_speed(speed)
            self._next_step_at = 0.0
            if self.config is not None:
                self.config.speed = speed_label(self.speed)
        env = self.env if self.state != "loading" else None
        if action == "reset":
            if self.config is None:
                return {"ok": False, "error": "no session to reset yet"}
            return self._restart(replace(self.config))
        if action == "jump":
            if t is None:
                return {"ok": False, "error": "jump needs a target time 't'"}
            target = max(0.0, float(t))
            if env is None or target < env.t:  # SUMO cannot rewind: restart and fast-forward
                if self.config is None:
                    return {"ok": False, "error": "no session yet"}
                keep_playing = self.playing if env is not None else True
                return self._restart(replace(self.config, start_at=target, autoplay=keep_playing))
            self._play_after_ff = self.playing
            self.ff_target = min(target, env.end_time)
            self.state = "running"
        elif action in ("play", "pause", "step"):
            if env is None:
                hint = " (the run finished: press Reset)" if self.state == "finished" else ""
                return {"ok": False, "error": "no simulation running" + hint}
            if action == "play":
                self.playing, self.state = True, "running"
                self._next_step_at = 0.0
            elif action == "pause":
                self.playing, self.ff_target, self.state = False, None, "paused"
                self._publish_frame()
            else:  # single step: pause, advance one step, show it
                self.playing, self.ff_target, self.state = False, None, "paused"
                if self._step_once():
                    self._publish_frame()
        elif action != "speed":
            return {"ok": False, "error": f"unknown control action '{action}'"}
        self._publish_status()
        return {"ok": True, "state": self.state, "speed": speed_label(self.speed), "t": self.last_t}

    def _command(self, command: dict) -> dict:
        env = self.env
        if env is None or self.state == "loading":
            return {"ok": False, "error": "no simulation running"}
        try:
            reply = env.handle_command(dict(command))
        except Exception as exc:
            log.warning("command %s failed: %s", redact_secrets(command), exc)
            reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(reply, dict):
            reply = {"ok": True, "result": reply}
        if self.env is not None and not self._stepping():
            self._publish_frame()  # paused: show the effect (event, closure, ...) right away
        return jsonable(reply)

    # --- publishing ---------------------------------------------------------------
    def _publish_frame(self) -> None:
        env = self.env
        if env is None or self.state == "loading":
            return
        try:
            frame = env.frame()
        except Exception as exc:
            self._fail("could not read a frame", exc)
            return
        frame["type"] = "frame"
        frame["sid"] = self.sid
        for event in frame.get("events") or ():
            self.events.append(event)
        kpi = frame.get("kpi") or {}
        if kpi and kpi.get("t") != self._last_kpi_t:
            self._last_kpi_t = kpi.get("t")
            self.kpi_history.append({k: kpi.get(k) for k in KPI_KEYS})
        text = dumps(frame)
        self.last_frame_text = text
        self.last_t = frame.get("t", self.last_t)
        self._last_publish = time.monotonic()
        self.hub.publish(text, droppable=True)

    def _publish_status(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        self._build_status()
        self._last_status = time.monotonic()
        self.hub.publish(dumps(self.status()), droppable=False)

    def _build_status(self) -> None:
        self._status = {
            "type": "status",
            "state": self.state,
            "sid": self.sid,
            "config": self.config.to_dict() if self.config else None,
            "speed": speed_label(self.speed),
            "playing": self.playing,
            "fast_forward_to": self.ff_target,
            "message": self.message,
            "error": self.error,
            "summary": self.summary,
            "fps": self.fps,
            "step_ms": round(self.step_ms, 1) if self.step_ms else None,
            **self.run_info,
        }

    # --- endings ------------------------------------------------------------------
    def _finish(self) -> None:
        env = self.env
        self._publish_frame()
        try:
            self.summary = jsonable(env.close())
        except Exception as exc:
            log.exception("closing the finished run failed")
            self.error = f"could not write the run outputs: {exc}"
        self.env = None
        self.playing, self.ff_target, self.state = False, None, "finished"
        self._publish_status(message=f"Run finished at t = {env.t:.0f} s. Outputs in {env.output_dir}")

    def _fail(self, what: str, exc: BaseException) -> None:
        log.error("%s", what, exc_info=exc)
        self.error = f"{what}: {type(exc).__name__}: {exc}"
        env, self.env = self.env, None
        if env is not None:
            _safe_close(env)
        self.playing, self.ff_target, self.state = False, None, "error"
        self._publish_status(message=self.error)

    def _close_env(self) -> None:
        env, self.env = self.env, None
        if env is not None:
            _safe_close(env)


class EnvProxy:
    """The live env as the signal-data router (teamb/api) sees it.

    Attribute reads go straight to the env; method calls are executed on the sim thread, so
    router code can never talk to TraCI from a web thread by accident.
    """

    def __init__(self, session: TwinSession, env):
        self._session = session
        self._env = env

    def __getattr__(self, name: str):
        env = self._env
        value = getattr(env, name)
        if not callable(value):
            return value
        session = self._session

        def call(*args, **kwargs):
            def run():
                if session.env is not env:
                    raise RuntimeError("the simulation was restarted")
                return getattr(env, name)(*args, **kwargs)

            return session.call(run)

        call.__name__ = name
        return call


def _safe_close(env) -> None:
    """Close an env that may be only half started; never raise."""
    try:
        env.close()
    except Exception:
        log.warning("env.close() failed; closing the TraCI connection directly", exc_info=True)
        conn = getattr(env, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _snapshot(items: collections.deque) -> list:
    """Copy a deque another thread may be appending to."""
    for _ in range(5):
        try:
            return list(items)
        except RuntimeError:  # "deque mutated during iteration"
            time.sleep(0.001)
    return []
