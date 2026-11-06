"""Starting and releasing the SUMO connection that SimEnv drives.

``start(cmd, label)`` launches SUMO and returns ``(conn, version)``; ``release(conn)`` ends it
and makes sure the SUMO process is gone, whatever state the connection is in.
"""
from __future__ import annotations

import contextlib
import subprocess
import time

import traci
from sumolib.miscutils import getFreeSocketPort

CONNECT_TIMEOUT_S = 60.0  # traci's own budget (60 x 1 s); cold Docker/Render starts can be slow
PORT_ATTEMPTS = 3  # SUMO exited before we connected (e.g. lost the port to another process): new port


def start(cmd: list[str], label: str):
    """Launch SUMO with TraCI; returns (connection, SUMO version string).

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
