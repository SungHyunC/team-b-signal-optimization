"""Fake-data defense: do the probe reports make physical sense next to the loop detectors?

Idea: navigation-app reports are cheap to fake (Berlin 2020: 99 phones in a handcart),
loop detectors are not. For one approach and one second we compare

    H       stopped-probe reports (real probes + any fake ones) - a raw count, NOT scaled
    Q_det   vehicles the E2 detector counts as halting (< 5 km/h) in its zone
            (the last 100 m before the stop line)
    p       share of vehicles that are probes (estimated penetration, see SensorSuite)

with two capacities taken from the network (JAM_SPACING_M = 7 m per stopped car):

    C_zone  cars that fit in the detector zone of a lane    = E2 length / 7 m
    C_lane  cars that fit on the whole approach (all lanes) = sum(lane length) / 7 m

A second is *suspicious* if one of these tests fails:

    1. storage      H > C_lane + 2
                    more stopped phones than cars fit on the road: impossible.
    2. detector     H > Q_det + max(3, 0.25 * Q_det)                (zone not full only)
                    probes are a subset of the cars, and a queue that does not fill the
                    detector zone lies inside it, so H cannot exceed Q_det by much.
    3. statistical  H > p*Q_det + Z * sqrt(p*(1-p)*Q_det) + 2          (zone not full only)
                    without an attack H ~ Binomial(Q_det, p): its mean is p*Q_det and its
                    standard deviation sqrt(p*(1-p)*Q_det). Catches small attacks at low
                    coverage, where a few fake phones are scaled up a lot.

"Zone full" means some lane has occupancy >= 40 % or Q_lane >= 0.7 * C_zone: the queue may
then reach upstream of the detector, so the detector cannot confirm or deny the reports
beyond its zone. The detector also stays "unable to verify" for ZONE_MEMORY_S (60 s) after
the zone was last full: when the light turns green the front of a long queue (inside the
zone) moves off first while its tail beyond the zone is still stopped, so for a while the
probes rightly see more stopped cars than the detector. The start-up wave travels back at
about 5 m/s, so it needs up to ~60 s to reach the end of a 290 m approach. (Without this
memory the first version raised 10-30 s false alarms at 100 % coverage after long queues.)

While the zone is unverifiable the reports are split by where they claim to be:

    H_zone  stopped-probe reports inside the detector zone (a probe report carries its
            position; phantom phones claim the stop line, see SensorSuite.phantom_layout)
    H_up    the rest, upstream of the zone

and the detector still checks the part it can see:

    2'. detector     H_zone > Q_det + max(3, 0.25 * Q_det)
    3'. statistical  H_zone > p'*Q_det + Z * sqrt(p'*(1-p')*Q_det) + 2,   p' = min(1, 2 * max(p, c))
    1'. storage      H_up   > C_up + 2      C_up = cars that fit upstream of the zone

A real stopped probe in the zone is one of the cars the detector counts as halting, so
H_zone <= Q_det however long the queue is. p' allows the probes' share of one queue to be
twice the coverage: navigation users do not always queue where everyone else does (after
the earthquake bridge reopened they were re-routed onto it first and made up 75-100 % of a
jammed zone at 25 % coverage). That still flags 20 phantom phones in a full two-lane zone at
25 % coverage. The first version used only test 1
here, and on a busy arterial the zone is full or recently full most of every cycle: a
20-phone attack at 25 % coverage stayed trusted 89 % of the time. If the zone split is not
available (no vehicle ids from the detector) only test 1 is used, as before.

Hysteresis: an approach becomes untrusted after PERSIST_BAD_S suspicious seconds in a row
and trusted again after PERSIST_GOOD_S clean seconds in a row, so a single noisy second
(e.g. a queue that is discharging) does not raise an alarm and an alarm does not flicker.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from teamb.network.build import E2_LENGTH_M

JAM_SPACING_M = 7.0  # car length 4.5 m + min gap 2.5 m
STORAGE_SLACK = 2.0
DETECTOR_SLACK_ABS = 3.0
DETECTOR_SLACK_REL = 0.25
Z = 3.5
STAT_SLACK = 2.0
ZONE_FULL_OCCUPANCY = 40.0  # %
ZONE_FULL_SHARE = 0.7
ZONE_MEMORY_S = 60.0  # the detector cannot verify for this long after its zone was full
PERSIST_BAD_S = 3
PERSIST_GOOD_S = 10


@dataclass
class ApproachCheckState:
    bad: int = 0  # suspicious seconds in a row
    good: int = 0  # clean seconds in a row
    flagged: bool = False
    since: float | None = None
    test: str = ""
    last_full: float | None = None  # last time the detector zone was full


@dataclass
class AlertEpisode:
    junction: str
    approach: str
    start: float
    end: float | None = None
    test: str = ""
    max_probe_halted: int = 0


@dataclass
class CrossCheck:
    """Keeps the per-approach hysteresis state and a log of alert episodes."""

    zone_capacity: dict[str, float]  # lane -> cars that fit in its E2 zone
    approach_storage: dict[tuple[str, str], float]  # (junction, approach) -> cars that fit on it
    upstream_storage: dict[tuple[str, str], float] = field(default_factory=dict)  # ... upstream of the zones
    states: dict[tuple[str, str], ApproachCheckState] = field(default_factory=dict)
    episodes: list[AlertEpisode] = field(default_factory=list)
    _open: dict[tuple[str, str], AlertEpisode] = field(default_factory=dict)

    @classmethod
    def from_topology(cls, topology) -> "CrossCheck":
        zone, storage, upstream = {}, {}, {}
        for j in topology.tls_ids:
            for side, lanes in topology.approach_lanes[j].items():
                total = up = 0.0
                for lane in lanes:
                    length = topology.lane_length(lane)
                    zone_len = min(E2_LENGTH_M, length - 1.0)
                    zone[lane] = zone_len / JAM_SPACING_M
                    total += length / JAM_SPACING_M
                    up += (length - zone_len) / JAM_SPACING_M
                storage[(j, side)] = total
                upstream[(j, side)] = up
        return cls(zone, storage, upstream)

    def zone_full(self, lane_stats: list[tuple[str, float, float]]) -> bool:
        """lane_stats: [(lane, E2 halting count, E2 occupancy %)] for one approach."""
        return any(occ >= ZONE_FULL_OCCUPANCY or q >= ZONE_FULL_SHARE * self.zone_capacity[lane] for lane, q, occ in lane_stats)

    def unverifiable(self, t: float, key, lane_stats: list[tuple[str, float, float]]) -> bool:
        """True if the detector cannot confirm the probe queue now: its zone is full, or was
        full less than ZONE_MEMORY_S ago (a discharging queue's tail may still be stopped)."""
        st = self.state(key)
        if self.zone_full(lane_stats):
            st.last_full = t
            return True
        return st.last_full is not None and t - st.last_full < ZONE_MEMORY_S

    def suspicious(
        self, key, probe_halted: float, det_queue: float, zone_full: bool, penetration: float,
        zone_halted: float | None = None, zone_penetration: float | None = None,
    ) -> str:
        """Name of the first failed test, or '' if the reports look plausible. `zone_halted`
        (H_zone) enables the zone-full tests, with `zone_penetration` (p', default p) in the
        statistical one; None keeps only the storage test there."""
        h, q = probe_halted, det_queue
        if h > self.approach_storage[key] + STORAGE_SLACK:
            return "storage"
        if zone_full:
            if zone_halted is None:
                return ""
            h = zone_halted
            if zone_penetration is not None:
                penetration = zone_penetration
        if h > q + max(DETECTOR_SLACK_ABS, DETECTOR_SLACK_REL * q):
            return "detector"
        p = min(1.0, max(0.0, penetration))
        if h > p * q + Z * math.sqrt(p * (1 - p) * q) + STAT_SLACK:
            return "statistical"
        if zone_full and probe_halted - zone_halted > self.upstream_storage.get(key, float("inf")) + STORAGE_SLACK:
            return "storage"
        return ""

    def update(self, t: float, key, failed_test: str, probe_halted: int) -> bool:
        """Advance the hysteresis for one approach; returns True while it is trusted."""
        st = self.states.setdefault(key, ApproachCheckState())
        if failed_test:
            st.bad += 1
            st.good = 0
            if not st.flagged and st.bad >= PERSIST_BAD_S:
                st.flagged, st.since, st.test = True, t, failed_test
                ep = AlertEpisode(key[0], key[1], start=t, test=failed_test)
                self._open[key] = ep
                self.episodes.append(ep)
        else:
            st.good += 1
            st.bad = 0
            if st.flagged and st.good >= PERSIST_GOOD_S:
                st.flagged = False
                ep = self._open.pop(key, None)
                if ep is not None:
                    ep.end = t
        if st.flagged and key in self._open:
            ep = self._open[key]
            ep.max_probe_halted = max(ep.max_probe_halted, int(probe_halted))
        return not st.flagged

    def state(self, key) -> ApproachCheckState:
        return self.states.setdefault(key, ApproachCheckState())
