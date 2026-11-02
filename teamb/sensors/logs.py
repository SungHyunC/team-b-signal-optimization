"""Small building blocks for the sensors: rolling counts and the evaluation logs.

The logs are for evaluation only. They contain ground truth next to the estimates,
so they are never part of an observation a controller sees.
"""
from __future__ import annotations

from collections import deque

# One row every ESTIMATION_EVERY_S per signalized approach (see docs/roles/data-evaluation.md).
ESTIMATION_EVERY_S = 5.0
ESTIMATION_COLUMNS = (
    "t",                    # s, simulation time
    "junction",             # J1..J4
    "approach",             # W/E/N/S, side the traffic comes from
    "kind",                 # arterial / cross
    "attacked",             # 1 if fake reports were being injected on this approach
    "trusted",              # 1 if the cross-check trusted the probe data at this second
    "n_reports",            # probe reports this second (incl. fake ones)
    "true_queue",           # ground truth: halted vehicles (< 0.1 m/s) on the whole approach
    "true_count",           # ground truth: vehicles on the whole approach
    "true_flow_vph",        # ground truth: vehicles that crossed the stop line, last 5 min, veh/h
    "det_queue",            # E2 detector halting count (last 100 m only)
    "det_flow_vph",         # E1 loop flow, last 5 min, veh/h
    "probe_queue_est",      # halted probe reports / coverage (the contract's queue_est)
    "probe_queue_adj",      # halted probe reports / estimated penetration
    "probe_flow_est_vph",   # probes that crossed the stop line / coverage, veh/h
    "fused_queue",          # detector, extended by probes when the detector zone is full
    "penetration_est",      # estimated share of probes (probe crossings / loop counts)
)

DETECTOR_INTERVAL_S = 60.0
DETECTOR_INTERVAL_COLUMNS = (
    "detector_id",   # e2_<lane> (the E1 loop on the same lane is e1_<lane>)
    "lane_id",
    "start_s",       # interval start, simulation time
    "end_s",         # interval end (exclusive)
    "count",         # vehicles counted by the E1 loop (25 m before the stop line)
    "flow_vph",      # count * 3600 / interval length
    "occupancy_pct", # mean E2 occupancy, %
    "speed_mps",     # vehicle-weighted mean speed in the E2 zone; empty if no vehicle was seen
    "halting_mean",  # mean number of halting vehicles in the E2 zone
    "missing_flag",  # 1 if the detector did not report (always 0 in simulation, see TODO)
    "latency_s",     # reporting delay (0 in simulation)
)


class RollingCount:
    """Number of events in the last `window_s` seconds, kept with a running total.

    rate_vph(t) = total * 3600 / span, where span = min(window, t) but at least 60 s, so the
    first minutes of a run do not produce huge rates from a handful of vehicles."""

    def __init__(self, window_s: float):
        self.window_s = window_s
        self.items: deque = deque()
        self.total = 0

    def add(self, t: float, n: int) -> None:
        if n:
            self.items.append((t, n))
            self.total += n
        limit = t - self.window_s
        items = self.items
        while items and items[0][0] < limit:
            self.total -= items.popleft()[1]

    def rate_vph(self, t: float) -> float:
        span = max(60.0, min(self.window_s, t))
        return self.total * 3600.0 / span


class DetectorIntervals:
    """Aggregates per-second detector readings into fixed intervals (default 60 s)."""

    def __init__(self, lanes, interval_s: float = DETECTOR_INTERVAL_S):
        self.interval_s = interval_s
        self.lanes = list(lanes)
        self.rows: list[tuple] = []
        self.start = 0.0
        self.steps = 0
        self._reset()

    def _reset(self) -> None:
        # lane -> [loop count, occupancy sum, speed*vehicles sum, vehicles sum, halting sum]
        self.acc = {lane: [0, 0.0, 0.0, 0, 0] for lane in self.lanes}
        self.steps = 0

    def tick(self, t: float) -> None:
        """Call once per step before `add`; closes the interval when it is over."""
        if t >= self.start + self.interval_s:
            self.close(self.start + self.interval_s)
        self.steps += 1

    def add(self, lane: str, count_new: int, occupancy: float, speed: float, vehicles: int, halting: int) -> None:
        a = self.acc.get(lane)
        if a is None:
            return
        a[0] += count_new
        a[1] += occupancy
        if vehicles > 0 and speed >= 0:
            a[2] += speed * vehicles
            a[3] += vehicles
        a[4] += halting

    def close(self, end: float) -> None:
        span = end - self.start
        if self.steps and span > 0:
            for lane, (count, occ, sv, nv, halt) in self.acc.items():
                self.rows.append(
                    (
                        f"e2_{lane}",
                        lane,
                        self.start,
                        end,
                        count,
                        round(count * 3600.0 / span, 1),
                        round(occ / self.steps, 2),
                        round(sv / nv, 2) if nv else "",
                        round(halt / self.steps, 2),
                        0,
                        0.0,
                    )
                )
        self.start = end
        self._reset()
