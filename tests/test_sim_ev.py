"""Emergency-vehicle preemption when two EVs approach one junction (sim-core-3, ext-145, sim-core-12)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace

from teamb import config
from teamb.sim.env import SimEnv


class _FakeVehicles:
    def __init__(self, upcoming):
        self.upcoming = upcoming  # vid -> (tls, link index, distance)

    def getNextTLS(self, vid):
        tls, link, dist = self.upcoming[vid]
        return [(tls, link, dist, "r")]


def _env(upcoming, ev_ids):
    env = SimEnv.__new__(SimEnv)  # no SUMO: only what _ev_requests touches
    env.t, env.events, env.preemptions, env._ev_active = 10.0, [], [], set()
    env._ev_ids = set(ev_ids)
    env.conn = SimpleNamespace(vehicle=_FakeVehicles(upcoming))
    env.topology = SimpleNamespace(link_axis={"J2": {0: "NS", 1: "EW"}})
    return env


def test_nearest_ev_wins_whatever_the_set_order():
    upcoming = {"firetruck_2": ("J2", 0, 62.9), "ambulance_1": ("J2", 1, 139.5)}
    for order in (["ambulance_1", "firetruck_2"], ["firetruck_2", "ambulance_1"]):
        env = _env(upcoming, order)
        assert env._ev_requests() == {"J2": "NS"}
        assert [p["vehicle"] for p in env.preemptions] == ["firetruck_2"]


def test_a_running_preemption_is_not_taken_over():
    upcoming = {"firetruck_2": ("J2", 0, 62.9), "ambulance_1": ("J2", 1, 139.5)}
    env = _env(upcoming, upcoming)
    env._ev_requests()
    upcoming["ambulance_1"] = ("J2", 1, 30.0)  # the ambulance is now nearer...
    upcoming["firetruck_2"] = ("J2", 0, 40.0)
    assert env._ev_requests() == {"J2": "NS"}  # ...but the fire truck keeps its green until it passes
    upcoming["firetruck_2"] = ("J3", 0, 400.0)  # passed J2, next signal out of range
    assert env._ev_requests() == {"J2": "EW"}
    assert [(p["vehicle"], p["junction"]) for p in env.preemptions] == [("firetruck_2", "J2"), ("ambulance_1", "J2")]
    upcoming["ambulance_1"] = ("J2", 1, config.EV_PREEMPT_DISTANCE_M + 1)
    assert env._ev_requests() == {} and env._ev_active == set()


_TWO_EVS = """
import json, sys
from teamb.sim.env import SimEnv
env = SimEnv("rush_hour", "fixed_time", seed=2, end_time=300, output_dir=sys.argv[1]).start()
while env.t < 60:
    env.step()
env.handle_command({"type": "dispatch_ev", "origin": "W0_J1", "destination": "J4_E5", "kind": "ambulance"})
while env.t < 75:
    env.step()
env.handle_command({"type": "dispatch_ev", "origin": "NN2_N2", "destination": "J2_S2", "kind": "firetruck"})
while env.t < 300:
    env.step()
env.close()
arrivals = {e["vehicle"]: e["t"] for e in env.events if e["type"] == "ev_arrived"}
print(json.dumps({"arrivals": arrivals, "preemptions": env.preemptions}))
"""


def test_two_ev_conflict_is_the_same_in_every_process(tmp_path):
    """REP-01 across processes: the batch runner's spawn workers each get a random hash seed."""
    results = []
    for hash_seed in ("0", "2"):
        out = subprocess.run(
            [sys.executable, "-c", _TWO_EVS, str(tmp_path / hash_seed)],
            cwd=config.ROOT, env={**os.environ, "PYTHONHASHSEED": hash_seed},
            capture_output=True, text=True, timeout=180, check=True,
        )
        results.append(json.loads(out.stdout.strip().splitlines()[-1]))
    assert results[0] == results[1]
    arrivals = results[0]["arrivals"]
    assert set(arrivals) == {"ambulance_1", "firetruck_2"}
    assert arrivals["firetruck_2"] < 150  # the nearer fire truck was not held at J2 for the ambulance
    j2 = [p for p in results[0]["preemptions"] if p["junction"] == "J2"]
    assert j2[0]["vehicle"] == "firetruck_2"
