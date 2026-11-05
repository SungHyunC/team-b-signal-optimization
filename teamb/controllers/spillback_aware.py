"""Experimental max-pressure variant with extra penalties for crowded downstream links.

This controller is a research hypothesis, not a validated safety improvement.
It inherits the normal safety supervisor, decision timing, fallback, and max-green
limits. The original max_pressure controller is unchanged.
"""
from __future__ import annotations

from teamb.controllers.base import register
from teamb.controllers.common import num
from teamb.controllers.max_pressure import MaxPressureController


@register
class SpillbackAwareMaxPressureController(MaxPressureController):
    name = "max_pressure_spillback"
    label = "Max-pressure (spillback-aware experiment)"
    description = (
        "Research variant: discourages green into downstream links whose measured "
        "stopped queues exceed a threshold. Not yet validated against the original."
    )

    def __init__(
        self,
        congestion_threshold: float = 6.0,
        downstream_penalty: float = 1.5,
        **params,
    ):
        if congestion_threshold < 0 or downstream_penalty < 1:
            raise ValueError("congestion_threshold must be >= 0 and downstream_penalty >= 1")
        # Use loop detectors for this experiment; no fake-data observations.
        source = params.pop("source", "detector")
        if source != "detector":
            raise ValueError("experimental controller supports detector data only")
        super().__init__(source=source, **params)
        self.congestion_threshold = float(congestion_threshold)
        self.downstream_penalty = float(downstream_penalty)
        self.params.update({
            "congestion_threshold": self.congestion_threshold,
            "downstream_penalty": self.downstream_penalty,
        })

    def cars_downstream(self, junction: str, exit_side: str) -> float:
        baseline = super().cars_downstream(junction, exit_side)
        exit_info = self.observation["junctions"][junction].get("exits", {}).get(exit_side) or {}
        det = exit_info.get("detector") or {}
        queue = num(det, "queue")
        if queue < self.congestion_threshold:
            return baseline
        # Only penalize currently congested downstream links. Count includes moving
        # vehicles, so it is used conservatively only beyond a stopped-queue threshold.
        return max(baseline, num(det, "count")) * self.downstream_penalty
