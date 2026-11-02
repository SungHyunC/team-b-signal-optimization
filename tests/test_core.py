"""Core acceptance tests from the software role package: NET-01, SIG-01, SIG-02, REP-01, PERF-01."""
from __future__ import annotations

import itertools
import json
import random

import pytest

from teamb import config
from teamb.controllers.base import Controller
from teamb.network.topology import load_topology
from teamb.safety.supervisor import SafetySupervisor
from teamb.sim.env import SimEnv
from teamb.sim.phases import NEXT_SIGNAL, SIGNALS, build_state, is_conflict_free


@pytest.fixture(scope="module")
def topo():
    return load_topology()


def test_net01_four_junctions_with_all_movements(topo):
    assert topo.tls_ids == ["J1", "J2", "J3", "J4"]
    for j in topo.tls_ids:
        assert set(topo.approach_lanes[j]) == {"W", "E", "N", "S"}
        movements = {(link.approach, link.direction) for link in topo.links[j]}
        for side in "WENS":
            assert {(side, "s"), (side, "l"), (side, "r")} <= movements
        assert all(link.direction not in ("t", "T") for link in topo.links[j])  # no U-turns


def test_net01_routes_and_detour(topo):
    assert topo.shortest_path("W0_J1", "J4_E5") == ["W0_J1", "J1_J2", "J2_J3", "J3_J4", "J4_E5"]
    for i, j in enumerate(topo.tls_ids, start=1):
        assert topo.shortest_path(f"NN{i}_N{i}", f"{j}_S{i}")[-1] == f"{j}_S{i}"
    assert topo.shortest_path("J2_N2", "N3_J3") == ["J2_N2", "N2_N3", "N3_J3"]  # back-street detour


def test_sig01_every_signal_state_is_conflict_free(topo):
    for j in topo.tls_ids:
        for signal in SIGNALS:
            state = build_state(topo.links[j], topo.n_links[j], signal)
            assert len(state) == topo.n_links[j]
            assert is_conflict_free(topo.links[j], state)
        assert not is_conflict_free(topo.links[j], "G" * topo.n_links[j])


def test_sig01_supervisor_timing_under_random_requests(topo):
    sup = SafetySupervisor(list(topo.tls_ids))
    rng = random.Random(0)
    shown = {j: [] for j in topo.tls_ids}
    for t in range(3000):
        action = {j: rng.choice(["EW", "NS", None]) for j in topo.tls_ids}
        for j, signal in sup.apply_safe_action(sup.validate(action, t), t).items():
            shown[j].append(signal)
        sup.tick(1.0)
    for seq in shown.values():
        runs = [(signal, len(list(group))) for signal, group in itertools.groupby(seq)]
        assert len(runs) > 20
        for (signal, n), (nxt, _) in zip(runs, runs[1:]):
            assert NEXT_SIGNAL[signal] == nxt  # never skips yellow or all-red
            if signal.endswith("_G"):
                assert n >= config.MIN_GREEN_S
            elif signal.endswith("_Y"):
                assert n == config.YELLOW_S
            else:
                assert n == config.ALL_RED_S


def test_sig02_invalid_actions_are_rejected_and_logged(topo):
    sup = SafetySupervisor(list(topo.tls_ids))
    assert sup.validate({"J9": "EW", "J1": "XX", "J2": "NS", "J3": None}, 0) == {"J2": "NS"}
    assert sup.validate("switch now", 0) == {}
    assert sup.rejections == 3
    details = " ".join(e.detail for e in sup.events if e.reason == "rejected")
    assert "unknown junction" in details and "invalid phase" in details


class _Broken(Controller):
    name = "broken_for_test"

    def propose_action(self, state):
        raise RuntimeError("boom")


def test_sig02_failing_controller_falls_back_to_fixed_time(tmp_path):
    summary = SimEnv("rush_hour", _Broken(), seed=1, end_time=150, output_dir=tmp_path).run()
    assert summary["controller_errors"] == summary["fallback_steps"] == 150
    assert summary["signal_switches"] > 0


def test_ev_preemption_clears_the_way(tmp_path):
    env = SimEnv("rush_hour", "fixed_time", seed=2, end_time=420, output_dir=tmp_path).start()
    while env.t < 60:
        env.step()
    env.handle_command({"type": "dispatch_ev", "origin": "W0_J1", "destination": "J4_E5", "kind": "ambulance"})
    while env.t < 420 and not any(e["type"] == "ev_arrived" for e in env.events):
        env.step()
    env.close()
    assert any(e["type"] == "ev_arrived" for e in env.events)
    assert {p["junction"] for p in env.preemptions} >= {"J1", "J2", "J3", "J4"} or len(env.preemptions) >= 2


def test_rep01_same_seed_same_result_and_perf01_fields(tmp_path):
    a = SimEnv("rush_hour", "fixed_time", seed=7, end_time=1200, output_dir=tmp_path / "a").run()
    b = SimEnv("rush_hour", "fixed_time", seed=7, end_time=1200, output_dir=tmp_path / "b").run()
    keys = ["completed", "unfinished", "mean_delay_s", "p95_travel_time_s", "stops_per_veh"]
    assert {k: a[k] for k in keys} == {k: b[k] for k in keys}
    assert a["completed"] > 0 and a["unfinished"] >= 0 and "unfinished_pct" in a
    manifest = json.loads((tmp_path / "a" / "manifest.json").read_text())
    assert manifest["seed"] == 7 and manifest["network_hash"] and manifest["demand_hash"]
    assert (tmp_path / "a" / "signal_events.csv").exists() and (tmp_path / "a" / "trips.csv").exists()
