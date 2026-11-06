"""The traffic feed as SimEnv uses it: closures from the runtime, a fresh feed per run."""
from __future__ import annotations

import csv

import pytest

from teamb.sensors import feed as feed_module
from teamb.sim import env as env_module
from teamb.sim.env import SimEnv

CLOSURES = {
    "warmup": 0,
    "events": [
        {"time": 30, "kind": "close_road", "params": {"edge": "J2_J3", "cause": "flood"}},
        {"time": 40, "kind": "close_road", "params": {"edge": "J2_N2", "cause": "sinkhole", "both_directions": True}},
        {"time": 90, "kind": "reopen_road", "params": {"edge": "J2_J3"}},
    ],
}


def _run(out, monkeypatch=None, lanes=False):
    if lanes:  # the old way: watch every edge's lane permissions
        real = feed_module.attach_feed
        monkeypatch.setattr(env_module, "attach_feed", lambda conn, topo, closures=None: real(conn, topo))
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=120, scenario_params=CLOSURES, output_dir=out)
    env.start()
    lane_subscriptions = len(env.conn.lane.getAllSubscriptionResults())
    closed_at_100 = None
    while not env.finished:
        env.step()
        if env.t == 100:
            closed_at_100 = env._feed.closed_edges()
    feed = env._feed
    env.close()
    with open(out / "timeseries.csv") as fh:
        rows = list(csv.reader(fh))
    return {"events": feed.events, "closed_at_100": closed_at_100, "timeseries": rows}, lane_subscriptions


def test_closures_from_the_runtime_match_lane_permission_watching(tmp_path, monkeypatch):
    """runtime-perf: the 40 LANE_DISALLOWED subscriptions are dropped when the runtime is attached."""
    new, new_lanes = _run(tmp_path / "runtime")
    old, old_lanes = _run(tmp_path / "lanes", monkeypatch, lanes=True)
    assert new_lanes == 0 and old_lanes == 40
    assert new == old
    assert [(e["t"], e["type"], e["edge"]) for e in new["events"]] == [
        (31.0, "road_closed", "J2_J3"), (41.0, "road_closed", "J2_N2"), (41.0, "road_closed", "N2_J2"),
        (91.0, "road_reopened", "J2_J3"),
    ]
    assert new["closed_at_100"] == {"J2_N2", "N2_J2"}


def test_every_start_gets_a_fresh_shared_feed(tmp_path):
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=5, output_dir=tmp_path).start()
    try:
        assert env.conn._teamb_feed is env._feed is env.sensors.feed is env.metrics.feed
        stale = env._feed
        fresh = feed_module.attach_feed(env.conn, env.topology)
        assert env.conn._teamb_feed is fresh is not stale
        assert feed_module.get_feed(env.conn, env.topology) is fresh
    finally:
        env.close()


def test_frames_query_vehicles_only_when_a_frame_is_built(tmp_path):
    """runtime-perf-2: frames=True must not decode every vehicle's variables on every step."""
    env = SimEnv("earthquake", "max_pressure", seed=1, end_time=400, output_dir=tmp_path, frames=True).start()
    try:
        while env.t < 300:
            env.step()
        assert env.conn.vehicle.getAllSubscriptionResults() == {}
        for _ in range(3):
            env.step()
            rows = env.frame()["vehicles"]
            on_road = set(env.conn.vehicle.getIDList())
            assert {r[0] for r in rows} == on_road and len(rows) == len(on_road) > 20
            for vid, x, y, angle, speed, kind in rows[:25]:
                px, py = env.conn.vehicle.getPosition(vid)
                assert abs(px - x) <= 0.01 and abs(py - y) <= 0.01
                assert abs(env.conn.vehicle.getSpeed(vid) - speed) <= 0.01
                assert kind in ("car", "probe", "truck", "bus", "ambulance", "firetruck")
        env.step()
        assert env.conn.vehicle.getAllSubscriptionResults() == {}
    finally:
        env.close()
