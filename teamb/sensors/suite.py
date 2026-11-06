"""SensorSuite: what the controllers are allowed to know, built every simulated second.

See the package docstring (teamb/sensors/__init__.py) for the observation format.

Per-step cost: all SUMO values come from the shared subscription feed (feed.py), so one
`observe()` makes no TraCI round trips; it is plain Python over ~200 vehicles.

Coverage changes mid-run (the twin's slider): a vehicle shares data or not for its whole
trip, decided when it departs, so after a change the probes on the road are a mix of
vehicles chosen under the old and the new coverage for several minutes. Every probe
therefore keeps the coverage that was in effect at its departure (its cohort), and the
estimates weight each probe by it:

    queue_est      = sum over halted reporting probes of 1 / c_i   (+ fake reports / c)
    flow_est_vph   = sum over cohorts of probe crossings / c_i, per hour
    penetration    = (sum over probe crossings of c / c_i + PRIOR * c) / (loop crossings + PRIOR)
    queue_est_adj  = (sum over halted probes of c / c_i + fake) / penetration

where c is the current coverage. With a constant coverage every c_i = c and these are
exactly the plain formulas (halted / c, crossings / c, ...). The cross-check's statistical
test uses the highest cohort coverage still on the road, so genuine reports of a
high-coverage cohort are not taken for fake ones after the coverage was lowered.
"""
from __future__ import annotations

import math
import random

import traci.constants as tc

from teamb.network.build import E2_LENGTH_M, edge_kind
from teamb.sensors.crosscheck import CrossCheck
from teamb.sensors.feed import E2_VARS, HALT_SPEED, get_feed
from teamb.sensors.logs import ESTIMATION_EVERY_S, DetectorIntervals, RollingCount
from teamb.sensors.sampling import ProbeSelector, parse_sampling

PHANTOM_SPACING_M = 7.5  # fake phones claim a queue of stopped cars, one every 7.5 m ...
PHANTOM_FRONT_M = 4.0  # ... starting 4 m before the stop line
FLOW_WINDOW_S = 300.0  # flows are counted over the last 5 minutes
PENETRATION_WINDOW_S = 900.0  # penetration is estimated over the last 15 minutes
PENETRATION_PRIOR = 10.0  # pseudo-vehicles that pull a thin estimate toward the nominal coverage
PENETRATION_BAND = 2.0  # the per-approach estimate stays within [c / 2, 2c] (wider for approach_biased:r > 2)


def _clamp_coverage(value: float) -> float:
    return max(0.01, min(1.0, float(value)))


def _point_back(shape, d: float) -> tuple[float, float]:
    """The point `d` metres back from the end of a lane polyline (its start if shorter)."""
    rem = d
    for i in range(len(shape) - 1, 0, -1):
        (x0, y0), (x1, y1) = shape[i - 1], shape[i]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg > 0 and rem <= seg:
            f = rem / seg
            return x1 - (x1 - x0) * f, y1 - (y1 - y0) * f
        rem -= seg
    return tuple(shape[0])


