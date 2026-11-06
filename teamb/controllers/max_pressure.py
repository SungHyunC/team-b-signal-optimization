"""Max-pressure control (Varaiya 2013), decided every few seconds at each junction.

Owner: AI & security (Yunseong).

    pressure(axis) = Σ over the axis' approaches a:   w(a) · ( x_up(a) − x_down(a) )

    x_up(a)    cars on approach a that want to cross (`measure`, default: all cars)
    x_down(a)  stopped cars on the road a's straight-on traffic drives into (W → exit E,
               E → exit W, N → exit S, S → exit N), i.e. how much room is gone there
               (`down_measure`, default: stopped cars); 0 when that road leaves the corridor
    w(a)       1, or the number of lanes of a with weighted=True (Varaiya weights each
               movement by its saturation flow, which is proportional to its lanes)

Serving the axis with the higher pressure moves cars from long queues into roads that
have room — throughput-optimal in theory, and it needs no timing plan. We keep the
current green unless the other axis' pressure is higher by `margin` cars, which avoids
flip-flopping (every switch costs 5 s of yellow + all-red).

What counts as "cars" — `measure` (upstream) and `down_measure` (downstream):
    "count"  all cars in the detector zone (detector.count) / probe reports (probe.n ÷ coverage)
    "queue"  stopped cars only (detector.queue / probe.queue_est)
Defaults: measure="count", down_measure="queue". Stopped-only upstream (the literal spec)
backfires: as soon as an axis turns green its cars start moving, its "queue" drops to ~0
and the controller flips back after min green — 82 s mean delay on rush hour vs 69 s for
fixed-time (2 seeds, 2700 s). Varaiya's model is store-and-forward, where the queue is every
car on the link, so upstream we count every car. Downstream only stopped cars take away
room; counting moving ones (a platoon just released) made the probe version flip-flop.

Data sources (`source`):
    "detector"  loop detectors: approaches[a].detector, exits[side].detector
    "probe"     navigation-app probes: probe.n / coverage ("count") or probe.queue_est
                ("queue") on the approach, and for x_down the probe number on the
                downstream junction's approach. The fake-data attack targets this one.
`defense=True` ignores probe entries flagged `trusted: false` or claiming more cars than
the lanes can hold, and uses the loop detector there instead (defense.py).

Registered three times: `max_pressure` (detectors), `max_pressure_probe` (probes, no
defense) so the security test is one dropdown away, and `max_pressure_plus` (detectors,
rho = 0.25, the hysteresis setting that passed the 30-seed regression screen).

Lost-time-aware hysteresis (`rho`, default 0 = off): every switch costs 5 s of yellow +
all-red, which matters most when queues are long. With rho > 0 the green switches only if

    P_other > P_current + margin + min(rho · max(P_current, 0), rho_cap)

(rho_cap in cars, None = no cap). Symmetric: it never boosts one approach, it only asks for a
larger lead before paying the lost time. rho=0 gives exactly the original rule.

Closed / blocked straight-on exits (`closure_aware`, default False = off): when the road an
approach's straight-on traffic drives into is closed, its detector zone is empty, so x_down = 0
reads as "lots of room" although nobody can go straight. With closure_aware=True such an
approach's term becomes closure_weight · (x_up − x_down) instead of (x_up − x_down)
(closure_weight 0 = the through movement adds no pressure). The exit counts as closed when
    - the observation says so (exits[side]["closed"] is true, or its edge is listed in
      observation["closed_edges"]), or
    - detectors show it: while the approach had green with ≥ closure_min_queue stopped cars,
      the exit's zone stayed completely empty for closure_detect_s seconds of decisions.
      Any car in that zone resets the evidence (so a reopened road counts as open again).
Without a closure nothing changes: the evidence never builds up while cars reach the exit.

Tunable: measure, down_measure, weighted, margin (cars), rho, rho_cap (cars), interval (5 s),
min_green, max_green, source, defense, closure_aware, closure_weight (0..1), closure_detect_s (> 0 s),
closure_min_queue (>= 0 cars).
"""
from __future__ import annotations

from teamb.controllers.base import register
from teamb.controllers.common import AXIS_SIDES, THROUGH_EXIT, AdaptiveController, detector, num
from teamb.sim.phases import other_axis

SOURCES = ("detector", "probe")
MEASURES = ("count", "queue")


