"""TraCI round-trip budget (runtime-perf-4).

Run speed depends on the feed contract (teamb/sensors/feed.py): per-step values come from
subscriptions, so SensorSuite.observe makes no round trips and a whole step makes about three
(simulationStep, the teleport counter, signal changes, the 5-second metrics snapshot). A getter added in
sensors, metrics, SimEnv or a controller multiplies with vehicles x steps and would show here.
"""
from __future__ import annotations

import pytest
from traci.connection import Connection

from teamb.sensors.suite import SensorSuite
from teamb.sim.env import SimEnv

END = 300
# Measured 2.8 per step (6.8 before the step values were subscribed): simulationStep 1.0,
# ScenarioRuntime's getStartingTeleportNumber 1.0 (the feed already has it: teleports_started),
# the metrics snapshot 0.4, setRedYellowGreenState on signal changes 0.4.
MAX_ROUND_TRIPS_PER_STEP = 3.0


@pytest.mark.parametrize("controller", ["max_pressure", "fixed_time"])
def test_round_trips_per_step_stay_within_budget(tmp_path, monkeypatch, controller):
    counts = {"run": 0, "in_observe": 0}
    state = {"observing": False, "counting": False}
    send = Connection._sendExact

    def counting_send(self):
        if state["counting"]:
            counts["run"] += 1
            counts["in_observe"] += state["observing"]
        return send(self)

    observe = SensorSuite.observe

    def flagged_observe(self, *args, **kwargs):
        state["observing"] = True
        try:
            return observe(self, *args, **kwargs)
        finally:
            state["observing"] = False

    monkeypatch.setattr(Connection, "_sendExact", counting_send)
    monkeypatch.setattr(SensorSuite, "observe", flagged_observe)
    env = SimEnv("rush_hour", controller, seed=1, end_time=END, output_dir=tmp_path).start()
    state["counting"] = True  # the step loop only, not start-up and close
    while not env.finished:
        env.step()
    state["counting"] = False
    env.close()
    assert counts["in_observe"] == 0, "SensorSuite.observe made TraCI round trips"
    per_step = counts["run"] / env.step_count
    assert per_step <= MAX_ROUND_TRIPS_PER_STEP, f"{per_step:.2f} TraCI round trips per step"
