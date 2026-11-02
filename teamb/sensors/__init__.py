"""Sensors: infrastructure detectors and navigation-app probe vehicles.

Owner: Data & evaluation (Doyoung). This is the baseline implementation the core
needs to run; extend it, but keep the SensorSuite methods the env calls.

Observation contract (what controllers receive every step):

    {
      "t": 123.0, "coverage": 0.25, "sampling": "uniform",
      "junctions": {
        "J1": {
          "approaches": {
            "W": {
              "detector": {"queue": 4, "count": 7, "occupancy": 12.5, "speed": 3.1,
                           "flow_vph": 820.0,   # E1 loop counts over the last 5 min
                           "gap_s": 2.4},       # seconds since a loop last saw a vehicle (actuated)
              "probe":    {"queue_est": 8.0, "n": 2, "halted": 2, "speed": 0.4,
                           "flow_est_vph": 760.0,  # probes that crossed the stop line, ÷ coverage
                           "trusted": True},
              "oracle":   {...}   # only when the controller asked for "oracle"
            }, ...
          },
          "exits": {"E": {"detector": {...}}, ...}   # downstream queues (max-pressure)
        }, ...
      },
      "alerts": [{"type": "probe_detector_mismatch", "junction": "J2", "approach": "N", ...}]
    }

Probe estimates are scaled by 1/coverage, so low coverage gives noisy, possibly biased
numbers — that is the sampling-bias question from Report 1.
"""
from __future__ import annotations

import random
from collections import deque

PHANTOM_SPACING_M = 7.5
FLOW_WINDOW_S = 300.0


