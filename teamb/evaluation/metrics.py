"""Traffic metrics: live numbers for the twin and the end-of-run summary.

Owner: Data & evaluation (Doyoung). The env calls ``on_step``, ``live`` and
``finalize``; keep them.

Measurement population (primary endpoint)
-----------------------------------------
Mean vehicle delay = mean SUMO ``timeLoss`` (s/veh) of the trips that DEPART inside the
measurement window [warmup, end) and FINISH before the run ends. timeLoss is the time
lost against driving at the maximum possible speed the whole way (stops, slowing,
waiting at red). Unfinished trips are always reported next to it (PERF-01), so a
controller cannot look better by keeping cars from finishing or from entering:

    unfinished     = trips still in the network at the end + trips never inserted
    unfinished_pct = 100 * unfinished / (completed + unfinished)

Other formulas are in the docstrings of the helpers (spillback.py, recovery.py,
estimation.py) and in docs/roles/data-evaluation.md.

Extra files written next to tripinfo.xml (the run directory)
------------------------------------------------------------
timeseries.csv          every 5 s: vehicles, halting, delay rate, queues, spillback, alerts
estimation.csv          every 5 s per approach: probe/detector/fused estimates vs ground truth
detector_intervals.csv  60-s detector aggregates (count, occupancy, speed)
evaluation.json         detailed breakdowns (per approach / link / event / EV trip)
"""
from __future__ import annotations

import csv
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import traci

from teamb.evaluation.estimation import headline, summarize_estimation
from teamb.evaluation.recovery import event_windows, recovery_time, union_excess
from teamb.evaluation.spillback import SpillbackMonitor
from teamb.network.build import edge_kind
from teamb.sensors.feed import HALT_SPEED, get_feed, lane_edge, origin_group
from teamb.sensors.logs import DETECTOR_INTERVAL_COLUMNS, ESTIMATION_COLUMNS

EV_TYPES = ("ambulance", "firetruck")
SAMPLE_EVERY_S = 5.0
VEH_LENGTH_M = 7.0  # car length + gap, for queue length in meters
QUEUE_WARNING_SHARE = 0.9  # queue occupancy warning at 90 % of the approach storage
EV_WINDOW_TAIL_S = 30.0  # others count as "around an EV" until 30 s after it arrived
EV_COMPARE_CUTOFF_S = 300.0  # ignore trips departing in the last 5 min for the near/far comparison
FALSE_ALARM_GRACE_S = 30.0  # alerts up to 30 s after an attack ended still count as true alerts
TIMESERIES_COLUMNS = (
    "t", "in_window", "vehicles", "halting", "mean_speed", "delay_rate", "current_mean_delay",
    "max_queue", "queue_warning", "spillback_links", "closed_edges", "attack_active",
    "untrusted_approaches", "probes",
)


def _percentile(values, q):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _r(value, digits=2):
    return None if value is None else round(value, digits)


def movement(origin_edge: str, destination_edge: str) -> str:
    """arterial_through / cross_through / turning (between arterial and cross street) / unknown."""
    if not origin_edge or not destination_edge:
        return "unknown"
    o = "arterial" if edge_kind(origin_edge) == "arterial" else "cross"
    d = "arterial" if edge_kind(destination_edge) == "arterial" else "cross"
    return f"{o}_through" if o == d else "turning"


