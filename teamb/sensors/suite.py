"""SensorSuite: what the controllers are allowed to know, built every simulated second.

See the package docstring (teamb/sensors/__init__.py) for the observation format.

Per-step cost: all SUMO values come from the shared subscription feed (feed.py), so one
`observe()` makes no TraCI round trips; it is plain Python over ~200 vehicles.
"""
from __future__ import annotations

import random

import traci.constants as tc

from teamb.network.build import edge_kind
from teamb.sensors.crosscheck import CrossCheck
from teamb.sensors.feed import HALT_SPEED, get_feed
from teamb.sensors.logs import ESTIMATION_EVERY_S, DetectorIntervals, RollingCount
from teamb.sensors.sampling import ProbeSelector, parse_sampling

PHANTOM_SPACING_M = 7.5
FLOW_WINDOW_S = 300.0  # flows are counted over the last 5 minutes
PENETRATION_WINDOW_S = 900.0  # penetration is estimated over the last 15 minutes
PENETRATION_PRIOR = 10.0  # pseudo-vehicles that pull a thin estimate toward the nominal coverage


def _clamp_coverage(value: float) -> float:
    return max(0.01, min(1.0, float(value)))


class SensorSuite:
    def __init__(self, conn, topology, *, coverage: float = 1.0, sampling: str = "uniform", seed: int = 0):
        self.conn = conn
        self.topo = topology
        self.coverage = _clamp_coverage(coverage)
        self.spec = parse_sampling(sampling)
        self.sampling = self.spec.label
        self.rng = random.Random(seed * 7919 + 17)  # who is a probe (same stream as the first version)
        self.report_rng = random.Random(seed * 104729 + 3)  # when a stopped probe reports (speed_biased)
        self.selector = ProbeSelector(self.spec, self.rng)
        self.probes: set[str] = set()
        self.fake: dict[tuple[str, str], int] = {}  # (junction, approach) -> phantom reports
        self.attacks: list[dict] = []  # attack log for the evaluation (never shown to controllers)
        self._alerts: list[dict] = []
        self._t = 0.0  # time of the last observation
        self._now = 0.0  # latest simulation time we heard of
        self._last_obs: dict | None = None
        self._last_key = None

        self.feed = get_feed(conn, topology)
        self.feed.sensors = self
        self.check = CrossCheck.from_topology(topology)

        # static description of every signalized approach and exit
        self._approaches = []  # (junction, side, lanes, kind)
        self._exits = {}  # junction -> [(side, edge, lanes, has_detector)]
        for j in topology.tls_ids:
            for side, lanes in topology.approach_lanes[j].items():
                kind = "arterial" if edge_kind(topology.approach_edges[j][side]) == "arterial" else "cross"
                self._approaches.append((j, side, tuple(lanes), kind))
            self._exits[j] = [
                (side, edge, tuple(topology.exit_lanes[j][side]), topology.downstream_junction(edge) is not None)
                for side, edge in topology.exit_edges[j].items()
            ]
        keys = [(j, side) for j, side, _, _ in self._approaches]
        self._loop_prev: dict[str, set] = {}
        self._loop_counts = {lane: RollingCount(FLOW_WINDOW_S) for lane in self.feed.detector_lanes}
        self._probe_prev: dict[tuple, set] = {k: set() for k in keys}
        self._probe_counts = {k: RollingCount(FLOW_WINDOW_S) for k in keys}
        self._true_prev: dict[tuple, set] = {k: set() for k in keys}
        self._true_counts = {k: RollingCount(FLOW_WINDOW_S) for k in keys}
        self._pen_probe = {k: RollingCount(PENETRATION_WINDOW_S) for k in keys}
        self._pen_loop = {k: RollingCount(PENETRATION_WINDOW_S) for k in keys}
        self.estimation: list[tuple] = []  # rows, see logs.ESTIMATION_COLUMNS
        self._next_log = 0.0
        self.intervals = DetectorIntervals(self.feed.detector_lanes)

    # --- called by the env ------------------------------------------------
    def set_coverage(self, value: float) -> None:
        """Applies to vehicles that depart from now on."""
        self.coverage = _clamp_coverage(value)

    def on_step(self, t: float, departed, arrived) -> None:
        self._now = t
        self.feed.update(t)
        for vid in departed:
            if self.selector.select(self.feed.origin_group(vid), self.coverage):
                self.probes.add(vid)
        for vid in arrived:
            self.probes.discard(vid)
        self._count(t)

    def _count(self, t: float) -> None:
        """Per-second counting, done here (not in observe) so that flows stay right even if a
        caller observes less often than every second (e.g. fast_env.TrainEnv)."""
        feed, probes = self.feed, self.probes
        self.intervals.tick(t)
        loop_new: dict[str, int] = {}
        for lane in feed.detector_lanes:
            ids = set(feed.e1(lane, tc.LAST_STEP_VEHICLE_ID_LIST))
            new = len(ids - self._loop_prev.get(lane, set()))
            self._loop_prev[lane] = ids
            self._loop_counts[lane].add(t, new)
            loop_new[lane] = new
            self.intervals.add(
                lane, new,
                feed.e2(lane, tc.LAST_STEP_OCCUPANCY), feed.e2(lane, tc.LAST_STEP_MEAN_SPEED),
                int(feed.e2(lane, tc.LAST_STEP_VEHICLE_NUMBER)), int(feed.e2(lane, tc.LAST_STEP_VEHICLE_HALTING_NUMBER)),
            )
        for j, side, lanes, _ in self._approaches:
            key = (j, side)
            on_approach = {vid for lane in lanes for vid, _ in feed.on_lane(lane)}
            present = on_approach & probes
            # vehicles that were on the approach a second ago and are not any more crossed the stop
            # line. Probes are followed as trajectories, so silent (non-reporting) seconds do not matter.
            left_probes = len(self._probe_prev[key] - present)
            left_all = len(self._true_prev[key] - on_approach)
            self._probe_prev[key], self._true_prev[key] = present, on_approach
            self._probe_counts[key].add(t, left_probes)
            self._true_counts[key].add(t, left_all)
            self._pen_probe[key].add(t, left_probes)
            self._pen_loop[key].add(t, sum(loop_new[lane] for lane in lanes))

    def is_probe(self, vid: str) -> bool:
        return vid in self.probes

    def observe(self, t: float, source: str = "detector") -> dict:
        if self._last_key == (t, source) and self._last_obs is not None:
            return self._last_obs  # asked twice in the same second: same answer, no double counting
        self.feed.update(t)
        self._t = t
        self._now = max(self._now, t)
        alerts: list[dict] = []
        log_now = t >= self._next_log
        if log_now:
            self._next_log = t + ESTIMATION_EVERY_S
        cache: dict = {}
        junctions: dict = {}
        for j, side, lanes, kind in self._approaches:
            key = (j, side)
            det, lane_stats = self._detector(lanes, cache)
            probe, truth = self._probe(t, key, lanes)
            zone_full = self.check.unverifiable(t, key, lane_stats)  # full now or in the last 60 s
            failed = self.check.suspicious(key, probe["halted"], det["queue"], zone_full, probe["penetration_est"])
            trusted = self.check.update(t, key, failed, probe["halted"])
            probe["trusted"] = trusted
            if not trusted:
                st = self.check.state(key)
                alerts.append(
                    {
                        "type": "probe_detector_mismatch",
                        "junction": j,
                        "approach": side,
                        "probe_queue": probe["queue_est"],
                        "detector_queue": det["queue"],
                        "probe_halted": probe["halted"],
                        "test": st.test,
                        "since": st.since,
                    }
                )
            fused = self._fuse(det, probe, zone_full, trusted)
            entry = {"detector": det, "probe": probe, "fused": fused}
            if source == "oracle":
                entry["oracle"] = {"queue": truth[0], "count": truth[1]}
            junctions.setdefault(j, {"approaches": {}, "exits": {}})["approaches"][side] = entry
            if log_now:
                self.estimation.append(
                    (
                        t, j, side, kind, int(key in self.fake), int(trusted), probe["n"],
                        truth[0], truth[1], round(truth[2], 1), det["queue"], det["flow_vph"],
                        probe["queue_est"], probe["queue_est_adj"], probe["flow_est_vph"],
                        fused["queue"], probe["penetration_est"],
                    )
                )
        for j, exits in self._exits.items():
            out = junctions.setdefault(j, {"approaches": {}, "exits": {}})["exits"]
            for side, edge, lanes, has_detector in exits:
                out[side] = {"edge": edge, "detector": self._detector(lanes, cache)[0] if has_detector else None}
        self._alerts = alerts
        obs = {"t": t, "coverage": self.coverage, "sampling": self.sampling, "junctions": junctions, "alerts": list(alerts)}
        self._last_obs, self._last_key = obs, (t, source)
        return obs

    # --- detectors (E2 lane-area detectors + E1 loops on every signalized approach) ----
    def _detector(self, lanes: tuple, cache: dict):
        """(detector block, [(lane, halting, occupancy)]) for a set of lanes."""
        if lanes in cache:
            return cache[lanes]
        feed = self.feed
        queue = count = 0
        flow = occ = speed = 0.0
        gap = float("inf")
        lane_stats = []
        for lane in lanes:
            q = int(feed.e2(lane, tc.LAST_STEP_VEHICLE_HALTING_NUMBER))
            o = feed.e2(lane, tc.LAST_STEP_OCCUPANCY)
            queue += q
            count += int(feed.e2(lane, tc.LAST_STEP_VEHICLE_NUMBER))
            occ += o
            speed += max(0.0, feed.e2(lane, tc.LAST_STEP_MEAN_SPEED))
            gap = min(gap, feed.e1(lane, tc.LAST_STEP_TIME_SINCE_DETECTION))
            window = self._loop_counts.get(lane)
            flow += window.rate_vph(self._t) if window else 0.0
            lane_stats.append((lane, q, o))
        k = max(1, len(lanes))
        block = {
            "queue": queue,
            "count": count,
            "occupancy": round(occ / k, 2),
            "speed": round(speed / k, 2),
            "flow_vph": round(flow, 1),
            "gap_s": round(gap, 1),
        }
        cache[lanes] = (block, lane_stats)
        return cache[lanes]

    # --- probes (vehicles whose navigation app shares data) -------------------
    def _probe(self, t: float, key: tuple, lanes: tuple):
        """(probe block, ground truth (halted, count, flow veh/h)) for one approach."""
        feed, probes = self.feed, self.probes
        speed_biased = self.spec.mechanism == "speed_biased"
        p_stopped = self.spec.stopped_report_prob
        rnd = self.report_rng.random
        reported = halted = true_halted = true_count = 0
        speed_sum = 0.0
        for lane in lanes:
            for vid, v in feed.on_lane(lane):
                true_count += 1
                stopped = v < HALT_SPEED
                true_halted += stopped
                if vid in probes:
                    if speed_biased and stopped and rnd() >= p_stopped:
                        continue  # this stopped phone stays silent this second
                    reported += 1
                    speed_sum += v
                    halted += stopped
        c = self.coverage
        # penetration = probe crossings / loop counts, shrunk toward c while counts are small
        pen = (self._pen_probe[key].total + PENETRATION_PRIOR * c) / (self._pen_loop[key].total + PENETRATION_PRIOR)
        pen = min(1.0, max(0.01, pen))
        fake = self.fake.get(key, 0)
        n = reported + fake
        halted_all = halted + fake
        block = {
            "queue_est": round(halted_all / c, 2),
            "n": n,
            "halted": halted_all,
            "speed": round(speed_sum / n, 2) if n else None,
            "flow_est_vph": round(self._probe_counts[key].rate_vph(t) / c, 1),
            "queue_est_adj": round(halted_all / pen, 2),
            "penetration_est": round(pen, 3),
        }
        truth = (true_halted, true_count, self._true_counts[key].rate_vph(t))
        return block, truth

    @staticmethod
    def _fuse(det: dict, probe: dict, zone_full: bool, trusted: bool) -> dict:
        """Detector queue; when the detector zone is (or was, in the last minute) full the queue
        may be longer than the detector can see, so trusted probes may extend it."""
        if zone_full and trusted:
            return {"queue": round(max(det["queue"], probe["queue_est_adj"]), 2), "flow_vph": det["flow_vph"], "source": "detector+probe"}
        return {"queue": det["queue"], "flow_vph": det["flow_vph"], "source": "detector"}

    # --- fake-data attack (security test) ---------------------------------
    def inject_fake_reports(self, junction: str, approach: str, n: int) -> None:
        key = (junction, approach)
        if key in self.fake:
            self._end_attack(key)
        self.fake[key] = int(n)
        self.attacks.append({"junction": junction, "approach": approach, "n": int(n), "start": self._now, "end": None})
        self.feed.events.append({"t": self._now, "type": "attack_started", "junction": junction, "approach": approach, "n": int(n)})

    def clear_fake_reports(self) -> None:
        for key in list(self.fake):
            self._end_attack(key)
        self.fake.clear()

    def _end_attack(self, key) -> None:
        for a in self.attacks:
            if (a["junction"], a["approach"]) == key and a["end"] is None:
                a["end"] = self._now
        self.feed.events.append({"t": self._now, "type": "attack_stopped", "junction": key[0], "approach": key[1]})

    def phantom_positions(self) -> list[list[float]]:
        """Where the fake 'stopped cars' claim to be — for the twin."""
        out = []
        for (j, side), n in self.fake.items():
            lanes = self.topo.approach_lanes[j][side]
            shape = self.topo.net.getLane(lanes[0]).getShape()
            (x0, y0), (x1, y1) = shape[-2], shape[-1]
            seg = max(1e-6, ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
            ux, uy = (x1 - x0) / seg, (y1 - y0) / seg
            per_lane = max(1, n // len(lanes))
            for lane in lanes:
                lx, ly = self.topo.net.getLane(lane).getShape()[-1]
                for i in range(per_lane):
                    d = 4.0 + i * PHANTOM_SPACING_M
                    out.append([round(lx - ux * d, 2), round(ly - uy * d, 2)])
        return out

    def alerts(self) -> list[dict]:
        return list(self._alerts)

    # --- for the evaluation -----------------------------------------------------
    def probe_shares(self) -> dict:
        """Realized share of probes among departed vehicles, by origin group and overall."""
        return self.selector.shares()

    def finish_intervals(self) -> list[tuple]:
        """Detector interval rows, including the last (partial) interval."""
        if self.intervals.steps:
            self.intervals.close(self._now + 1.0)
        return self.intervals.rows
