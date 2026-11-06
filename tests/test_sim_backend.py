"""SUMO location and TraCI backend selection (traci socket vs libsumo)."""
from __future__ import annotations

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