def phantom_layout(topology, junction: str, approach: str, n: int) -> dict:
    """Where `n` fake phones on one approach claim to stand: exactly n phones, spread over the
    lanes round-robin, PHANTOM_SPACING_M apart from PHANTOM_FRONT_M before the stop line, at
    most as many per lane as fit on it. Phones that fit nowhere are counted in `hidden`.

    Returns {"lanes": {lane: [distance from the stop line, m]}, "positions": [[x, y]],
    "shown": int, "hidden": int}. Pure (no TraCI): used for the twin and the cross-check."""
    lanes = list(topology.approach_lanes[junction][approach])
    capacity = [max(0, int((topology.lane_length(l) - PHANTOM_FRONT_M) // PHANTOM_SPACING_M) + 1) for l in lanes]
    counts = [0] * len(lanes)
    hidden = 0
    lane = 0
    for _ in range(max(0, int(n))):
        for step in range(len(lanes)):  # next lane (round-robin) that still has room
            k = (lane + step) % len(lanes)
            if counts[k] < capacity[k]:
                counts[k] += 1
                lane = k + 1
                break
        else:
            hidden += 1
    distances = {l: [PHANTOM_FRONT_M + i * PHANTOM_SPACING_M for i in range(c)] for l, c in zip(lanes, counts)}
    positions = []
    for l, ds in distances.items():
        shape = topology.net.getLane(l).getShape()
        for d in ds:
            x, y = _point_back(shape, d)
            positions.append([round(x, 2), round(y, 2)])
    return {"lanes": distances, "positions": positions, "shown": len(positions), "hidden": hidden}


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
        band = max(PENETRATION_BAND, self.spec.arterial_ratio if self.spec.mechanism == "approach_biased" else 0.0)
        self._band_low, self._band_high = 1.0 / band, band
        self.probes: dict[str, float] = {}  # probe vehicle id -> coverage when it departed (its cohort)
        self._cohorts: dict[float, int] = {}  # cohort coverage -> probes of it in the network
        self.fake: dict[tuple[str, str], int] = {}  # (junction, approach) -> phantom reports
        self._phantom_cache: dict[tuple[str, str], tuple[int, dict]] = {}
        self.attacks: list[dict] = []  # attack log for the evaluation (never shown to controllers)
        self._attack_excess: list[float] = []  # per attack: sum of (fused queue - true queue) while it ran
        self._alerts: list[dict] = []
        self._t = 0.0  # time of the last observation
        self._now = 0.0  # latest simulation time we heard of
        self._last_obs: dict | None = None
        self._last_key = None
        self.step_t: float | None = None  # time of the last on_step and its vehicle lists
        self.step_departed: tuple = ()
        self.step_arrived: tuple = ()

        self.feed = get_feed(conn, topology)
        self.feed.sensors = self
        self.check = CrossCheck.from_topology(topology)
        self._zone_len = {
            lane: min(E2_LENGTH_M, topology.lane_length(lane) - 1.0) for lane in self.feed.detector_lanes
        }
        self._zone_ids_ok = self._subscribe_zone_ids()

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
        # probe stop-line crossings per approach, per cohort coverage (flow window)
        self._probe_counts: dict[tuple, dict[float, RollingCount]] = {k: {} for k in keys}
        self._true_prev: dict[tuple, set] = {k: set() for k in keys}
        self._true_counts = {k: RollingCount(FLOW_WINDOW_S) for k in keys}
        self._pen_probe: dict[tuple, dict[float, RollingCount]] = {k: {} for k in keys}  # same, 15 min window
        self._pen_loop = {k: RollingCount(PENETRATION_WINDOW_S) for k in keys}
        self.estimation: list[tuple] = []  # rows, see logs.ESTIMATION_COLUMNS
        self._next_log = 0.0
        self.intervals = DetectorIntervals(self.feed.detector_lanes)

    def _subscribe_zone_ids(self) -> bool:
        """Which vehicles are inside each E2 zone (the cross-check splits probe reports by
        position, crosscheck.py). Adds the vehicle id list to the feed's lane-area
        subscriptions; a re-subscription replaces the variable set, so the feed's own
        variables are kept in it. False if that is not possible (e.g. a stub feed)."""
        if callable(getattr(self.feed, "e2_vehicles", None)):
            return True
        try:
            lanearea = self.conn.lanearea
            for lane in self.feed.detector_lanes:
                lanearea.subscribe(f"e2_{lane}", list(E2_VARS) + [tc.LAST_STEP_VEHICLE_ID_LIST])
        except Exception:  # noqa: BLE001 - optional: without it the zone split is skipped
            return False
        return True

    def _zone_vehicles(self, lane: str):
        """Vehicle ids inside the E2 zone of `lane` this step (None if unknown)."""
        getter = getattr(self.feed, "e2_vehicles", None)
        if callable(getter):
            return getter(lane)
        results = getattr(self.feed, "_e2", None)
        if results is None:
            return None
        return (results.get(f"e2_{lane}") or {}).get(tc.LAST_STEP_VEHICLE_ID_LIST)

    # --- called by the env ------------------------------------------------
    def set_coverage(self, value: float) -> None:
        """Applies to vehicles that depart from now on (probes on the road keep their cohort)."""
        self.coverage = _clamp_coverage(value)

    def on_step(self, t: float, departed, arrived) -> None:
        self._now = t
        # kept for the scenario runtime, which runs right after us in the same step
        self.step_t, self.step_departed, self.step_arrived = t, departed, arrived
        self.feed.update(t)
        c = self.coverage
        for vid in departed:
            if self.selector.select(self.feed.origin_group(vid), c):
                self.probes[vid] = c
                self._cohorts[c] = self._cohorts.get(c, 0) + 1
        self._count(t)
        for vid in arrived:  # after counting, so a probe's cohort is known when it crosses
            cohort = self.probes.pop(vid, None)
            if cohort is not None:
                left = self._cohorts[cohort] - 1
                if left:
                    self._cohorts[cohort] = left
                else:
                    del self._cohorts[cohort]

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
        c_now = self.coverage
        for j, side, lanes, _ in self._approaches:
            key = (j, side)
            on_approach = {vid for lane in lanes for vid, _ in feed.on_lane(lane)}
            present = on_approach & probes.keys()
            # vehicles that were on the approach a second ago and are not any more crossed the stop
            # line. Probes are followed as trajectories, so silent (non-reporting) seconds do not matter.
            left = self._probe_prev[key] - present
            left_all = len(self._true_prev[key] - on_approach)
            self._probe_prev[key], self._true_prev[key] = present, on_approach
            crossed: dict[float, int] = {}
            for vid in left:
                cohort = probes.get(vid, c_now)
                crossed[cohort] = crossed.get(cohort, 0) + 1
            self._add_cohort_counts(self._probe_counts[key], t, crossed, FLOW_WINDOW_S)
            self._add_cohort_counts(self._pen_probe[key], t, crossed, PENETRATION_WINDOW_S)
            self._true_counts[key].add(t, left_all)
            self._pen_loop[key].add(t, sum(loop_new[lane] for lane in lanes))

    def _add_cohort_counts(self, windows: dict[float, RollingCount], t: float, crossed: dict[float, int], window_s: float) -> None:
        """Add this second's crossings per cohort; windows of old cohorts expire when empty.
        The current coverage always has a window, so a constant coverage keeps exactly one."""
        c_now = self.coverage
        if c_now not in windows:
            windows[c_now] = RollingCount(window_s)
        for cohort in list(windows):
            rc = windows[cohort]
            rc.add(t, crossed.get(cohort, 0))
            if not rc.total and cohort != c_now:
                del windows[cohort]
        for cohort, n in crossed.items():
            if cohort not in windows:
                windows[cohort] = rc = RollingCount(window_s)
                rc.add(t, n)

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
            zone_full = self.check.unverifiable(t, key, lane_stats)  # full now or in the last 60 s
            probe, truth, extra = self._probe(t, key, lanes, split=zone_full)
            failed = self.check.suspicious(
                key, probe["halted"], det["queue"], zone_full, extra["p_test"], extra["zone_halted"], extra["p_zone"]
            )
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
            fused = self._fuse(det, probe, zone_full, trusted, self.check.approach_storage[key],
                               extra["upstream_eff"], self.check.upstream_storage.get(key))
            if key in self.fake:
                self._account_attack(key, trusted, fused["queue"], truth[0])
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
    def _probe(self, t: float, key: tuple, lanes: tuple, split: bool = False):
        """(probe block, ground truth (halted, count, flow veh/h), internals for the cross-check
        and the fusion) for one approach. Each probe is weighted by the coverage of its cohort
        (module doc). With `split`, halted reports are also divided into inside the detector
        zone and upstream of it (crosscheck.py), if the zone's vehicle ids are known."""
        feed, probes = self.feed, self.probes
        zones = None
        if split and self._zone_ids_ok:
            zones = {}
            for lane in lanes:
                ids = self._zone_vehicles(lane)
                if ids is None:
                    zones = None
                    break
                zones[lane] = ids if isinstance(ids, (set, frozenset)) else set(ids)
        zone_halted = 0
        upstream_by: dict[float, int] = {}  # cohort coverage -> halted reports upstream of the zone
        speed_biased = self.spec.mechanism == "speed_biased"
        p_stopped = self.spec.stopped_report_prob
        rnd = self.report_rng.random
        reported = halted = true_halted = true_count = 0
        speed_sum = 0.0
        reported_by: dict[float, int] = {}  # cohort coverage -> reports this second
        halted_by: dict[float, int] = {}  # cohort coverage -> halted reports this second
        for lane in lanes:
            for vid, v in feed.on_lane(lane):
                true_count += 1
                stopped = v < HALT_SPEED
                true_halted += stopped
                cohort = probes.get(vid)
                if cohort is not None:
                    if speed_biased and stopped and rnd() >= p_stopped:
                        continue  # this stopped phone stays silent this second
                    reported += 1
                    speed_sum += v
                    reported_by[cohort] = reported_by.get(cohort, 0) + 1
                    if stopped:
                        halted += 1
                        halted_by[cohort] = halted_by.get(cohort, 0) + 1
                        if zones is not None:
                            if vid in zones[lane]:
                                zone_halted += 1
                            else:
                                upstream_by[cohort] = upstream_by.get(cohort, 0) + 1
        c = self.coverage
        fake = self.fake.get(key, 0)
        if fake:  # phantom phones claim to be ordinary probes of the current coverage
            reported_by[c] = reported_by.get(c, 0) + fake
            halted_by[c] = halted_by.get(c, 0) + fake
            if zones is not None:  # ... standing where phantom_layout puts them
                layout = self._phantoms(key)
                in_zone = sum(1 for lane, ds in layout["lanes"].items() for d in ds if d <= self._zone_len.get(lane, E2_LENGTH_M))
                zone_halted += in_zone
                upstream_by[c] = upstream_by.get(c, 0) + fake - in_zone
        # penetration = probe crossings (in current-coverage units) / loop counts, shrunk toward c
        crossings = sum((rc.total * (c / cohort) for cohort, rc in self._pen_probe[key].items()), 0.0)
        pen = (crossings + PENETRATION_PRIOR * c) / (self._pen_loop[key].total + PENETRATION_PRIOR)
        # The crossers of one approach are not a random sample right after a closure: navigation
        # users were re-routed away, so the first 30 vehicles back can all be non-probes. Keep the
        # estimate in a band around the coverage (it only has to absorb sampling bias).
        pen = min(1.0, max(0.01, self._band_low * c, min(self._band_high * c, pen)))
        n = reported + fake
        halted_all = halted + fake
        halted_eff = sum((k * (c / cohort) for cohort, k in halted_by.items()), 0.0)
        block = {
            "queue_est": round(sum((k / cohort for cohort, k in halted_by.items()), 0.0), 2),
            "n": n,
            "halted": halted_all,
            "speed": round(speed_sum / n, 2) if n else None,
            "flow_est_vph": round(sum((rc.rate_vph(t) / cohort for cohort, rc in self._probe_counts[key].items()), 0.0), 1),
            "queue_est_adj": round(halted_eff / pen, 2),
            "penetration_est": round(pen, 3),
            "n_est": round(sum((k / cohort for cohort, k in reported_by.items()), 0.0), 2),
        }
        # The statistical test compares raw reports with p * Q_det. It never assumes fewer probes
        # than the coverage: an estimate below c is noise or a non-random set of crossers (after a
        # closure, early in a run), and a too-low p turns genuine reports into alarms. While probes
        # of a cohort with a higher coverage are still on the road, the share can be that much higher.
        c_max = max(self._cohorts, default=c)
        p_test = max(pen, c) if c_max <= c else min(1.0, max(pen, c) * c_max / c)
        truth = (true_halted, true_count, self._true_counts[key].rate_vph(t))
        extra = {"p_test": round(p_test, 3), "zone_halted": None, "upstream_eff": None, "p_zone": None}
        if zones is not None:
            extra["zone_halted"] = zone_halted
            # one queue may hold up to PENETRATION_BAND x the coverage in probes (crosscheck.py)
            extra["p_zone"] = round(min(1.0, self._band_high * p_test), 3)
            # halted cars upstream of the zone, estimated from the probes there
            extra["upstream_eff"] = sum((k * (c / cohort) for cohort, k in upstream_by.items()), 0.0) / pen
        return block, truth, extra

    @staticmethod
    def _fuse(
        det: dict, probe: dict, zone_full: bool, trusted: bool, storage: float = float("inf"),
        upstream: float | None = None, upstream_storage: float | None = None,
    ) -> dict:
        """Detector queue; when the detector zone is (or was, in the last minute) full the queue
        may be longer than the detector can see, so trusted probes may extend it, but never past
        what fits on the approach (`storage`, cars).

        With the zone split (`upstream` = halted cars beyond the zone estimated from the probes
        there) the detector counts the zone and the probes only add what lies beyond it, up to
        `upstream_storage`. Reports claiming the zone (where phantom phones stand) then cannot
        inflate the queue, even while an attack is not detected. Without it: max(detector,
        queue_est_adj)."""
        if zone_full and trusted:
            if upstream is not None:
                extra = upstream if upstream_storage is None else min(upstream, upstream_storage)
                queue = min(det["queue"] + extra, max(storage, det["queue"]))
            else:
                queue = max(det["queue"], min(probe["queue_est_adj"], storage))
            return {"queue": round(queue, 2), "flow_vph": det["flow_vph"], "source": "detector+probe"}
        return {"queue": det["queue"], "flow_vph": det["flow_vph"], "source": "detector"}

    # --- fake-data attack (security test) ---------------------------------
    def inject_fake_reports(self, junction: str, approach: str, n: int) -> None:
        key = (junction, approach)
        if key in self.fake:
            self._end_attack(key)
        self.fake[key] = int(n)
        self.attacks.append(
            {"junction": junction, "approach": approach, "n": int(n), "start": self._now, "end": None,
             "observed_s": 0, "trusted_s": 0, "trusted_share": None, "fused_excess_mean": None}
        )
        self._attack_excess.append(0.0)
        self.feed.events.append({"t": self._now, "type": "attack_started", "junction": junction, "approach": approach, "n": int(n)})

    def clear_fake_reports(self) -> None:
        for key in list(self.fake):
            self._end_attack(key)
        self.fake.clear()

    def _account_attack(self, key, trusted: bool, fused_queue: float, true_queue: int) -> None:
        """How much the running attack got through (evaluation only, never observed): seconds
        it was observed, seconds the attacked approach stayed trusted, and the mean excess of
        the fused queue over the true queue while it ran."""
        for i in range(len(self.attacks) - 1, -1, -1):
            a = self.attacks[i]
            if (a["junction"], a["approach"]) == key and a["end"] is None:
                a["observed_s"] += 1
                a["trusted_s"] += int(trusted)
                self._attack_excess[i] += fused_queue - true_queue
                a["trusted_share"] = round(a["trusted_s"] / a["observed_s"], 3)
                a["fused_excess_mean"] = round(self._attack_excess[i] / a["observed_s"], 2)
                return

    def _end_attack(self, key) -> None:
        for a in self.attacks:
            if (a["junction"], a["approach"]) == key and a["end"] is None:
                a["end"] = self._now
        self.feed.events.append({"t": self._now, "type": "attack_stopped", "junction": key[0], "approach": key[1]})

    def _phantoms(self, key) -> dict:
        n = self.fake.get(key, 0)
        cached = self._phantom_cache.get(key)
        if cached is None or cached[0] != n:
            cached = self._phantom_cache[key] = (n, phantom_layout(self.topo, key[0], key[1], n))
        return cached[1]

    def phantom_positions(self) -> list[list[float]]:
        """Where the fake 'stopped cars' claim to be — for the twin. Exactly the injected
        number of phones, all on the approach lanes; phones that do not fit on the road are
        not drawn (see phantom_summary)."""
        out = []
        for key in self.fake:
            out.extend(self._phantoms(key)["positions"])
        return out

    def phantom_summary(self) -> list[dict]:
        """Per attacked approach: phones injected, drawn, and not drawn because they do not
        fit on the road (the twin can label those as '+N more')."""
        return [
            {"junction": j, "approach": side, "n": n, "shown": self._phantoms((j, side))["shown"], "hidden": self._phantoms((j, side))["hidden"]}
            for (j, side), n in self.fake.items()
        ]

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
