"""Shared building blocks for the sensor-driven controllers (actuated, max-pressure).

Owner: AI & security (Yunseong).

`AdaptiveController` does the bookkeeping every adaptive controller needs, so a subclass
only answers one question in `decide()`: "junction J has shown `axis` green for `t_green`
seconds — keep it or switch?"

    every step       check the observation (defense.py); missing / stale / replayed
                     → run the approved fallback plan (fixed-time 90 s) instead
    every `interval` for each junction that has shown green for at least `min_green`:
                       green ≥ max_green and the other axis has cars → switch (no starvation)
                       otherwise                                    → decide(j, axis, t_green)

The safety supervisor still enforces min green / yellow / all-red; `min_green` here is
our own, never shorter than the supervisor's 8 s.

Tunable (constructor params, recorded in each run's manifest):
    interval     seconds between decisions
    min_green    shortest green this controller asks for (≥ 8 s)
    max_green    longest green while the other axis waits (None = no cap)
    max_obs_age  observations older than this many seconds count as stale
"""
from __future__ import annotations

import math
from collections import Counter

from teamb import config
from teamb.controllers.base import Controller
from teamb.controllers.defense import ObservationGuard
from teamb.controllers.fixed_time import TimingPlan
from teamb.sim.phases import other_axis

AXIS_SIDES = {"EW": ("W", "E"), "NS": ("N", "S")}  # approaches served by each axis
THROUGH_EXIT = {"W": "E", "E": "W", "N": "S", "S": "N"}  # straight-on traffic from W leaves to the E


def num(data: dict | None, key: str, default: float = 0.0) -> float:
    """Read a number from an optional dict; None or missing → default."""
    if not data:
        return default
    value = data.get(key)
    return default if value is None else float(value)


def detector(entry: dict | None) -> dict:
    return (entry or {}).get("detector") or {}


def axis_sum(approaches: dict, axis: str, key: str) -> float:
    """Sum of a detector field (e.g. "queue", "count") over the approaches of one axis."""
    return sum(num(detector(approaches.get(side)), key) for side in AXIS_SIDES[axis])


class AdaptiveController(Controller):
    """Base class: decision clock, min/max green, and the stale-data fallback."""

    def __init__(
        self,
        *,
        interval: float = 1.0,
        min_green: float = 10.0,
        max_green: float | None = 60.0,
        max_obs_age: float = 10.0,
        **params,
    ):
        super().__init__(interval=interval, min_green=min_green, max_green=max_green, max_obs_age=max_obs_age, **params)
        self.interval = float(interval)
        self.min_green = max(float(min_green), float(config.MIN_GREEN_S))
        self.max_green = float(max_green) if max_green else None
        self.max_obs_age = float(max_obs_age)
        self.fallback_plan = TimingPlan()  # the approved fixed-time plan for degraded data

    def reset(self, cfg, seed, topology) -> None:
        super().reset(cfg, seed, topology)
        self.guard = ObservationGuard(topology, max_age_s=self.max_obs_age)
        self.fallback_plan.splits = {j: 0.5 for j in topology.tls_ids}
        self.stats: Counter = Counter()  # decisions, switch requests, degraded steps
        self.last_action: dict[str, str] = {}
        self._next_decision = -math.inf

    # --- the step ---------------------------------------------------------
    def propose_action(self, state: dict) -> dict[str, str | None]:
        t = state["t"]
        problem = self.guard.check_observation(self.observation, t)
        if problem:
            self.stats[f"degraded_{problem}"] += 1
            return {j: self.fallback_plan.axis_at(j, t) for j in state["junctions"]}
        if t + 1e-9 < self._next_decision:
            return {}  # between decisions: keep every green
        self._next_decision = t + self.interval
        seen = self.observation["junctions"]
        action: dict[str, str | None] = {}
        for j, js in state["junctions"].items():
            if not js["green"] or js["time_in_state"] < self.min_green or j not in seen:
                continue  # yellow / all-red running, green too young, or no data for J
            axis, t_green = js["phase"], js["time_in_state"]
            other = other_axis(axis)
            self.stats["decisions"] += 1
            if self.max_green is not None and t_green >= self.max_green and self.has_demand(j, other):
                want = other  # max-out: the other street has waited long enough
            else:
                want = self.decide(j, axis, t_green)
            if want == other:
                action[j] = other
                self.stats["switch_requests"] += 1
        self.last_action = action
        return action

    def summary(self) -> dict:
        """Counters for experiments: decisions, switch requests, degraded steps, defense rejections."""
        return {"stats": dict(self.stats), "guard_rejected": dict(self.guard.rejected)}

    # --- what subclasses override -------------------------------------------
    def decide(self, junction: str, axis: str, t_green: float) -> str | None:
        """Return the axis to show next ("EW"/"NS"); None or `axis` keeps the green."""
        raise NotImplementedError

    def has_demand(self, junction: str, axis: str) -> bool:
        """Is anybody waiting or arriving on `axis`? (loop detectors: count or queue > 0)"""
        approaches = self.observation["junctions"][junction]["approaches"]
        return axis_sum(approaches, axis, "count") > 0 or axis_sum(approaches, axis, "queue") > 0
