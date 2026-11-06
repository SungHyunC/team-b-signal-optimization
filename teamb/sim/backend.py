"""Starting and releasing the SUMO connection that SimEnv drives.

``start(cmd, label, backend)`` launches SUMO and returns ``(conn, version, backend used)``;
``release(conn)`` ends it and makes sure SUMO is gone, whatever state the connection is in.

Backends
--------
traci    (default) SUMO runs as a child process; every TraCI call is a socket round trip.
libsumo  SUMO runs inside this Python process (pip package ``libsumo``, same version as
         eclipse-sumo): no socket, no Python decoding of subscriptions, ~2.4x faster runs.
         Only one libsumo simulation can run per process; a SimEnv started while another
         one holds it (e.g. the AI recommender's nested plan search) uses traci instead.
auto     libsumo when it is installed, else traci.

``SimEnv(traci_backend=None)`` reads the choice from $TEAMB_TRACI_BACKEND (default traci).
"""
from __future__ import annotations

import contextlib
import importlib.util
import logging
import os
import subprocess
import threading
import time

import traci
from sumolib.miscutils import getFreeSocketPort

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_S = 60.0  # traci's own budget (60 x 1 s); cold Docker/Render starts can be slow
PORT_ATTEMPTS = 3  # SUMO exited before we connected (e.g. lost the port to another process): new port
BACKENDS = ("traci", "libsumo", "auto")
ENV_VAR = "TEAMB_TRACI_BACKEND"

_libsumo_lock = threading.Lock()
_libsumo_in_use = False


def requested(name: str | None = None) -> str:
    """The requested backend: `name`, or $TEAMB_TRACI_BACKEND when None (default 'traci')."""
    value = os.environ.get(ENV_VAR, "traci") if name is None else name
    value = (value or "traci").strip().lower()
    if value not in BACKENDS:
        raise ValueError(f"unknown TraCI backend {value!r} (expected one of {BACKENDS}; set via traci_backend or ${ENV_VAR})")
    return value


def libsumo_available() -> bool:
    return importlib.util.find_spec("libsumo") is not None


def start(cmd: list[str], label: str, backend: str = "traci"):
    """Launch SUMO; returns (connection, SUMO version string, backend used: 'traci' or 'libsumo')."""
    backend = requested(backend)
    if backend == "auto":
        backend = "libsumo" if libsumo_available() else "traci"
    if backend == "libsumo":
        started = _start_libsumo(cmd)
        if started is not None:
            return (*started, "libsumo")
        log.warning("libsumo already runs a simulation in this process; this one uses traci")
    return (*_start_traci(cmd, label), "traci")


def _start_traci(cmd: list[str], label: str):
    """Launch SUMO as a child process and connect; returns (connection, SUMO version string).

    traci.start() tries to connect at once, fails because SUMO is not listening yet, and then
    sleeps a fixed second (and prints 'Retrying in 1 seconds'). SUMO listens after ~0.1 s, so
    we launch it ourselves and retry the connection every few milliseconds (runtime-perf-1).
    The connection is the same traci Connection object, registered under `label`."""
    exit_code = None
    for _ in range(PORT_ATTEMPTS):
        port = getFreeSocketPort()
        proc = subprocess.Popen([*cmd, "--remote-port", str(port)])
        try:
            conn = _connect(port, proc, label)
            if conn is None:
                exit_code = proc.poll()
                _kill(proc)
                continue
            try:
                version = conn.getVersion()
            except BaseException:
                release(conn, timeout=5.0)
                raise
        except BaseException:
            _kill(proc)
            raise
        sumo_version = str(version[1]) if isinstance(version, tuple) and len(version) > 1 else "unknown"
        return conn, sumo_version
    raise traci.FatalTraCIError(f"could not connect to SUMO (exit code {exit_code}): {' '.join(map(str, cmd))}")


def _connect(port: int, proc: subprocess.Popen, label: str):
    """A Connection to the SUMO in `proc`, or None if it exited (or never listened) first.

    Only real connection attempts are made: a plain socket probe would take SUMO's single
    client slot and make it exit."""
    deadline = time.monotonic() + CONNECT_TIMEOUT_S
    pause = 0.005
    while True:
        try:
            return traci.connection.Connection("localhost", port, proc, None, True, label)
        except OSError:  # not listening yet
            if proc.poll() is not None or time.monotonic() > deadline:
                return None
            time.sleep(pause)
            pause = min(2 * pause, 0.05)


def _kill(proc: subprocess.Popen) -> None:
    with contextlib.suppress(Exception):
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