@register
class MaxPressureController(AdaptiveController):
    name = "max_pressure"
    label = "Max-pressure"
    description = (
        "Every 5 s, gives green to the axis with the larger pressure (cars upstream minus cars "
        "downstream, from loop detectors). No timing plan needed."
    )
    owner = "AI & security (Yunseong)"
    observation_source = "detector"

    def __init__(
        self,
        source: str = "detector",
        defense: bool = False,
        measure: str = "count",
        down_measure: str | None = "queue",
        weighted: bool = False,
        margin: float = 2.0,
        interval: float = 5.0,
        min_green: float = 10.0,
        max_green: float | None = 90.0,
        rho: float = 0.0,
        rho_cap: float | None = None,
        closure_aware: bool = False,
        closure_weight: float = 0.0,
        closure_detect_s: float = 30.0,
        closure_min_queue: float = 3.0,
        **params,
    ):
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, not {source!r}")
        if measure not in MEASURES or (down_measure or measure) not in MEASURES:
            raise ValueError(f"measure and down_measure must be one of {MEASURES}")
        if float(rho) < 0 or (rho_cap is not None and float(rho_cap) < 0):
            raise ValueError("rho and rho_cap must be >= 0")
        if not 0.0 <= float(closure_weight) <= 1.0:
            raise ValueError("closure_weight must be between 0 and 1")
        # closure_detect_s <= 0 would count an open exit (evidence 0.0) as closed at every approach
        if not float(closure_detect_s) > 0 or not float(closure_min_queue) >= 0:
            raise ValueError("closure_detect_s must be > 0 s and closure_min_queue >= 0 cars")
        super().__init__(source=source, defense=defense, measure=measure, down_measure=down_measure, weighted=weighted,
                         margin=margin, interval=interval, min_green=min_green, max_green=max_green, rho=rho,
                         rho_cap=rho_cap, closure_aware=closure_aware, closure_weight=closure_weight,
                         closure_detect_s=closure_detect_s, closure_min_queue=closure_min_queue, **params)
        self.source = source
        self.defense = bool(defense)
        self.measure = measure
        self.down_measure = down_measure or measure
        self.weighted = bool(weighted)
        self.margin = float(margin)
        self.rho = float(rho)
        self.rho_cap = None if rho_cap is None else float(rho_cap)
        self.closure_aware = bool(closure_aware)
        self.closure_weight = float(closure_weight)
        self.closure_detect_s = float(closure_detect_s)
        self.closure_min_queue = float(closure_min_queue)

    def reset(self, cfg, seed, topology) -> None:
        super().reset(cfg, seed, topology)
        self.lanes = {(j, s): len(lanes) for j, sides in topology.approach_lanes.items() for s, lanes in sides.items()}
        # exit (junction, side) → the downstream junction's approach it feeds, if signalized
        self.downstream: dict[tuple[str, str], tuple[str, str] | None] = {}
        for j in topology.tls_ids:
            for side, edge in topology.exit_edges[j].items():
                j2 = topology.downstream_junction(edge)
                side2 = next((s for s, e in topology.approach_edges.get(j2, {}).items() if e == edge), None)
                self.downstream[(j, side)] = (j2, side2) if j2 and side2 else None
        self._empty_exit_s: dict[tuple[str, str], float] = {}  # (junction, exit side) → closure evidence

    # --- the rule -----------------------------------------------------------
    def decide(self, junction: str, axis: str, t_green: float) -> str | None:
        other = other_axis(axis)
        if self.closure_aware:
            self._watch_exits(junction, axis)
        p_other = self.pressure(junction, other)
        p_current = self.pressure(junction, axis)
        if p_other > p_current + self.margin + self.hysteresis(p_current):
            return other
        return axis

    def hysteresis(self, p_current: float) -> float:
        """Extra lead (cars) the other axis needs on top of `margin`: rho·P_current, capped at rho_cap."""
        if not self.rho:
            return 0.0
        extra = self.rho * max(p_current, 0.0)
        return extra if self.rho_cap is None else min(extra, self.rho_cap)

    def pressure(self, junction: str, axis: str) -> float:
        approaches = self.observation["junctions"][junction]["approaches"]
        total = 0.0
        for side in AXIS_SIDES[axis]:
            if side in approaches:
                weight = self.lanes.get((junction, side), 1) if self.weighted else 1
                up, down = self.cars(junction, side), self.cars_downstream(junction, THROUGH_EXIT[side])
                if self.closure_aware and up > down and self.through_closed(junction, side):
                    down += (1.0 - self.closure_weight) * (up - down)  # a closed road is not an empty one
                    self.stats["closure_adjusted"] += 1
                total += weight * (up - down)
        return total

    # --- closed straight-on exits (closure_aware) ----------------------------------
    def through_closed(self, junction: str, side: str) -> bool:
        """Is the road that straight-on traffic from approach `side` drives into closed / blocked?"""
        exit_side = THROUGH_EXIT[side]
        info = self.observation["junctions"][junction].get("exits", {}).get(exit_side) or {}
        if info.get("closed") or (info.get("edge") and info["edge"] in (self.observation.get("closed_edges") or ())):
            return True
        return self._empty_exit_s.get((junction, exit_side), 0.0) >= self.closure_detect_s

    def _watch_exits(self, junction: str, axis: str) -> None:
        """Collect detector evidence of closed exits at one decision of `junction` (green `axis`)."""
        js = self.observation["junctions"][junction]
        approaches, exits = js["approaches"], js.get("exits", {})
        for side, exit_side in THROUGH_EXIT.items():
            det = (exits.get(exit_side) or {}).get("detector")
            if det is None:
                continue  # no detector on that road: only explicit closure info can tell
            key = (junction, exit_side)
            if num(det, "count") > 0:
                self._empty_exit_s[key] = 0.0  # cars get onto that road: it is open
            elif side in AXIS_SIDES[axis] and num(detector(approaches.get(side)), "queue") >= self.closure_min_queue:
                self._empty_exit_s[key] = self._empty_exit_s.get(key, 0.0) + self.interval

    def has_demand(self, junction: str, axis: str) -> bool:
        approaches = self.observation["junctions"][junction]["approaches"]
        return any(self.cars(junction, s) > 0 for s in AXIS_SIDES[axis] if s in approaches) or super().has_demand(junction, axis)

    # --- where the numbers come from ----------------------------------------
    def cars(self, junction: str, side: str) -> float:
        """x_up: cars on one approach, from the configured source and measure."""
        entry = self.observation["junctions"][junction]["approaches"].get(side)
        if self.source == "probe":
            value = self._probe_cars(junction, side, entry, self.measure)
            if value is not None:
                return value
        return num(detector(entry), self.measure)

    def cars_downstream(self, junction: str, exit_side: str) -> float:
        """x_down: cars on the road leaving `junction` towards `exit_side` (0 if it leaves the corridor)."""
        if self.source == "probe":
            down = self.downstream.get((junction, exit_side))
            if down is None:
                return 0.0
            j2, side2 = down
            entry = self.observation["junctions"].get(j2, {}).get("approaches", {}).get(side2)
            value = self._probe_cars(j2, side2, entry, self.down_measure)
            if value is not None:
                return value
        exit_info = self.observation["junctions"][junction].get("exits", {}).get(exit_side) or {}
        return num(exit_info.get("detector"), self.down_measure)

    def _probe_cars(self, junction: str, side: str, entry: dict | None, measure: str) -> float | None:
        probe = (entry or {}).get("probe") or {}
        if measure == "queue":
            value = probe.get("queue_est")
        else:  # every probe report on the approach, scaled up to all cars
            n, coverage = probe.get("n"), self.observation.get("coverage") or 1.0
            value = None if n is None else n / max(0.01, float(coverage))
        if self.defense:
            return self.guard.screen(junction, side, entry, value)
        return None if value is None else float(value)


