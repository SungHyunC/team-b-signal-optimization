"""Actuated control: gap-out / max-out from loop detectors (standard practice in the US and Korea).

Owner: AI & security (Yunseong).

Per junction, while one axis is green (checked every `interval` = 1 s):

    keep the green for at least `min_green` s
    nobody waiting on the other axis          → rest in green (no pointless yellow)
    a car crossed a green-axis loop recently  → extend  (detector.gap_s ≤ gap_out)
    no car for more than `gap_out` s          → gap-out: switch
    green has lasted `max_green` s            → max-out: switch (handled by AdaptiveController)

`detector.gap_s` is the time since a car last crossed the E1 loop 25 m before the stop
line (smallest over the approach's lanes); we take the smallest over both green approaches,
so the green ends only when both directions have a gap — like a dual-ring controller
crossing the barrier.

Tunable: gap_out (s, 2.5–4 is typical), min_green, max_green, interval.
"""
from __future__ import annotations

import math

from teamb.controllers.base import register
from teamb.controllers.common import AXIS_SIDES, AdaptiveController, detector, num
from teamb.sim.phases import other_axis


@register
class ActuatedController(AdaptiveController):
    name = "actuated"
    label = "Actuated (gap-out / max-out)"
    description = (
        "Extends the green while the loop detectors still see cars arriving; switches after a "
        "gap of more than 3 s or at max green (50 s), and only if the other street has cars."
    )
    owner = "AI & security (Yunseong)"
    observation_source = "detector"

    def __init__(self, gap_out: float = 3.0, min_green: float = 10.0, max_green: float = 50.0, interval: float = 1.0, **params):
        super().__init__(gap_out=gap_out, min_green=min_green, max_green=max_green, interval=interval, **params)
        self.gap_out = float(gap_out)

    def decide(self, junction: str, axis: str, t_green: float) -> str | None:
        approaches = self.observation["junctions"][junction]["approaches"]
        other = other_axis(axis)
        if not self.has_demand(junction, other):
            return axis  # nobody waiting: rest in green
        gaps = [num(detector(approaches[side]), "gap_s", math.inf) for side in AXIS_SIDES[axis] if side in approaches]
        gap = min(gaps, default=math.inf)
        return other if gap > self.gap_out else axis
