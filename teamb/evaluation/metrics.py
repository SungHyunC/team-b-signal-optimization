"""Traffic metrics: live numbers for the twin and the end-of-run summary.

Owner: Data & evaluation (Doyoung). Baseline implementation; keep `on_step`, `live`
and `finalize` because the env calls them.

Primary endpoint: mean vehicle delay (SUMO timeLoss, s/veh) for trips that depart
inside the measurement window [warmup, end). Unfinished trips are always reported so a
controller cannot look better by keeping cars from finishing (PERF-01).
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

EV_TYPES = ("ambulance", "firetruck")
SAMPLE_EVERY_S = 5.0
VEH_LENGTH_M = 7.0  # car length + gap, for queue length in meters


def _percentile(values, q):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


class MetricsCollector:
    def __init__(self, conn, topology, *, warmup: float = 0.0, end_time: float | None = None):
        self.conn = conn
        self.topo = topology
        self.warmup = warmup
        self.end_time = end_time
        self.depart: dict[str, float] = {}
        self.arrived = 0
        self.timeloss: dict[str, float] = {}
        self.finished_delay: list[float] = []
        self._next_sample = 0.0
        self.queue_samples: list[dict] = []  # [{t, J1: {W: q, ...}, ...}]
        self.spillback_steps = 0
        self._live: dict = {}

    def on_step(self, t: float, departed, arrived) -> None:
        for vid in departed:
            self.depart[vid] = t
        for vid in arrived:
            self.arrived += 1
            if vid in self.timeloss:
                self.finished_delay.append(self.timeloss.pop(vid))
        if t >= self._next_sample:
            self._next_sample = t + SAMPLE_EVERY_S
            self._sample(t)

    def _sample(self, t: float) -> None:
        v, ln = self.conn.vehicle, self.conn.lane
        ids = v.getIDList()
        speeds = []
        halting = 0
        for vid in ids:
            self.timeloss[vid] = v.getTimeLoss(vid)
            s = v.getSpeed(vid)
            speeds.append(s)
            halting += s < 0.1
        queues = {}
        spill = False
        for j in self.topo.tls_ids:
            queues[j] = {}
            for side, lanes in self.topo.approach_lanes[j].items():
                q = sum(ln.getLastStepHaltingNumber(l) for l in lanes)
                queues[j][side] = q
                storage = max(self.topo.lane_length(l) for l in lanes) * len(lanes)
                if q * VEH_LENGTH_M >= 0.9 * storage:
                    spill = True
        self.spillback_steps += spill
        if t >= self.warmup:
            self.queue_samples.append({"t": t, "queues": queues})
        current = [self.timeloss[x] for x in ids]
        self._live = {
            "t": t,
            "vehicles": len(ids),
            "arrived": self.arrived,
            "halting": halting,
            "mean_speed": round(sum(speeds) / len(speeds), 2) if speeds else 0.0,
            "mean_delay": round(sum(self.finished_delay[-300:]) / len(self.finished_delay[-300:]), 1)
            if self.finished_delay
            else 0.0,
            "current_mean_delay": round(sum(current) / len(current), 1) if current else 0.0,
            "queues": queues,
            "spillback": spill,
        }

    def live(self) -> dict:
        return dict(self._live)

    def finalize(self, tripinfo_path: Path, *, planned_in_window: int | None = None) -> dict:
        """Parse SUMO's tripinfo output into the run summary."""
        rows = []
        if Path(tripinfo_path).exists():
            for _, el in ET.iterparse(str(tripinfo_path)):
                if el.tag != "tripinfo":
                    continue
                arrival = float(el.get("arrival", "-1"))
                rows.append(
                    {
                        "id": el.get("id"),
                        "vtype": el.get("vType", ""),
                        "depart": float(el.get("depart", "0")),
                        "arrival": arrival,
                        "finished": arrival >= 0,
                        "duration": float(el.get("duration", "0")),
                        "time_loss": float(el.get("timeLoss", "0")),
                        "stops": int(float(el.get("waitingCount", "0"))),
                        "route_length": float(el.get("routeLength", "0")),
                    }
                )
                el.clear()
        window = [r for r in rows if r["depart"] >= self.warmup]
        done = [r for r in window if r["finished"]]
        evs = [r for r in window if r["vtype"] in EV_TYPES]
        travel = [r["duration"] for r in done]
        written = len(window)
        unfinished = written - len(done)
        if planned_in_window is not None:
            unfinished += max(0, planned_in_window - written)  # never inserted (insertion backlog)
        measured = max(1.0, (self.end_time or 0) - self.warmup) if self.end_time else None
        q_vals = [q for s in self.queue_samples for jq in s["queues"].values() for q in jq.values()]
        return {
            "completed": len(done),
            "unfinished": unfinished,
            "unfinished_pct": round(100 * unfinished / max(1, len(done) + unfinished), 2),
            "mean_delay_s": round(sum(r["time_loss"] for r in done) / len(done), 2) if done else None,
            "mean_travel_time_s": round(sum(travel) / len(travel), 2) if travel else None,
            "p95_travel_time_s": round(_percentile(travel, 0.95), 2) if travel else None,
            "stops_per_veh": round(sum(r["stops"] for r in done) / len(done), 3) if done else None,
            "throughput_veh_h": round(len(done) * 3600 / measured, 1) if measured else None,
            "mean_queue_veh": round(sum(q_vals) / len(q_vals), 2) if q_vals else None,
            "max_queue_veh": max(q_vals) if q_vals else None,
            "spillback_samples": self.spillback_steps,
            "ev_count": len(evs),
            "ev_mean_travel_time_s": round(sum(r["duration"] for r in evs if r["finished"]) / max(1, sum(r["finished"] for r in evs)), 2)
            if evs
            else None,
            "trips": rows,
        }
