"""Experiment runner against real SUMO: end_time is part of the run identity, and an
interrupted run is redone on resume (evaluation-1, evaluation-2)."""
from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from teamb.experiments.runner import RunSpec, check_resume, run_matrix, run_one

PARAMS = {"warmup": 100.0}


def test_other_end_time_runs_again_and_interrupt_is_not_resumed(tmp_path, monkeypatch):
    short = RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=300.0, scenario_params=PARAMS)
    longer = RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=360.0, scenario_params=PARAMS)
    assert run_matrix([short], tmp_path, workers=1, quiet=True)["ok"] == 1
    second = run_matrix([longer], tmp_path, workers=1, quiet=True)
    assert second["ok"] == 1 and second["skipped"] == 0
    saved = json.loads((tmp_path / "runs" / longer.name / "run_spec.json").read_text())
    assert saved["end_time"] == 360.0
    assert json.loads((tmp_path / "runs" / longer.name / "summary.json").read_text())["sim_time_s"] == 360.0

    from teamb.sim.env import SimEnv

    real_step = SimEnv.step

    def step(self):
        if self.t >= 200:
            raise KeyboardInterrupt  # what Ctrl-C does mid-run
        real_step(self)

    monkeypatch.setattr(SimEnv, "step", step)
    spec = RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=420.0, scenario_params=PARAMS)
    with pytest.raises(KeyboardInterrupt):
        run_one(asdict(spec), str(tmp_path / "runs"))
    out = tmp_path / "runs" / spec.name
    assert (out / "error.json").exists() and not (out / "summary.json").exists()
    assert check_resume(spec, tmp_path / "runs") is None  # the next invocation runs it again