def _start_libsumo(cmd: list[str]):
    """Load the simulation into this process; (connection, version), or None if libsumo is busy."""
    global _libsumo_in_use
    import libsumo  # ImportError here means traci_backend='libsumo' without the libsumo package

    with _libsumo_lock:
        if _libsumo_in_use:
            return None
        _libsumo_in_use = True
    try:
        conn = LibsumoConnection(libsumo)
        version = conn.start(list(cmd))
        # libsumo keeps the previous simulation's subscription results in this process, and a new
        # subscription with nothing to report (e.g. no vehicles at t=0) does not overwrite them, so
        # a second run's first observation saw the last run's vehicles. A step to a past time
        # simulates nothing (the clock stays at 0) but clears all subscription results.
        conn.simulationStep(-1.0)
    except BaseException:
        _free_libsumo()
        with contextlib.suppress(Exception):
            libsumo.close()
        raise
    sumo_version = str(version[1]) if isinstance(version, tuple) and len(version) > 1 else "unknown"
    return conn, sumo_version


def _free_libsumo() -> None:
    global _libsumo_in_use
    with _libsumo_lock:
        _libsumo_in_use = False


def _translating(fn, lib):
    """`fn` raising traci's exception classes instead of libsumo's own ones."""
    tra_exc, fatal_exc = lib.TraCIException, lib.FatalTraCIError

    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except tra_exc as exc:
            raise traci.TraCIException(str(exc)) from None
        except fatal_exc as exc:
            raise traci.FatalTraCIError(str(exc)) from None

    call.__name__ = getattr(fn, "__name__", "call")
    call.__doc__ = getattr(fn, "__doc__", None)
    return call


class _LibsumoDomain:
    """One libsumo domain (vehicle, lane, ...) with traci's exception classes."""

    def __init__(self, domain, lib):
        self._domain = domain
        self._lib = lib

    def __getattr__(self, name: str):
        target = getattr(self._domain, name)
        if callable(target) and not isinstance(target, type):
            target = _translating(target, self._lib)
        setattr(self, name, target)  # cached: __getattr__ runs once per name
        return target


class LibsumoConnection:
    """libsumo behind the traci Connection interface (``conn.vehicle.getSpeed(...)``, ``conn.simulationStep()``).

    libsumo has no connection objects (the module is the simulation) and raises its own
    TraCIException / FatalTraCIError classes, which ``except traci.TraCIException`` in the
    sensors, metrics and scenario events would not catch. This wrapper translates them. It is a
    new object per run, so per-run attributes (the feed cache ``_teamb_feed``) never leak into the
    next run."""

    backend = "libsumo"

    def __init__(self, lib):
        self._lib = lib
        self._closed = False

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        target = getattr(self._lib, name)
        if isinstance(target, type):
            target = _LibsumoDomain(target, self._lib)
        elif callable(target):
            target = _translating(target, self._lib)
        setattr(self, name, target)
        return target

    def close(self, wait: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            _translating(self._lib.close, self._lib)()
        finally:
            _free_libsumo()


def release(conn, timeout: float = 60.0) -> None:
    """Close a TraCI connection and make sure its SUMO process has exited. Never raises.

    A healthy connection is closed normally, so SUMO finishes writing its outputs (tripinfo).
    A broken one (SUMO died, Ctrl-C during a socket read) cannot be closed by traci: its socket
    and its entry in traci's connection pool are dropped here instead. Either way SUMO is waited
    for up to `timeout` seconds and killed if it is still running, so no process is left behind
    and the tripinfo file is never read while SUMO may still be writing it.
    """
    if conn is None:
        return
    if isinstance(conn, LibsumoConnection):  # in-process: close() returns when SUMO has finished
        with contextlib.suppress(Exception):
            conn.close()
        return
    proc = getattr(conn, "_process", None)
    try:
        conn.close(wait=False)
    except Exception:
        _drop(conn)
    if proc is None:
        return
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(Exception):
            proc.kill()
            proc.wait(timeout=10)
    except Exception:
        pass


def _drop(conn) -> None:
    """Forget a TraCI connection whose close() failed: close its socket, remove it from the pool."""
    sock = getattr(conn, "_socket", None)
    if sock is not None:
        with contextlib.suppress(Exception):
            sock.close()
    with contextlib.suppress(Exception):
        conn._socket = None
    pool = getattr(traci.connection, "_connections", None)
    if isinstance(pool, dict):
        for key in ("", getattr(conn, "_label", None)):
            if key is not None and pool.get(key) is conn:
                pool.pop(key, None)
