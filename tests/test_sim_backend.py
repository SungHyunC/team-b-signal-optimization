"""SUMO location and TraCI backend selection (traci socket vs libsumo)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from teamb import sumo_paths


def test_binary_ignores_a_sumo_home_without_binaries(tmp_path, monkeypatch):
    """Importing libsumo points SUMO_HOME at the sumo_data package, which has no bin/ folder."""
    real = Path(sumo_paths.binary("sumo"))
    data_only = tmp_path / "sumo_data"
    (data_only / "data").mkdir(parents=True)
    monkeypatch.setenv("SUMO_HOME", str(data_only))
    found = Path(sumo_paths.binary("sumo"))
    assert found.exists() and found.name.startswith("sumo")
    if (real.parent.parent / "bin").is_dir():
        assert found == real
    assert sumo_paths.sumo_home() != data_only or not (data_only / "bin").exists()


def test_start_does_not_use_tracis_sleeping_connect(tmp_path, monkeypatch, capfd):
    """runtime-perf-1: traci.start() always sleeps a fixed second before its second connect attempt."""
    import traci

    from teamb.sim.env import SimEnv

    def forbidden(*args, **kwargs):
        raise AssertionError("traci.start/connect sleeps 1 s per start")

    monkeypatch.setattr(traci, "start", forbidden)
    monkeypatch.setattr(traci.main, "connect", forbidden)
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=3, output_dir=tmp_path)
    summary = env.run()
    assert summary["complete"] and summary["sim_time_s"] == 3.0
    assert "Retrying" not in capfd.readouterr().out
    assert env.label not in traci.connection._connections


def test_start_reports_a_sumo_that_exits_at_once(tmp_path):
    import traci

    from teamb.sim import backend

    cmd = [sumo_paths.binary("sumo"), "-n", str(tmp_path / "missing.net.xml")]
    t0 = time.monotonic()
    with pytest.raises(traci.FatalTraCIError):  # SUMO quits on the missing network: fail fast, no 60 s wait
        backend.start(cmd, "teamb_test_bad_start")
    assert time.monotonic() - t0 < 20
    assert "teamb_test_bad_start" not in traci.connection._connections


def test_backend_choice_is_validated(monkeypatch, tmp_path):
    from teamb.sim import backend
    from teamb.sim.env import SimEnv

    monkeypatch.delenv(backend.ENV_VAR, raising=False)
    assert backend.requested(None) == "traci"
    monkeypatch.setenv(backend.ENV_VAR, " LibSUMO ")
    assert backend.requested(None) == "libsumo"
    assert backend.requested("auto") == "auto"
    with pytest.raises(ValueError, match="TraCI backend"):
        backend.requested("sockets")
    with pytest.raises(ValueError, match="TraCI backend"):
        SimEnv("rush_hour", "fixed_time", traci_backend="sockets", output_dir=tmp_path)
    monkeypatch.setenv(backend.ENV_VAR, "traci")
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=2, output_dir=tmp_path)
    env.run()
    assert env.traci_backend == "traci"
    assert json.loads((tmp_path / "manifest.json").read_text())["traci_backend"] == "traci"


# libsumo changes process-wide state when imported (SUMO_HOME, traci.exceptions), so its checks
# run in a separate interpreter.
_LIBSUMO_CHECKS = r"""
import json, sys
from pathlib import Path
import traci
from teamb.sim.env import SimEnv

out = Path(sys.argv[1])
params = {"warmup": 0, "events": [
    {"time": 20, "kind": "dispatch_ev", "params": {"origin": "W0_J1", "destination": "J4_E5", "kind": "ambulance"}},
    {"time": 30, "kind": "close_road", "params": {"edge": "J2_J3", "cause": "flood"}},
    {"time": 150, "kind": "reopen_road", "params": {"edge": "J2_J3"}},
]}
DROP = {"run_id", "wall_time_s"}

