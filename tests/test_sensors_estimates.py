"""SensorSuite estimates and the fake-data cross-check on hand-made traffic (no SUMO).

A stub feed stands in for the TraCI subscriptions, so each case sets exactly the vehicles,
detector readings and counts it needs."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import traci.constants as tc

from teamb.network.topology import load_topology
from teamb.sensors.crosscheck import CrossCheck
from teamb.sensors.suite import SensorSuite


class StubFeed:
    def __init__(self, topo):
        self.detector_lanes = sorted({l for j in topo.tls_ids for ls in topo.approach_lanes[j].values() for l in ls})
        self.sensors, self.events, self.t = None, [], None
        self.lanes: dict[str, list] = {}  # lane -> [(vehicle id, speed)]
        self.e2v: dict[str, dict] = {}  # lane -> {variable: value}
        self.zone: dict[str, list] = {}  # lane -> vehicle ids inside the E2 zone

    def update(self, t):
        self.t = t

    def on_lane(self, lane):
        return self.lanes.get(lane, ())

    def e2(self, lane, var):
        return self.e2v.get(lane, {}).get(var, 0)

    def e1(self, lane, var):
        return () if var == tc.LAST_STEP_VEHICLE_ID_LIST else 99.0

    def e2_vehicles(self, lane):
        return self.zone.get(lane, ())

    def origin_group(self, vid):
        return "arterial"


@pytest.fixture(scope="module")
def topo():
    return load_topology()


def _suite(topo, coverage=0.25, sampling="uniform"):
    feed = StubFeed(topo)
    return SensorSuite(SimpleNamespace(_teamb_feed=feed), topo, coverage=coverage, sampling=sampling), feed


def test_penetration_estimate_stays_near_the_coverage_after_a_closure(topo):
    """After a reopening the first crossers can all be non-probes (the navigation users were
    re-routed away). The estimate must not collapse (scenarios-sensors-4)."""
    suite, _ = _suite(topo, coverage=0.25)
    key = ("J4", "W")
    lanes = tuple(topo.approach_lanes["J4"]["W"])
    suite._pen_loop[key].add(3100.0, 30)  # 30 loop crossings, 0 probe crossings
    probe, _, extra = suite._probe(3100.0, key, lanes)
    assert probe["penetration_est"] >= 0.125  # was 0.0625 (prior only), and 0.053 in the earthquake run
    assert suite.check.suspicious(key, 7, 15, False, extra["p_test"]) == ""  # genuine reports, no alarm
    for _ in range(400):  # plenty of crossings, all by probes: capped at 2c
        suite._pen_loop[key].add(3101.0, 1)
        suite._pen_probe[key].setdefault(0.25, type(suite._pen_loop[key])(900.0)).add(3101.0, 1)
    assert suite._probe(3101.0, key, lanes)[0]["penetration_est"] == pytest.approx(0.5)
    wide, _ = _suite(topo, coverage=0.25, sampling="approach_biased:4")
    wide._pen_loop[key].add(10.0, 400)
    assert wide._probe(10.0, key, lanes)[0]["penetration_est"] == pytest.approx(0.25 / 4, abs=1e-3)


def test_fused_queue_never_exceeds_what_fits_on_the_approach(topo):
    det = {"queue": 12, "flow_vph": 400.0}
    storage = CrossCheck.from_topology(topo).approach_storage[("J4", "W")]
    fused = SensorSuite._fuse(det, {"queue_est_adj": 319.6}, True, True, storage)
    assert fused["queue"] == pytest.approx(round(storage, 2)) and fused["source"] == "detector+probe"
    assert SensorSuite._fuse(det, {"queue_est_adj": 319.6}, True, False, storage)["queue"] == 12  # untrusted
    assert SensorSuite._fuse(det, {"queue_est_adj": 319.6}, False, True, storage)["queue"] == 12  # zone not full
