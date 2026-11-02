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

Registered twice: `max_pressure` (detectors) and `max_pressure_probe` (probes, no
defense) so the security test is one dropdown away.

Tunable: measure, down_measure, weighted, margin (cars), interval (5 s), min_green, max_green,
source, defense.
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
        **params,
    ):
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, not {source!r}")
        if measure not in MEASURES or (down_measure or measure) not in MEASURES:
            raise ValueError(f"measure and down_measure must be one of {MEASURES}")
        super().__init__(source=source, defense=defense, measure=measure, down_measure=down_measure, weighted=weighted,
                         margin=margin, interval=interval, min_green=min_green, max_green=max_green, **params)
        self.source = source
        self.defense = bool(defense)
        self.measure = measure
        self.down_measure = down_measure or measure
        self.weighted = bool(weighted)
        self.margin = float(margin)

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

    # --- the rule -----------------------------------------------------------
    def decide(self, junction: str, axis: str, t_green: float) -> str | None:
        other = other_axis(axis)
        if self.pressure(junction, other) > self.pressure(junction, axis) + self.margin:
            return other
        return axis

    def pressure(self, junction: str, axis: str) -> float:
        approaches = self.observation["junctions"][junction]["approaches"]
        total = 0.0
        for side in AXIS_SIDES[axis]:
            if side in approaches:
                weight = self.lanes.get((junction, side), 1) if self.weighted else 1
                total += weight * (self.cars(junction, side) - self.cars_downstream(junction, THROUGH_EXIT[side]))
        return total

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
