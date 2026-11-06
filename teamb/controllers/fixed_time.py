"""Fixed-time and coordinated (green-wave) timing plans.

A timing plan is cycle length + EW green share + offset per junction. The same plan
executor is reused by the AI recommender, which tunes these numbers and applies them
after approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from teamb import config
from teamb.controllers.base import Controller, register

# shortest cycle that fits two minimum greens and two yellow + all-red changes (26 s)
MIN_CYCLE_S = 2 * config.MIN_GREEN_S + 2 * config.LOST_TIME_PER_SWITCH_S


@dataclass
class TimingPlan:
    cycle: float = config.BASE_CYCLE_S
    splits: dict[str, float] = field(default_factory=dict)  # EW share of the usable green, 0..1
    offsets: dict[str, float] = field(default_factory=dict)  # seconds

    def __post_init__(self):
        if not float(self.cycle) >= MIN_CYCLE_S:
            raise ValueError(f"cycle must be at least {MIN_CYCLE_S} s (two {config.MIN_GREEN_S} s greens + lost time), "
                             f"not {self.cycle!r}")

    def greens(self, junction: str) -> tuple[float, float]:
        """(EW green, NS green) in seconds; both ≥ MIN_GREEN_S and together always cycle − lost time.

        Raising one green to the minimum takes the time from the other one, so every junction
        runs exactly `cycle` seconds and coordinated offsets cannot drift apart.
        """
        usable = self.cycle - 2 * config.LOST_TIME_PER_SWITCH_S
        share = min(0.85, max(0.15, self.splits.get(junction, 0.5)))
        ew = min(max(config.MIN_GREEN_S, usable * share), usable - config.MIN_GREEN_S)
        ns = usable - ew
        return ew, ns

    def axis_at(self, junction: str, t: float) -> str:
        """Axis to request at time t so greens start at offset (EW) and offset+EW+lost (NS)."""
        ew, ns = self.greens(junction)
        cycle = ew + ns + 2 * config.LOST_TIME_PER_SWITCH_S  # == self.cycle (greens() keeps the sum)
        tau = (t - self.offsets.get(junction, 0.0)) % cycle
        # Ask for EW during its green and while NS is clearing at the end of the cycle.
        if tau < ew or tau >= cycle - config.LOST_TIME_PER_SWITCH_S:
            return "EW"
        return "NS"

    def to_dict(self) -> dict:
        return {"cycle": self.cycle, "splits": dict(self.splits), "offsets": dict(self.offsets)}


@register
class FixedTimeController(Controller):
    name = "fixed_time"
    label = "Fixed-time (90 s)"
    description = "Same timing every 90 s cycle, 50/50 split, no coordination. Our starting point."
    owner = "Software & integration (Seong Hyeon)"

    def __init__(self, cycle: float = config.BASE_CYCLE_S, split: float = 0.5, offsets: dict | None = None, **params):
        # every timing parameter goes into self.params, so the run manifest can reproduce the run
        super().__init__(cycle=cycle, split=split, offsets=dict(offsets or {}), **params)
        self.plan = TimingPlan(cycle=cycle, offsets=dict(offsets or {}))
        self.default_split = split

    def reset(self, cfg, seed, topology) -> None:
        super().reset(cfg, seed, topology)
        for j in topology.tls_ids:
            self.plan.splits.setdefault(j, self.default_split)

    def propose_action(self, state: dict) -> dict[str, str | None]:
        t = state["t"]
        return {j: self.plan.axis_at(j, t) for j in state["junctions"]}


@register
class CoordinatedController(FixedTimeController):
    name = "coordinated"
    label = "Coordinated (green wave)"
    description = "Fixed-time with offsets so eastbound platoons meet green at each junction."
    # Offsets follow the eastbound green wave at `progression_speed` m/s; a junction listed in
    # `offsets` (seconds) keeps that value instead.
    owner = "Software & integration (Seong Hyeon)"

    def __init__(self, progression_speed: float = 12.5, split: float = 0.6, **params):
        super().__init__(split=split, progression_speed=progression_speed, **params)
        self.progression_speed = progression_speed
        self.user_offsets = dict(self.params["offsets"])  # explicit offsets win over the green wave

    def reset(self, cfg, seed, topology) -> None:
        super().reset(cfg, seed, topology)
        x0 = min(config.JUNCTION_X.values())
        for j in topology.tls_ids:
            wave = (config.JUNCTION_X[j] - x0) / self.progression_speed
            self.plan.offsets[j] = float(self.user_offsets.get(j, wave))
