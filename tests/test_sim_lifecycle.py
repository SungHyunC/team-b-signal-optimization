"""SimEnv lifecycle: run completeness (contract 2), failure paths and SUMO cleanup.

sim-core-1, sim-core-2, sim-core-4, sim-core-7, sim-core-8, sim-core-12, ext-151.
"""
from __future__ import annotations

import json
import os
import signal

import pytest
import traci

from teamb.sim import backend
from teamb.sim.env import SimEnv


@pytest.fixture
def started(monkeypatch):
    """Records every connection SimEnv opens, to check later that SUMO and the TraCI label are gone."""
    conns = []
    original = backend.start

    def recording(cmd, label, *args, **kwargs):
        conn, version, used = original(cmd, label, *args, **kwargs)
        conns.append(conn)
        return conn, version, used

    monkeypatch.setattr(backend, "start", recording)
    return conns


def _released(conn) -> bool:
    proc = getattr(conn, "_process", None)
    label = getattr(conn, "_label", None)
    return (proc is None or proc.poll() is not None) and label not in traci.connection._connections


def _raise_at(t_fail, exc_type=RuntimeError):
    def callback(env):
        if env.t >= t_fail:
            raise exc_type(f"boom at t={env.t}")

    return callback


def test_complete_run_writes_summary_last_with_complete_flag(tmp_path, started):
    out = tmp_path / "run"
    summary = SimEnv("rush_hour", "fixed_time", seed=1, end_time=30, output_dir=out).run()
    assert summary["complete"] is True and summary["end_time"] == 30.0 and summary["sim_time_s"] == 30.0
    assert json.loads((out / "summary.json").read_text()) == summary
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["complete"] is True and manifest["outputs"]["summary"] == "summary.json"
    for name in manifest["outputs"].values():  # ext-151: every listed output exists
        assert (out / name).exists(), name
    assert not (out / "summary.partial.json").exists()
    assert not [p for p in out.iterdir() if p.name.endswith(".tmp")]
    assert (out / "summary.json").stat().st_mtime_ns >= max(p.stat().st_mtime_ns for p in out.iterdir())
    assert _released(started[0])


def test_failed_run_leaves_no_summary_and_releases_sumo(tmp_path, started):
    out = tmp_path / "run"
    out.mkdir()
    (out / "summary.json").write_text('{"stale": true}')  # from an earlier run in the same folder
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=60, output_dir=out)
    with pytest.raises(RuntimeError, match="boom"):
        env.run(callback=_raise_at(20))
    assert not (out / "summary.json").exists() and not (out / "summary.partial.json").exists()
    assert not (out / "manifest.json").exists()
    assert _released(started[0])
    assert env.close() is None  # the twin's clean-up after a failure is a no-op


def test_ctrl_c_propagates_and_writes_nothing(tmp_path, started):
    out = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        SimEnv("rush_hour", "fixed_time", seed=1, end_time=60, output_dir=out).run(callback=_raise_at(15, KeyboardInterrupt))
    assert not (out / "summary.json").exists()
    assert _released(started[0])


def test_sumo_dying_mid_run_raises_the_traci_error_not_a_parse_error(tmp_path, started):
    """sim-core-4: the truncated tripinfo must not be parsed on the error path."""
    out = tmp_path / "run"
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=200, output_dir=out).start()
    while env.t < 50:
        env.step()
    proc = env.conn._process
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=10)
    with pytest.raises(traci.FatalTraCIError):
        env.run()
    assert not (out / "summary.json").exists()
    assert _released(started[0])


def test_failed_start_releases_sumo(tmp_path, started):
    """sim-core-2: a controller that fails in reset() (missing RL model) must not leak SUMO."""
    missing = {"model_path": str(tmp_path / "missing.json")}
    env = SimEnv("rush_hour", "rl", seed=1, end_time=10, controller_params=missing, output_dir=tmp_path / "a")
    with pytest.raises(FileNotFoundError):
        env.run()
    assert env.conn is None and _released(started[0])
    with pytest.raises(FileNotFoundError):
        with SimEnv("rush_hour", "rl", seed=1, end_time=10, controller_params=missing, output_dir=tmp_path / "b"):
            pass
    assert len(started) == 2 and _released(started[1])