def parse_tripinfo(path: Path) -> list[dict]:
    """One dict per trip in SUMO's tripinfo output (unfinished trips have arrival = -1)."""
    rows = []
    if not Path(path).exists():
        return rows
    for _, el in ET.iterparse(str(path)):
        if el.tag != "tripinfo":
            continue
        arrival = float(el.get("arrival", "-1"))
        finished = arrival >= 0
        depart_edge = lane_edge(el.get("departLane", "")) if el.get("departLane") else ""
        arrival_edge = lane_edge(el.get("arrivalLane", "")) if finished and el.get("arrivalLane") else ""
        rows.append(
            {
                "id": el.get("id"),
                "vtype": el.get("vType", ""),
                "depart": float(el.get("depart", "0")),
                "arrival": arrival,
                "finished": finished,
                "duration": float(el.get("duration", "0")),
                "time_loss": float(el.get("timeLoss", "0")),
                "stops": int(float(el.get("waitingCount", "0"))),
                "route_length": float(el.get("routeLength", "0")),
                "depart_delay": float(el.get("departDelay", "0")),
                "waiting_time": float(el.get("waitingTime", "0")),
                "depart_edge": depart_edge,
                "arrival_edge": arrival_edge,
                "origin": origin_group(depart_edge) if depart_edge else "",
                "movement": movement(depart_edge, arrival_edge),
            }
        )
        el.clear()
    return rows


