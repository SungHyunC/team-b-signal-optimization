"""Probe estimates when the coverage changes mid-run (the twin's slider).

A vehicle shares data for its whole trip or not at all, decided at departure, so after a
change the probes on the road are a mix of the old and the new cohort for several minutes.
Two short SUMO runs (about 5 s each)."""
from __future__ import annotations

import pytest

from teamb.sim.env import SimEnv

CHANGE_AT, END = 1500.0, 1800.0


def _run(tmp_path, before: float, after: float) -> dict:
    env = SimEnv("rush_hour", "fixed_time", seed=1, coverage=before, end_time=END, output_dir=tmp_path)
    env.start()
    while env.t < END:
        env.step()
        if env.t == CHANGE_AT:
            assert env.handle_command({"type": "set_coverage", "value": after})["coverage"] == after
    out = {"episodes": list(env.sensors.check.episodes), "rows": [r for r in env.sensors.estimation if r[0] >= CHANGE_AT],
           "cohorts": dict(env.sensors._cohorts), "obs_coverage": env.sensors.coverage}
    env.close()
    return out


def _ratio(rows, col: int, truth: int = 7) -> float:
    return sum(r[col] for r in rows) / max(1e-9, sum(r[truth] for r in rows))


@pytest.mark.parametrize("before,after", [(0.1, 1.0), (1.0, 0.1)])
def test_coverage_change_keeps_estimates_unbiased_and_raises_no_false_alarm(tmp_path, before, after):
    o = _run(tmp_path, before, after)
    # raising the coverage made genuine reports look like fake ones (10 statistical alerts before)
    assert o["episodes"] == []
    assert o["obs_coverage"] == after
    assert 0.7 <= _ratio(o["rows"], 12) <= 1.3  # probe_queue_est (was 0.65x / 4.46x)
    assert 0.7 <= _ratio(o["rows"], 13) <= 1.3  # probe_queue_adj (was 2.98x / 0.48x)
    assert 0.7 <= _ratio(o["rows"], 14, truth=9) <= 1.3  # probe_flow_est_vph (was 0.31x / 7.98x)
    pen = sum(r[16] for r in o["rows"]) / len(o["rows"])
    assert abs(pen - after) <= 0.15 * max(after, 0.1) + 0.05  # penetration_est follows the new coverage at once
    assert set(o["cohorts"]) <= {before, after}  # probes remember the coverage they departed under
