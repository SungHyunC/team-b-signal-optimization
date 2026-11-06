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
    # approach_biased:0.2 (arterial drivers share less): the arterial share is ~0.092 at c = 0.25,
    # below c/2, so the band must widen on the low side too (1/r) or queue_est_adj comes out low
    low, _ = _suite(topo, coverage=0.25, sampling="approach_biased:0.2")
    low._pen_loop[key].add(10.0, 1000)
    low._pen_probe[key].setdefault(0.25, type(low._pen_loop[key])(900.0)).add(10.0, 92)
    assert low._probe(10.0, key, lanes)[0]["penetration_est"] == pytest.approx((92 + 10 * 0.25) / 1010, abs=1e-3)


def test_fused_queue_never_exceeds_what_fits_on_the_approach(topo):
    det = {"queue": 12, "flow_vph": 400.0}
    storage = CrossCheck.from_topology(topo).approach_storage[("J4", "W")]
    fused = SensorSuite._fuse(det, {"queue_est_adj": 319.6}, True, True, storage)
    assert fused["queue"] == pytest.approx(round(storage, 2)) and fused["source"] == "detector+probe"
    assert SensorSuite._fuse(det, {"queue_est_adj": 319.6}, True, False, storage)["queue"] == 12  # untrusted
    assert SensorSuite._fuse(det, {"queue_est_adj": 319.6}, False, True, storage)["queue"] == 12  # zone not full


# --- cross-check while the detector zone is full (scenarios-sensors-2) ----------------------------
def test_crosscheck_still_tests_the_zone_when_it_is_full(topo):
    cc, key = CrossCheck.from_topology(topo), ("J2", "W")
    # 22 stopped phones claim the zone where the detector sees 10 halting cars
    assert cc.suspicious(key, 22, 10, True, 0.25, zone_halted=22) == "detector"
    assert cc.suspicious(key, 22, 10, True, 0.25) == ""  # without the zone split: storage test only
    # 20 phantom phones + 7 real probes in a jammed two-lane zone (28 halting): too many for p' = 0.5
    assert cc.suspicious(key, 27, 28, True, 0.25, zone_halted=27, zone_penetration=0.5) == "statistical"
    # genuine: a long queue whose tail is upstream, probes in the zone ~ 25 % of the halting cars
    assert cc.suspicious(key, 20, 28, True, 0.25, zone_halted=8, zone_penetration=0.5) == ""
    # navigation users can crowd one queue (twice the coverage is tolerated)
    assert cc.suspicious(key, 17, 21, True, 0.25, zone_halted=17, zone_penetration=0.5) == ""
    # more stopped phones upstream of the zone than fit there
    up = cc.upstream_storage[key]
    assert cc.suspicious(key, 10 + up + 3, 28, True, 0.25, zone_halted=10, zone_penetration=0.5) == "storage"


def _place(feed, lane, vehicles, zone_ids):
    feed.lanes[lane] = vehicles
    feed.zone[lane] = set(zone_ids)


def test_probe_reports_are_split_by_zone_and_phantoms_claim_the_stop_line(topo):
    suite, feed = _suite(topo, coverage=0.25)
    key, lanes = ("J2", "W"), tuple(topo.approach_lanes["J2"]["W"])
    for vid in ("p1", "p2", "p3", "p4"):
        suite.probes[vid] = 0.25
    # p1, p2 stopped in the zone; p3 stopped upstream; p4 moving; c1..c3 are not probes
    _place(feed, lanes[0], [("p1", 0.0), ("c1", 0.0), ("p3", 0.0)], {"p1", "c1"})
    _place(feed, lanes[1], [("p2", 0.0), ("c2", 0.0), ("p4", 5.0), ("c3", 0.0)], {"p2", "c2"})
    probe, truth, extra = suite._probe(100.0, key, lanes, split=True)
    assert probe["halted"] == 3 and extra["zone_halted"] == 2
    assert extra["upstream_eff"] == pytest.approx(1 / probe["penetration_est"], rel=1e-3)
    assert truth[0] == 6  # every stopped car, probe or not
    _, _, plain = suite._probe(100.0, key, lanes, split=False)
    assert plain["zone_halted"] is None and plain["upstream_eff"] is None
    suite.inject_fake_reports("J2", "W", 20)  # 10 per lane from 4 m: all inside the 100 m zone
    probe, _, extra = suite._probe(101.0, key, lanes, split=True)
    assert probe["halted"] == 23 and extra["zone_halted"] == 22
    suite.inject_fake_reports("J2", "W", 40)  # 20 per lane reach 146.5 m: 13 per lane (4..94 m) in the zone
    _, _, extra = suite._probe(102.0, key, lanes, split=True)
    assert extra["zone_halted"] == 2 + 26


def test_fused_queue_takes_the_zone_from_the_detector_and_only_upstream_from_probes(topo):
    det = {"queue": 25, "flow_vph": 600.0}
    probe = {"queue_est_adj": 120.0}  # inflated by phantom phones in the zone
    fused = SensorSuite._fuse(det, probe, True, True, 81.6, upstream=4.0, upstream_storage=53.0)
    assert fused["queue"] == 29.0  # 25 seen by the detector + 4 estimated beyond the zone
    assert SensorSuite._fuse(det, probe, True, True, 81.6, upstream=500.0, upstream_storage=53.0)["queue"] == 78.0
    assert SensorSuite._fuse(det, probe, True, True, 81.6)["queue"] == 81.6  # no split: capped old rule


def test_attack_accounting_reports_how_long_the_attack_stayed_trusted(topo):
    suite, _ = _suite(topo, coverage=0.25)
    suite.inject_fake_reports("J2", "W", 20)
    for trusted, fused, true in ((True, 30.0, 10), (False, 12.0, 10), (False, 9.0, 10), (False, 11.0, 10)):
        suite._account_attack(("J2", "W"), trusted, fused, true)
    a = suite.attacks[0]
    assert (a["observed_s"], a["trusted_s"], a["trusted_share"]) == (4, 1, 0.25)
    assert a["fused_excess_mean"] == pytest.approx((20 + 2 - 1 + 1) / 4)


def test_rolling_count_covers_exactly_the_window():
    from teamb.sensors.logs import RollingCount

    rc = RollingCount(300.0)
    for t in range(1, 1201):  # one vehicle every second
        rc.add(float(t), 1)
    assert rc.total == 300  # was 301: window + 1 steps, every flow read 301/300 of the truth
    assert rc.rate_vph(1200.0) == pytest.approx(3600.0)