@register
class MaxPressureProbeController(MaxPressureController):
    name = "max_pressure_probe"
    label = "Max-pressure (navigation probes, no defense)"
    description = (
        "Max-pressure fed only by navigation-app probe reports, trusted blindly. Start the "
        "fake-data attack to see it fooled; max_pressure with source=probe, defense=True is the fix."
    )
    observation_source = "probe"

    def __init__(self, source: str = "probe", defense: bool = False, **params):
        super().__init__(source=source, defense=defense, **params)


@register
class MaxPressurePlusController(MaxPressureController):
    """`max_pressure` with lost-time-aware hysteresis (rho = 0.25), the setting that passed the
    prespecified regression screen on 30 fresh paired seeds in all 21 conditions (7 scenarios x
    demand 0.75/1.0/1.25; docs/results/studies/controller-confirmation-2026-11/). Everything else,
    including every other default, is the original controller's; pass rho to override."""

    name = "max_pressure_plus"
    label = "Max-pressure+ (lost-time aware)"
    description = (
        "Max-pressure that only switches when the other axis' pressure beats the current one by an extra "
        "25 % (every switch costs 5 s of yellow + all-red). Passed the 30-seed regression screen in all 21 "
        "scenario/demand conditions; biggest gains in heavy traffic and disasters."
    )

    def __init__(self, rho: float = 0.25, **params):
        super().__init__(rho=rho, **params)
