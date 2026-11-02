"""Demand model for the AI recommender, built ONLY from navigation-app probe data.

Owner: AI & security (Yunseong).

Like Google's Project Green Light, the recommender never reads loop detectors or ground
truth — only what cars running a navigation app report. At coverage c every probe stands
for 1/c cars, so low coverage gives a noisy (and possibly biased) model. That is the
sampling-bias experiment from Report 1, so do not "fix" it by peeking at the detectors.

    model = ProbeDemandModel(topology)
    model.add(observation)            every step (keeps one sample every `sample_every_s`)
    demand = model.approach_demand(t) veh/h per (junction, approach) over the last `window_s`
    flows = od_flows(demand)          origin–destination Flows for a test Scenario

Approach demand = mean probe flow (`probe.flow_est_vph`, cars that crossed the stop line)
                  + queue growth (cars that arrived but were not served: the probe
                    `queue_est` at the end of the window minus at its start, per hour).
Approaches without usable samples borrow the mean of the same approach at other junctions.

OD flows keep every approach volume: through traffic on the arterial and the cross
streets, plus turning traffic wherever the arterial volume changes between two junctions
(flow conservation). Cars that leave turn right onto a cross street; cars that join come
from a cross street (turning right), and are taken out of that street's through traffic.

Tunable: window_s, sample_every_s, defense (drop untrusted / impossible probe readings).
Ideas to improve it (TODO): time-of-day profiles, turn ratios from probe trajectories,
Bayesian shrinkage towards historical counts at low coverage.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from teamb.controllers.defense import ObservationGuard
from teamb.demand.routes import Flow

SIDES = ("W", "E", "N", "S")


@dataclass
class ProbeSample:
    t: float
    flow: dict[tuple[str, str], float] = field(default_factory=dict)  # veh/h per (junction, side)
    queue: dict[tuple[str, str], float] = field(default_factory=dict)  # stopped cars per (junction, side)


class ProbeDemandModel:
    def __init__(self, topology, *, window_s: float = 300.0, sample_every_s: float = 10.0,
                 defense: bool = False, guard: ObservationGuard | None = None):
        self.junctions = list(topology.tls_ids)
        self.window_s = float(window_s)
        self.sample_every_s = float(sample_every_s)
        self.defense = bool(defense)
        self.guard = guard or ObservationGuard(topology)
        self.samples: deque[ProbeSample] = deque()
        self.ignored = 0  # probe readings dropped by the defense
        self.coverage: float | None = None
        self._next = float("-inf")

    def add(self, observation: dict) -> None:
        t = float(observation["t"])
        if t < self._next:
            return
        self._next = t + self.sample_every_s
        self.coverage = observation.get("coverage")
        sample = ProbeSample(t)
        for j, data in observation.get("junctions", {}).items():
            for side, entry in data.get("approaches", {}).items():
                probe = entry.get("probe") or {}
                flow, queue = probe.get("flow_est_vph"), probe.get("queue_est")
                if flow is None or queue is None:
                    continue
                if self.defense and self.guard.probe_value(j, side, entry, "queue_est") is None:
                    self.ignored += 1  # flagged by the cross-check or physically impossible
                    continue
                sample.flow[(j, side)] = float(flow)
                sample.queue[(j, side)] = float(queue)
        self.samples.append(sample)
        while self.samples and self.samples[0].t < t - self.window_s - self.sample_every_s:
            self.samples.popleft()

    def window(self, now: float) -> list[ProbeSample]:
        return [s for s in self.samples if s.t >= now - self.window_s]

    def approach_demand(self, now: float) -> dict[tuple[str, str], float]:
        """veh/h per (junction, side): mean probe flow + queue growth over the window."""
        samples = self.window(now)
        demand: dict[tuple[str, str], float] = {}
        if not samples:
            return demand
        edge = max(1, len(samples) // 3)  # compare the first and last third of the window
        head, tail = samples[:edge], samples[-edge:]
        span_h = max(1.0, (tail[-1].t + tail[0].t) / 2 - (head[-1].t + head[0].t) / 2) / 3600.0
        keys = {k for s in samples for k in s.flow}
        for key in keys:
            flows = [s.flow[key] for s in samples if key in s.flow]
            q0 = _mean([s.queue[key] for s in head if key in s.queue])
            q1 = _mean([s.queue[key] for s in tail if key in s.queue])
            growth = max(0.0, q1 - q0) / span_h if q0 is not None and q1 is not None and len(samples) > 2 else 0.0
            demand[key] = _mean(flows) + growth
        for j in self.junctions:  # fill gaps from the same approach at other junctions
            for side in SIDES:
                if (j, side) not in demand:
                    same = [v for (j2, s2), v in demand.items() if s2 == side]
                    if same:
                        demand[(j, side)] = sum(same) / len(same)
        return demand


def _mean(values):
    return sum(values) / len(values) if values else None


def nested(demand: dict[tuple[str, str], float]) -> dict[str, dict[str, float]]:
    """{(J1, W): 1280.4} → {"J1": {"W": 1280.0}} for JSON / the twin."""
    out: dict[str, dict[str, float]] = {}
    for (j, side), value in sorted(demand.items()):
        out.setdefault(j, {})[side] = round(value, 0)
    return out


def od_flows(demand: dict[tuple[str, str], float], junctions=("J1", "J2", "J3", "J4"), min_vph: float = 1.0) -> list[Flow]:
    """Origin–destination flows on our corridor that reproduce the approach volumes."""
    junctions = list(junctions)
    idx = {j: i + 1 for i, j in enumerate(junctions)}  # J1 → 1; cross-street node ids use it
    nb_through = {j: demand.get((j, "S"), 0.0) for j in junctions}
    sb_through = {j: demand.get((j, "N"), 0.0) for j in junctions}
    flows: list[Flow] = []

    def take(groups, amount, destination, label):
        for g in groups:  # oldest group first
            part = min(g[1], amount)
            if part > 0:
                flows.append(Flow(g[0], destination, part, name=label))
                g[1] -= part
                amount -= part

    # eastbound: enters at J1's west approach, ends at J4_E5
    groups = [["W0_J1", demand.get((junctions[0], "W"), 0.0)]]  # [origin edge, veh/h] travelling east
    for a, b in zip(junctions, junctions[1:]):
        i = idx[a]
        change = demand.get((b, "W"), 0.0) - sum(g[1] for g in groups)
        if change < 0:  # cars left the arterial at a: right turn onto the south leg
            take(groups, -change, f"{a}_S{i}", f"EB right at {a}")
        elif change > 0:  # cars joined at a: northbound cars turning right
            join = min(change, nb_through[a])
            if join > 0:
                groups.append([f"S{i}_{a}", join])
                nb_through[a] -= join
    for origin, q in groups:
        flows.append(Flow(origin, f"{junctions[-1]}_E{len(junctions) + 1}", q, name=f"EB from {origin}"))

    # westbound: enters at J4's east approach, ends at J1_W0
    rev = junctions[::-1]
    groups = [[f"E{len(junctions) + 1}_{rev[0]}", demand.get((rev[0], "E"), 0.0)]]
    for a, b in zip(rev, rev[1:]):
        i = idx[a]
        change = demand.get((b, "E"), 0.0) - sum(g[1] for g in groups)
        if change < 0:  # left at a: right turn (for westbound) onto the north leg
            take(groups, -change, f"{a}_N{i}", f"WB right at {a}")
        elif change > 0:  # joined at a: southbound cars turning right
            join = min(change, sb_through[a])
            if join > 0:
                groups.append([f"NN{i}_N{i}", join])
                sb_through[a] -= join
    for origin, q in groups:
        flows.append(Flow(origin, f"{junctions[0]}_W0", q, name=f"WB from {origin}"))

    for j in junctions:  # what is left on the cross streets goes straight across
        i = idx[j]
        flows.append(Flow(f"NN{i}_N{i}", f"{j}_S{i}", sb_through[j], name=f"SB cross {j}"))
        flows.append(Flow(f"S{i}_{j}", f"N{i}_NN{i}", nb_through[j], name=f"NB cross {j}"))
    for f in flows:
        f.veh_per_hour = round(f.veh_per_hour, 1)
    return [f for f in flows if f.veh_per_hour >= min_vph]