class SensorSuite:
    def __init__(self, conn, topology, *, coverage: float = 1.0, sampling: str = "uniform", seed: int = 0):
        self.conn = conn
        self.topo = topology
        self.coverage = max(0.01, min(1.0, float(coverage)))
        self.sampling = sampling
        self.rng = random.Random(seed * 7919 + 17)
        self.probes: set[str] = set()
        self.fake: dict[tuple[str, str], int] = {}  # (junction, approach) -> phantom reports
        self._alerts: list[dict] = []
        self._t = 0.0
        self._loop_prev: dict[str, set] = {}  # E1 loop -> vehicle ids seen last step
        self._loop_counts: dict[str, deque] = {}  # E1 loop -> (t, new vehicles)
        self._probe_prev: dict[tuple[str, str], set] = {}  # approach -> probe ids on it last step
        self._probe_counts: dict[tuple[str, str], deque] = {}  # approach -> (t, probes that left it)

    # --- called by the env ------------------------------------------------
    def set_coverage(self, value: float) -> None:
        """Applies to vehicles that depart from now on."""
        self.coverage = max(0.01, min(1.0, float(value)))

    def on_step(self, t: float, departed, arrived) -> None:
        for vid in departed:
            if self.rng.random() < self.coverage:
                self.probes.add(vid)
        for vid in arrived:
            self.probes.discard(vid)

    def is_probe(self, vid: str) -> bool:
        return vid in self.probes

    def observe(self, t: float, source: str = "detector") -> dict:
        self._alerts = []
        self._t = t
        junctions = {}
        for j in self.topo.tls_ids:
            approaches = {}
            for side, lanes in self.topo.approach_lanes[j].items():
                entry = {"detector": self._detector(lanes), "probe": self._probe(j, side, lanes)}
                entry["probe"]["trusted"] = self._check(j, side, entry)
                if source == "oracle":
                    entry["oracle"] = self._oracle(lanes)
                approaches[side] = entry
            exits = {}
            for side, edge in self.topo.exit_edges[j].items():
                lanes = self.topo.exit_lanes[j][side]
                has_detector = self.topo.downstream_junction(edge) is not None
                exits[side] = {"edge": edge, "detector": self._detector(lanes) if has_detector else None}
            junctions[j] = {"approaches": approaches, "exits": exits}
        return {"t": t, "coverage": self.coverage, "sampling": self.sampling, "junctions": junctions, "alerts": list(self._alerts)}

    # --- detectors (E2 lane-area detectors on every signalized approach) -----
    def _detector(self, lanes) -> dict:
        la, il = self.conn.lanearea, self.conn.inductionloop
        queue = count = 0
        flow = 0.0
        occ = speed = 0.0
        gap = float("inf")
        for lane in lanes:
            det = f"e2_{lane}"
            queue += la.getLastStepHaltingNumber(det)
            count += la.getLastStepVehicleNumber(det)
            occ += la.getLastStepOccupancy(det)
            speed += max(0.0, la.getLastStepMeanSpeed(det))
            loop = f"e1_{lane}"
            gap = min(gap, il.getTimeSinceDetection(loop))
            flow += self._count_loop(loop, set(il.getLastStepVehicleIDs(loop)))
        n = max(1, len(lanes))
        return {
            "queue": queue,
            "count": count,
            "occupancy": round(occ / n, 2),
            "speed": round(speed / n, 2),
            "flow_vph": round(flow, 1),
            "gap_s": round(gap, 1),
        }

    def _count_loop(self, loop: str, ids: set) -> float:
        """Flow (veh/h) at one loop over the last FLOW_WINDOW_S."""
        new = len(ids - self._loop_prev.get(loop, set()))
        self._loop_prev[loop] = ids
        return self._rolling(self._loop_counts.setdefault(loop, deque()), new)

    def _rolling(self, window: deque, new: int) -> float:
        if new:
            window.append((self._t, new))
        while window and window[0][0] < self._t - FLOW_WINDOW_S:
            window.popleft()
        span = max(60.0, min(FLOW_WINDOW_S, self._t))
        return sum(n for _, n in window) * 3600.0 / span

    # --- probes (vehicles whose navigation app shares data) -------------
    def _probe(self, j, side, lanes) -> dict:
        halted = n = 0
        speed_sum = 0.0
        present = set()
        for lane in lanes:
            for vid in self.conn.lane.getLastStepVehicleIDs(lane):
                if vid in self.probes:
                    present.add(vid)
                    v = self.conn.vehicle.getSpeed(vid)
                    n += 1
                    speed_sum += v
                    halted += v < 0.1
        key = (j, side)
        left = len(self._probe_prev.get(key, set()) - present)
        self._probe_prev[key] = present
        flow = self._rolling(self._probe_counts.setdefault(key, deque()), left) / self.coverage
        fake = self.fake.get(key, 0)
        n += fake
        halted += fake
        return {
            "queue_est": round(halted / self.coverage, 2),
            "n": n,
            "halted": halted,
            "speed": round(speed_sum / n, 2) if n else None,
            "flow_est_vph": round(flow, 1),
        }

    def _oracle(self, lanes) -> dict:
        ln = self.conn.lane
        return {
            "queue": sum(ln.getLastStepHaltingNumber(l) for l in lanes),
            "count": sum(ln.getLastStepVehicleNumber(l) for l in lanes),
        }

    def _check(self, j, side, entry) -> bool:
        """Cross-check probe reports against the loop detectors (fake-data defense)."""
        det, probe = entry["detector"], entry["probe"]
        if probe["queue_est"] > 3 * det["queue"] + 8 and det["occupancy"] < 10:
            self._alerts.append(
                {
                    "type": "probe_detector_mismatch",
                    "junction": j,
                    "approach": side,
                    "probe_queue": probe["queue_est"],
                    "detector_queue": det["queue"],
                }
            )
            return False
        return True

    # --- fake-data attack (security test) ---------------------------------
    def inject_fake_reports(self, junction: str, approach: str, n: int) -> None:
        self.fake[(junction, approach)] = int(n)

    def clear_fake_reports(self) -> None:
        self.fake.clear()

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
            for k, lane in enumerate(lanes):
                lx, ly = self.topo.net.getLane(lane).getShape()[-1]
                for i in range(per_lane):
                    d = 4.0 + i * PHANTOM_SPACING_M
                    out.append([round(lx - ux * d, 2), round(ly - uy * d, 2)])
        return out

    def alerts(self) -> list[dict]:
        return list(self._alerts)
