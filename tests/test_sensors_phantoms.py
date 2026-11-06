"""Fake-phone positions for the twin (no SUMO): exactly n phones, all on the road."""
from __future__ import annotations

import math

import pytest

from teamb.network.topology import load_topology
from teamb.sensors.suite import PHANTOM_FRONT_M, PHANTOM_SPACING_M, phantom_layout


@pytest.fixture(scope="module")
def topo():
    return load_topology()


def _distance_to_polyline(shape, x, y) -> float:
    best = float("inf")
    for (x0, y0), (x1, y1) in zip(shape[:-1], shape[1:]):
        dx, dy = x1 - x0, y1 - y0
        seg2 = dx * dx + dy * dy
        f = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / seg2))
        best = min(best, math.hypot(x - (x0 + f * dx), y - (y0 + f * dy)))
    return best


def _capacity(topo, lane):
    return int((topo.lane_length(lane) - PHANTOM_FRONT_M) // PHANTOM_SPACING_M) + 1


@pytest.mark.parametrize("junction,approach,n", [("J2", "N", 99), ("J2", "W", 99), ("J2", "W", 1), ("J2", "W", 7), ("J1", "S", 5), ("J3", "E", 0)])
def test_phantoms_are_exactly_n_and_stay_on_the_approach_lanes(topo, junction, approach, n):
    lanes = topo.approach_lanes[junction][approach]
    layout = phantom_layout(topo, junction, approach, n)
    room = sum(_capacity(topo, lane) for lane in lanes)
    assert layout["shown"] == len(layout["positions"]) == min(n, room)
    assert layout["shown"] + layout["hidden"] == n
    shapes = [topo.net.getLane(lane).getShape() for lane in lanes]
    for x, y in layout["positions"]:
        assert min(_distance_to_polyline(s, x, y) for s in shapes) < 0.05, (x, y)
    for lane, ds in layout["lanes"].items():
        assert all(d <= topo.lane_length(lane) for d in ds)
    counts = [len(layout["lanes"][lane]) for lane in lanes]
    assert max(counts) - min(counts) <= 1 or layout["hidden"]  # spread evenly over the lanes


def test_default_attack_is_capped_at_the_lane_and_reports_the_rest(topo):
    layout = phantom_layout(topo, "J2", "N", 99)  # one 232 m lane: 31 phones fit
    assert layout["shown"] == 31 and layout["hidden"] == 68
    ys = [y for _, y in layout["positions"]]
    j2 = topo.net.getNode("J2").getCoord()
    n2 = topo.net.getNode("N2").getCoord()
    assert all(j2[1] < y < n2[1] for y in ys)  # between the stop line and N2, not 300 m off the map
    one = phantom_layout(topo, "J2", "W", 1)
    assert one["shown"] == 1 and sum(len(d) for d in one["lanes"].values()) == 1