def test_exception_inside_with_block_aborts(tmp_path, started):
    with pytest.raises(ValueError, match="inside"):
        with SimEnv("rush_hour", "fixed_time", seed=1, end_time=30, output_dir=tmp_path / "w") as env:
            env.step()
            raise ValueError("inside the block")
    assert not (tmp_path / "w" / "summary.json").exists() and _released(started[0])


def test_closing_early_writes_a_partial_summary_only(tmp_path):
    out = tmp_path / "run"
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=60, output_dir=out).start()
    while env.t < 20:
        env.step()
    summary = env.close()  # e.g. the twin's Reset
    assert summary["complete"] is False and summary["sim_time_s"] == 20.0
    assert not (out / "summary.json").exists()
    assert json.loads((out / "summary.partial.json").read_text()) == summary
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["complete"] is False and manifest["outputs"]["summary"] == "summary.partial.json"


def test_a_step_that_fails_at_the_end_time_is_not_complete(tmp_path):
    out = tmp_path / "run"
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=10, output_dir=out).start()
    original = env.runtime.on_step

    def failing(t, *step_lists):
        if t >= 10:
            raise RuntimeError("bookkeeping failed in the last step")
        original(t, *step_lists)

    env.runtime.on_step = failing
    with pytest.raises(RuntimeError):
        while True:
            env.step()
    assert env.finished and not env.complete
    assert env.close()["complete"] is False and not (out / "summary.json").exists()


def test_coverage_outside_0_1_is_rejected(tmp_path):
    """sim-core-7 / ext-12: the summary and run_id must show the coverage the sensors use."""
    for bad in (0.0, -0.1, 50.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="coverage"):
            SimEnv("rush_hour", "fixed_time", coverage=bad, output_dir=tmp_path)
    env = SimEnv("rush_hour", "fixed_time", coverage=0.5, output_dir=tmp_path)
    assert env.coverage == 0.5 and "__c50__" in env.run_id


def test_disabling_preemption_clears_the_preempting_junctions(tmp_path):
    """sim-core-8: frame()['preempting'] must not stay set after preemption is turned off."""
    env = SimEnv("rush_hour", "fixed_time", seed=2, end_time=400, output_dir=tmp_path).start()
    try:
        while env.t < 60:
            env.step()
        env.handle_command({"type": "dispatch_ev", "origin": "W0_J1", "destination": "J4_E5", "kind": "ambulance"})
        while env.t < 200 and not env.frame()["preempting"]:
            env.step()
        assert env.frame()["preempting"]
        env.handle_command({"type": "set_preemption", "enabled": False})
        frame = env.frame()  # the twin publishes this frame right away: it must agree with itself
        assert frame["preempting"] == []
        assert all(js.preempted_by is None for js in env.supervisor.junctions.values())
        assert all(s["preempted_by"] is None for s in frame["signals"].values())
        assert all(s["preempted_by"] is None for s in env.spat()["junctions"].values())
        env.step()
        assert env.frame()["preempting"] == []
        assert all(js.preempted_by is None for js in env.supervisor.junctions.values())
        n = len(env.preemptions)
        env.handle_command({"type": "set_preemption", "enabled": True})
        while env.t < 300 and len(env.preemptions) == n:
            env.step()
        assert len(env.preemptions) > n  # re-enabled: the approaching EV is preempted (and logged) again
    finally:
        env.close()


def test_run_on_a_finished_env_returns_its_summary_without_restarting_sumo(tmp_path, started):
    """run() again after close() must not start a second SUMO, delete summary.json or leak it."""
    out = tmp_path / "run"
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=5, output_dir=out)
    summary = env.run()
    assert env.run() == summary  # a no-op that returns the same summary
    assert json.loads((out / "summary.json").read_text()) == summary
    assert env.conn is None and len(started) == 1 and _released(started[0])
    assert not [label for label in traci.connection._connections if label.startswith("teamb")]
    with pytest.raises(RuntimeError, match="already"):
        env.start()  # also through `with env:`
    assert len(started) == 1


def test_run_after_abort_does_not_restart_sumo(tmp_path, started):
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=5, output_dir=tmp_path / "a").start()
    env.step()
    env.abort()
    assert env.run() is None  # aborted: nothing to return and nothing new is simulated
    assert env.conn is None and len(started) == 1 and _released(started[0])
    assert not (tmp_path / "a" / "summary.json").exists()