def run(backend, name, frames=False):
    env = SimEnv("rush_hour", "max_pressure", seed=1, end_time=240, scenario_params=params, output_dir=out / name,
                 traci_backend=backend, frames=frames)
    env.start()
    seen = []
    while not env.finished:
        env.step()
        if frames and env.t % 60 == 0:
            seen.append(sorted(env.frame()["vehicles"]))
    s = env.close()
    files = {f: (out / name / f).read_text() for f in ("preemptions.json", "events_report.json", "timeseries.csv", "trips.csv")}
    return env.traci_backend, {k: v for k, v in s.items() if k not in DROP}, files, seen

res = {}
res["traci"] = run("traci", "t", frames=True)
res["libsumo"] = run("libsumo", "l1", frames=True)
res["libsumo_again"] = run("libsumo", "l2", frames=True)  # same process: nothing may leak from run 1

outer = SimEnv("rush_hour", "fixed_time", seed=1, end_time=30, output_dir=out / "outer", traci_backend="libsumo").start()
try:
    outer.conn.vehicle.getNextTLS("no_such_vehicle")
    translated = False
except traci.TraCIException:
    translated = True
inner = SimEnv("rush_hour", "fixed_time", seed=1, end_time=20, output_dir=out / "inner", traci_backend="auto")
inner_summary = inner.run()  # libsumo is busy: the nested run falls back to traci
while not outer.finished:
    outer.step()
outer_summary = outer.close()

failed = SimEnv("rush_hour", "rl", seed=1, end_time=10, controller_params={"model_path": str(out / "missing.json")},
                output_dir=out / "failed", traci_backend="libsumo")
try:
    failed.run()
    start_error = None
except FileNotFoundError as exc:
    start_error = type(exc).__name__
def boom(env):
    if env.t >= 10:
        raise RuntimeError("mid-run failure")
crashed = SimEnv("rush_hour", "fixed_time", seed=1, end_time=30, output_dir=out / "crashed", traci_backend="libsumo")
try:
    crashed.run(callback=boom)
except RuntimeError:
    pass
after = SimEnv("rush_hour", "fixed_time", seed=1, end_time=5, output_dir=out / "after", traci_backend="libsumo")
after.run()

print(json.dumps({
    "runs": {k: [v[0], v[1], v[2], v[3]] for k, v in res.items()},
    "translated": translated,
    "nested": [outer.traci_backend, outer_summary["complete"], inner.traci_backend, inner_summary["complete"]],
    "start_error": start_error, "after": [after.traci_backend, after.summary["complete"]],
    "crashed_summary": (out / "crashed" / "summary.json").exists(),
}))
"""


def test_libsumo_gives_identical_results(tmp_path):
    """Contract 4: the optional libsumo backend must not change any number."""
    pytest.importorskip("libsumo")
    import subprocess
    import sys

    from teamb import config

    proc = subprocess.run([sys.executable, "-c", _LIBSUMO_CHECKS, str(tmp_path)], cwd=config.ROOT,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    runs = res["runs"]
    assert [runs[k][0] for k in ("traci", "libsumo", "libsumo_again")] == ["traci", "libsumo", "libsumo"]
    summary = runs["traci"][1]
    assert summary["complete"] and summary["preemptions"] >= 1 and summary["ev_count"] == 1
    for k in ("libsumo", "libsumo_again"):
        assert runs[k][1] == summary, k  # summary.json values
        assert runs[k][2] == runs["traci"][2], k  # preemptions, events report, timeseries, trips
        assert runs[k][3] == runs["traci"][3], k  # frames
    assert res["translated"] is True  # libsumo's TraCIException is raised as traci.TraCIException
    assert res["nested"] == ["libsumo", True, "traci", True]
    assert res["start_error"] == "FileNotFoundError" and res["after"] == ["libsumo", True]  # failures free libsumo
    assert res["crashed_summary"] is False