class MetricsCollector:
    def __init__(self, conn, topology, *, warmup: float = 0.0, end_time: float | None = None):
        self.conn = conn
        self.topo = topology
        self.warmup = warmup
        self.end_time = end_time
        self.feed = get_feed(conn, topology)
        self.depart: dict[str, float] = {}
        self.arrived = 0
        self.timeloss: dict[str, float] = {}
        self.finished_delay: list[float] = []
        self._next_sample = 0.0
        self.queue_samples: list[dict] = []  # [{t, queues: {J1: {W: q, ...}, ...}}] in the window
        self.spillback_steps = 0  # samples with a queue-occupancy warning, in the window
        self.queue_warning_seconds = 0.0
        self.spill = SpillbackMonitor(topology)
        self.timeseries: list[tuple] = []
        self.teleports = 0
        self._tl_prev: dict[str, float] = {}
        self._t_prev: float | None = None
        self._t_last = 0.0
        self._live: dict = {}
        self._approaches = []  # (junction, side, lanes, storage in m, kind)
        for j in topology.tls_ids:
            for side, lanes in topology.approach_lanes[j].items():
                storage = max(topology.lane_length(l) for l in lanes) * len(lanes)
                kind = "arterial" if edge_kind(topology.approach_edges[j][side]) == "arterial" else "cross"
                self._approaches.append((j, side, tuple(lanes), storage, kind))

    def _in_window(self, t: float) -> bool:
        return t >= self.warmup and (self.end_time is None or t <= self.end_time)

    # --- every step -----------------------------------------------------------
    def on_step(self, t: float, departed, arrived) -> None:
        self.feed.update(t)
        self._t_last = t
        for vid in departed:
            self.depart[vid] = t
        for vid in arrived:
            self.arrived += 1
            if vid in self.timeloss:
                self.finished_delay.append(self.timeloss.pop(vid))
        if self._in_window(t):
            self.teleports += self.feed.teleports_started
        if t >= self._next_sample:
            self._next_sample = t + SAMPLE_EVERY_S
            self._sample(t)

    def _next_link(self, vid: str):
        try:
            links = self.conn.vehicle.getNextLinks(vid)
        except traci.TraCIException:
            return None
        return (links[0][0], links[0][5]) if links else None

    def _sample(self, t: float) -> None:
        feed = self.feed
        # seconds this sample stands for (normally SAMPLE_EVERY_S; more if a caller samples less often)
        dt = t - self._t_prev if self._t_prev is not None and t > self._t_prev else SAMPLE_EVERY_S
        snap = feed.snapshot_at(t)  # vid -> (lane position, time loss)
        speeds = [s for _, s in feed.vehicles.values()]
        halting = sum(1 for s in speeds if s < HALT_SPEED)
        total_tl = 0.0
        delta_tl = 0.0
        prev = self._tl_prev
        for vid, (_, tl) in snap.items():
            self.timeloss[vid] = tl
            total_tl += tl
            delta_tl += tl - prev.get(vid, 0.0)
        delay_rate = delta_tl / dt if self._t_prev is not None else 0.0
        self._tl_prev = {vid: tl for vid, (_, tl) in snap.items()}
        self._t_prev = t

        queues: dict = {}
        warning = False
        max_q = 0
        for j, side, lanes, storage, _ in self._approaches:
            q = sum(1 for lane in lanes for _, s in feed.on_lane(lane) if s < HALT_SPEED)
            queues.setdefault(j, {})[side] = q
            max_q = max(max_q, q)
            if q * VEH_LENGTH_M >= QUEUE_WARNING_SHARE * storage:
                warning = True
        in_window = self._in_window(t)
        if in_window:
            self.spillback_steps += warning
            self.queue_warning_seconds += dt * warning
            self.queue_samples.append({"t": t, "queues": queues})
        active = self.spill.check(feed.by_lane, snap, self._next_link, dt, in_window)

        sensors = feed.sensors
        attack = int(bool(sensors and sensors.fake))
        untrusted = sum(1 for st in sensors.check.states.values() if st.flagged) if sensors else 0
        probes = len(sensors.probes) if sensors else 0
        n = len(speeds)
        current = total_tl / len(snap) if snap else 0.0
        recent = self.finished_delay[-300:]
        self.timeseries.append(
            (t, int(in_window), n, halting, round(sum(speeds) / n, 2) if n else 0.0, round(delay_rate, 2),
             round(current, 1), max_q, int(warning), len(active), len(feed.closed_edges()), attack, untrusted, probes)
        )
        self._live = {
            "t": t,
            "vehicles": n,
            "arrived": self.arrived,
            "halting": halting,
            "mean_speed": round(sum(speeds) / n, 2) if n else 0.0,
            "mean_delay": round(sum(recent) / len(recent), 1) if recent else 0.0,
            "current_mean_delay": round(current, 1),
            "queues": queues,
            "spillback": bool(active),  # confirmed spillback (upstream blocking evidence)
            "spillback_links": list(active),
            "queue_warning": warning,  # a queue at >= 90 % of its storage (threshold only)
            "delay_rate": round(delay_rate, 2),
        }

    def live(self) -> dict:
        return dict(self._live)

    # --- end of run -------------------------------------------------------------
    def finalize(self, tripinfo_path: Path, *, planned_in_window: int | None = None, events: list[dict] | None = None) -> dict:
        """Parse SUMO's tripinfo output into the run summary (and write the extra files).

        `events`: the env's event log, if the caller has it; otherwise the events the
        feed observed itself (closures from lane permissions, attacks from the sensors)."""
        rows = parse_tripinfo(Path(tripinfo_path))
        window = [r for r in rows if r["depart"] >= self.warmup]
        done = [r for r in window if r["finished"]]
        travel = [r["duration"] for r in done]
        written = len(window)
        in_network = written - len(done)
        never_inserted = max(0, planned_in_window - written) if planned_in_window is not None else 0
        unfinished = in_network + never_inserted
        measured = max(1.0, (self.end_time or 0) - self.warmup) if self.end_time else None
        q_vals = [q for s in self.queue_samples for jq in s["queues"].values() for q in jq.values()]

        summary = {
            # --- baseline keys (PERF-01: completed and unfinished are always reported) ---
            "completed": len(done),
            "unfinished": unfinished,
            "unfinished_pct": round(100 * unfinished / max(1, len(done) + unfinished), 2),
            "mean_delay_s": _r(_mean(r["time_loss"] for r in done)),
            "mean_travel_time_s": _r(_mean(travel)),
            "p95_travel_time_s": _r(_percentile(travel, 0.95)),
            "stops_per_veh": _r(_mean(r["stops"] for r in done), 3),
            "throughput_veh_h": round(len(done) * 3600 / measured, 1) if measured else None,
            "mean_queue_veh": _r(_mean(q_vals)),
            "max_queue_veh": max(q_vals) if q_vals else None,
            "spillback_samples": self.spillback_steps,
            # --- PERF-01 detail and selection-bias checks ---
            "planned_in_window": planned_in_window,
            "inserted_in_window": written,
            "in_network_at_end": in_network,
            "never_inserted": never_inserted,
            "mean_delay_incl_unfinished_s": _r(_mean(r["time_loss"] for r in window)),
            "mean_depart_delay_s": _r(_mean(r["depart_delay"] for r in window)),
            "teleports": self.teleports,
        }
        summary.update(self._group_metrics(done))
        summary.update(self._queue_metrics())
        summary["queue_warning_s"] = round(self.queue_warning_seconds, 1)
        summary.update(self.spill.summary())
        summary.update(self._ev_metrics(window, done))
        recovery = self._recovery(events)
        summary.update(recovery["headline"])
        sensors = self.feed.sensors
        estimation = summarize_estimation(sensors.estimation, self.warmup, self.end_time) if sensors else {}
        summary.update(headline(estimation))
        alerts = self._alert_metrics(sensors) if sensors else {}
        summary.update(alerts.get("headline", {}))
        if sensors:
            shares = sensors.probe_shares()
            summary["probe_share"] = _r(shares.get("overall"), 4)
            summary["probe_share_arterial"] = _r(shares.get("arterial"), 4)
            summary["probe_share_cross"] = _r(shares.get("cross"), 4)
        detail = {
            "delay_by_movement": self._delay_by(done, "movement"),
            "queue_by_approach": self._queue_by_approach(),
            "recovery": recovery["detail"],
            "events": self._events(events),
            "estimation": estimation,
            "alerts": alerts.get("detail", {}),
            "ev_trips": summary.get("ev_trips", []),
            "spillback_by_link": summary.get("spillback_by_link", {}),
        }
        self._write_files(Path(tripinfo_path).parent, detail)
        summary["trips"] = rows
        return summary

    # --- pieces of the summary ------------------------------------------------------
    @staticmethod
    def _delay_by(done: list[dict], key: str) -> dict:
        groups: dict[str, list] = {}
        for r in done:
            groups.setdefault(r[key] or "unknown", []).append(r)
        return {
            g: {
                "n": len(rs),
                "mean_delay_s": _r(_mean(r["time_loss"] for r in rs)),
                "p95_delay_s": _r(_percentile([r["time_loss"] for r in rs], 0.95)),
                "mean_travel_time_s": _r(_mean(r["duration"] for r in rs)),
                "stops_per_veh": _r(_mean(r["stops"] for r in rs), 3),
            }
            for g, rs in sorted(groups.items())
        }

    def _group_metrics(self, done: list[dict]) -> dict:
        """Who pays? Delay of trips that start on the arterial vs on a cross street."""
        by_origin = self._delay_by(done, "origin")
        return {
            "arterial_mean_delay_s": by_origin.get("arterial", {}).get("mean_delay_s"),
            "cross_mean_delay_s": by_origin.get("cross", {}).get("mean_delay_s"),
            "arterial_p95_delay_s": by_origin.get("arterial", {}).get("p95_delay_s"),
            "cross_p95_delay_s": by_origin.get("cross", {}).get("p95_delay_s"),
            "delay_by_origin": by_origin,
        }

    def _queue_metrics(self) -> dict:
        kinds = {(j, side): kind for j, side, _, _, kind in self._approaches}
        all_q, by_kind = [], {"arterial": [], "cross": []}
        for s in self.queue_samples:
            for j, jq in s["queues"].items():
                for side, q in jq.items():
                    all_q.append(q)
                    by_kind[kinds.get((j, side), "cross")].append(q)
        return {
            "queue_p95_veh": _r(_percentile(all_q, 0.95)),
            "queue_p95_arterial_veh": _r(_percentile(by_kind["arterial"], 0.95)),
            "queue_p95_cross_veh": _r(_percentile(by_kind["cross"], 0.95)),
        }

    def _queue_by_approach(self) -> dict:
        series: dict[str, list] = {}
        for s in self.queue_samples:
            for j, jq in s["queues"].items():
                for side, q in jq.items():
                    series.setdefault(f"{j}.{side}", []).append(q)
        return {
            k: {"mean": _r(_mean(v)), "p95": _r(_percentile(v, 0.95)), "max": max(v)}
            for k, v in sorted(series.items())
        }

    def _ev_metrics(self, window: list[dict], done: list[dict]) -> dict:
        """EV travel time and the delay of everyone else around the EVs' trips.

        others_mean_delay_s: mean delay of all finished non-EV trips. Compare it between runs
        with and without preemption on the same seeds (experiments --ev-preemption on,off):
        that paired difference is the clean "extra delay for others".

        Within one run (an indication only): a non-EV trip is "near" an EV if its time in the
        network overlaps an EV trip (EV depart .. EV arrival + 30 s). Trips departing in the last
        300 s are left out (only the fast ones could finish). Per movement g (arterial_through,
        cross_through, turning): d_g = mean delay(near, g) - mean delay(not near, g), and
            ev_extra_delay_others_s = sum_g n_near,g * d_g / sum_g n_near,g
        (stratifying by movement stops long trips, which overlap EVs more often, from looking
        like EV-caused delay)."""
        evs = [r for r in window if r["vtype"] in EV_TYPES]
        others = [r for r in done if r["vtype"] not in EV_TYPES]
        out = {
            "ev_count": len(evs),
            "ev_mean_travel_time_s": None,
            "ev_mean_delay_s": None,
            "ev_unfinished": 0,
            "ev_trips": [],
            "others_mean_delay_s": _r(_mean(r["time_loss"] for r in others)),
            "others_delay_ev_window_s": None,
            "others_delay_no_ev_s": None,
            "ev_extra_delay_others_s": None,
            "others_near_ev_n": 0,
        }
        if not evs:
            return out
        ev_done = [r for r in evs if r["finished"]]
        out["ev_mean_travel_time_s"] = _r(_mean(r["duration"] for r in ev_done))
        out["ev_mean_delay_s"] = _r(_mean(r["time_loss"] for r in ev_done))
        out["ev_unfinished"] = len(evs) - len(ev_done)
        out["ev_trips"] = [
            {k: r[k] for k in ("id", "vtype", "depart", "arrival", "finished", "duration", "time_loss", "depart_edge", "arrival_edge")}
            for r in evs
        ]
        run_end = self.end_time or self._t_last
        spans = [(r["depart"], (r["arrival"] if r["finished"] else run_end) + EV_WINDOW_TAIL_S) for r in evs]
        population = [r for r in others if r["depart"] <= run_end - EV_COMPARE_CUTOFF_S]
        near, far = [], []
        for r in population:
            (near if any(r["depart"] < b and r["arrival"] > a for a, b in spans) else far).append(r)
        out["others_delay_ev_window_s"] = _r(_mean(r["time_loss"] for r in near))
        out["others_delay_no_ev_s"] = _r(_mean(r["time_loss"] for r in far))
        out["others_near_ev_n"] = len(near)
        weighted, weight = 0.0, 0
        for g in {r["movement"] for r in near}:
            near_g = [r["time_loss"] for r in near if r["movement"] == g]
            far_g = [r["time_loss"] for r in far if r["movement"] == g]
            if near_g and far_g:
                weighted += len(near_g) * (_mean(near_g) - _mean(far_g))
                weight += len(near_g)
        out["ev_extra_delay_others_s"] = _r(weighted / weight) if weight else None
        return out

    def _events(self, events: list[dict] | None) -> list[dict]:
        return list(events) if events is not None else list(self.feed.events)

    def _recovery(self, events: list[dict] | None) -> dict:
        """Recovery per disruption. event_windows merges overlapping windows into one disruption;
        with several disruptions the headline excess is their union (recovery.union_excess), so
        a disruption that has not recovered when the next one starts is not counted twice."""
        windows = event_windows(self._events(events), self.end_time)
        times = [row[0] for row in self.timeseries]
        rates = [row[5] for row in self.timeseries]
        detail = []
        for w in windows:
            res = recovery_time(times, rates, start=w["start"], end=w["end"])
            item = {"kind": w["kind"], "what": w["what"], **res}
            if len(w.get("parts") or []) > 1:
                item["parts"] = w["parts"]
            detail.append(item)
        recovered = [d["recovery_s"] for d in detail if d["recovery_s"] is not None]
        if len(detail) > 1 and times:
            spans = [(d["start"], d["recovered_at"] if d["recovered_at"] is not None else times[-1], d["pre_level"]) for d in detail]
            excess = union_excess(times, rates, spans) or 0.0
        else:
            excess = sum(d["excess_veh_h"] or 0.0 for d in detail)
        headline = {
            "disruptions": len(detail),
            "recovery_time_s": max(recovered) if recovered else None,
            "recovery_censored": any(d["censored"] for d in detail) if detail else None,
            "excess_delay_veh_h": _r(excess, 3) if detail else None,
        }
        return {"headline": headline, "detail": detail}

    def _alert_metrics(self, sensors) -> dict:
        """Fake-data cross-check performance: detection delay and false alarms (window only)."""
        t_end = self.end_time or self._t_last
        lo = self.warmup

        def clipped(a: float, b: float) -> float:
            return max(0.0, min(b, t_end) - max(a, lo))

        attacks = [dict(a, end=a["end"] if a["end"] is not None else t_end) for a in sensors.attacks]
        episodes = []
        for ep in sensors.check.episodes:
            end = ep.end if ep.end is not None else t_end
            key = (ep.junction, ep.approach)
            true = any(
                (a["junction"], a["approach"]) == key and ep.start <= a["end"] + FALSE_ALARM_GRACE_S and end >= a["start"]
                for a in attacks
            )
            episodes.append(
                {"junction": ep.junction, "approach": ep.approach, "start": ep.start, "end": end,
                 "test": ep.test, "max_probe_halted": ep.max_probe_halted, "true_alarm": true}
            )
        detection = []
        for a in attacks:
            hits = [e for e in episodes if (e["junction"], e["approach"]) == (a["junction"], a["approach"]) and e["true_alarm"] and e["start"] >= a["start"]]
            first = min((e["start"] for e in hits), default=None)
            detection.append({**a, "detected": first is not None, "detection_delay_s": None if first is None else round(first - a["start"], 1)})
        headline = {
            "alert_episodes": sum(1 for e in episodes if clipped(e["start"], e["end"]) > 0),
            "alert_s": round(sum(clipped(e["start"], e["end"]) for e in episodes), 1),
            "false_alarm_s": round(sum(clipped(e["start"], e["end"]) for e in episodes if not e["true_alarm"]), 1),
            "attacks": len(attacks),
            "attack_detected": all(d["detected"] for d in detection) if detection else None,
            "detection_delay_s": max((d["detection_delay_s"] for d in detection if d["detection_delay_s"] is not None), default=None),
        }
        return {"headline": headline, "detail": {"episodes": episodes, "attacks": detection}}

    # --- files ---------------------------------------------------------------------
    def _write_files(self, out: Path, detail: dict) -> None:
        try:
            out.mkdir(parents=True, exist_ok=True)
            with open(out / "timeseries.csv", "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(TIMESERIES_COLUMNS)
                w.writerows(self.timeseries)
            sensors = self.feed.sensors
            if sensors is not None:
                with open(out / "estimation.csv", "w", newline="") as fh:
                    w = csv.writer(fh)
                    w.writerow(ESTIMATION_COLUMNS)
                    w.writerows(sensors.estimation)
                with open(out / "detector_intervals.csv", "w", newline="") as fh:
                    w = csv.writer(fh)
                    w.writerow(DETECTOR_INTERVAL_COLUMNS)
                    w.writerows(sensors.finish_intervals())
            (out / "evaluation.json").write_text(json.dumps(detail, indent=1, default=str))
        except OSError:
            pass  # extra files are nice to have; never fail a run because of them
