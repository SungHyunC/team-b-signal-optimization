"""Wiring between SimEnv, the scenario runtime, the sensors and max-pressure's closure_aware mode."""
from __future__ import annotations

import pytest

from teamb.sim.env import SimEnv


@pytest.fixture(scope="module")
def flooded(tmp_path_factory):
    """road_closure just after the flood closes J2 -> J3 at t = 1500 s."""
    env = SimEnv("road_closure", "max_pressure", seed=1, end_time=1600, output_dir=tmp_path_factory.mktemp("flood"))
    env.start()
    try:
        while env.t < 1505:
            env.step()
        yield env
    finally:
        env.abort()


def test_observation_carries_closure_notices(flooded):
    obs = flooded.sensors.observe(flooded.t, "detector")
    assert obs["closed_edges"] == ["J2_J3"]
    assert obs["junctions"]["J2"]["exits"]["E"]["closed"] is True
    assert obs["junctions"]["J3"]["exits"]["E"]["closed"] is False


def test_frame_lists_phantom_phones(flooded):
    assert flooded.frame()["phantom_phones"] == []  # no attack in this scenario


def test_summary_reports_failed_events(tmp_path):
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=960, scenario_params={"warmup": 900}, output_dir=tmp_path)
    summary = env.run()
    assert summary["failed_events"] == 0 and summary["complete"] is True
