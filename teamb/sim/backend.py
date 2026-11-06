"""Starting and releasing the SUMO connection that SimEnv drives.

``start(cmd, label)`` launches SUMO and returns ``(conn, version)``; ``release(conn)`` ends it
and makes sure the SUMO process is gone, whatever state the connection is in.
"""
from __future__ import annotations

import contextlib
import subprocess

import traci


def start(cmd: list[str], label: str):
    """Launch SUMO with TraCI; returns (connection, SUMO version string)."""
    version = traci.start(cmd, label=label)
    conn = traci.getConnection(label)
    sumo_version = str(version[1]) if isinstance(version, tuple) and len(version) > 1 else "unknown"
    return conn, sumo_version


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
