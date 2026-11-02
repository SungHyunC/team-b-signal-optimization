"""Who shares navigation-app data (probe selection) and when a probe sends a report.

The ``sampling`` argument of ``SimEnv`` / ``SensorSuite`` picks the mechanism. An
optional parameter follows a colon::

    uniform                 every departing vehicle is a probe with probability = coverage
    approach_biased[:r]     drivers who enter on the arterial are r times as likely (default
                            r = 2) to run a navigation app as drivers who enter from a cross
                            street; probabilities are rescaled so the overall share of probes
                            stays ≈ coverage
    speed_biased[:p]        probes are chosen like `uniform`, but a stopped phone
                            (speed < 0.1 m/s) sends a report in a given second only with
                            probability p (default 0.3); moving phones report every second

Selection happens once per trip (vehicle level): a driver either shares data for the
whole trip or not at all. The research question (Report 1, sampling bias) is how much
the estimates of queues and flows - and the decisions of probe-based controllers -
suffer when the probes are few (coverage 10-100 %) or not representative.

Formula for approach_biased (water-filling)
-------------------------------------------
Groups g (arterial, cross) have population shares s_g (estimated from the departures
seen so far) and relative weights w_g (arterial r, cross 1). We want per-group
probabilities p_g = min(1, k * w_g) such that the expected overall share
sum_g s_g * p_g equals the coverage c. The left side grows with k, so k is found by
bisection. Example: c = 0.25, r = 2, s_arterial = 0.57 gives
k = 0.25 / (0.57 * 2 + 0.43) = 0.159, p_arterial = 0.32, p_cross = 0.16.
At c = 1 every p_g is 1 and the bias disappears, as it should.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

MECHANISMS = ("uniform", "approach_biased", "speed_biased")
DEFAULT_ARTERIAL_RATIO = 2.0
DEFAULT_STOPPED_REPORT_PROB = 0.3
HALT_SPEED = 0.1  # m/s, same threshold as the "halted" probe count


@dataclass(frozen=True)
class SamplingSpec:
    mechanism: str = "uniform"
    arterial_ratio: float = DEFAULT_ARTERIAL_RATIO  # approach_biased: arterial vs cross-street app use
    stopped_report_prob: float = DEFAULT_STOPPED_REPORT_PROB  # speed_biased: P(report | stopped) per second

    @property
    def label(self) -> str:
        if self.mechanism == "approach_biased" and self.arterial_ratio != DEFAULT_ARTERIAL_RATIO:
            return f"approach_biased:{self.arterial_ratio:g}"
        if self.mechanism == "speed_biased" and self.stopped_report_prob != DEFAULT_STOPPED_REPORT_PROB:
            return f"speed_biased:{self.stopped_report_prob:g}"
        return self.mechanism


def parse_sampling(text: str | None) -> SamplingSpec:
    """'uniform' | 'approach_biased' | 'approach_biased:3' | 'speed_biased' | 'speed_biased:0.2'."""
    text = (text or "uniform").strip()
    name, _, arg = text.partition(":")
    name = name.strip().lower().replace("-", "_")
    if name not in MECHANISMS:
        raise ValueError(f"unknown sampling '{text}'. Use one of {MECHANISMS} (optionally 'name:param')")
    if not arg:
        return SamplingSpec(name)
    value = float(arg)
    if name == "approach_biased":
        if value <= 0:
            raise ValueError("approach_biased ratio must be > 0")
        return SamplingSpec(name, arterial_ratio=value)
    if name == "speed_biased":
        if not 0.0 <= value <= 1.0:
            raise ValueError("speed_biased report probability must be in [0, 1]")
        return SamplingSpec(name, stopped_report_prob=value)
    raise ValueError(f"sampling '{name}' takes no parameter")


def group_probabilities(coverage: float, shares: dict[str, float], weights: dict[str, float]) -> dict[str, float]:
    """Per-group probe probabilities p_g = min(1, k*w_g) with sum_g share_g*p_g = coverage.

    `shares` need not sum to 1 (they are normalized). Solved by bisection on k."""
    total = sum(shares.values())
    if total <= 0:
        return {g: coverage for g in shares}
    s = {g: v / total for g, v in shares.items()}
    target = max(0.0, min(1.0, coverage))

    def expected(k: float) -> float:
        return sum(s[g] * min(1.0, k * weights[g]) for g in s)

    lo, hi = 0.0, 1.0 / min(weights[g] for g in s)  # at hi every group is at p = 1
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if expected(mid) < target:
            lo = mid
        else:
            hi = mid
    return {g: min(1.0, hi * weights[g]) for g in s}


class ProbeSelector:
    """Decides, once per departing vehicle, whether it is a probe."""

    def __init__(self, spec: SamplingSpec, rng: random.Random, prior: float = 20.0):
        self.spec = spec
        self.rng = rng
        # departures seen per origin group, started with a weak prior (half/half)
        self.seen = {"arterial": prior / 2, "cross": prior / 2}
        self.selected = {"arterial": 0, "cross": 0}
        self.departed = {"arterial": 0, "cross": 0}

    def probability(self, group: str, coverage: float) -> float:
        if self.spec.mechanism != "approach_biased":
            return coverage
        weights = {"arterial": self.spec.arterial_ratio, "cross": 1.0}
        return group_probabilities(coverage, self.seen, weights)[group]

    def select(self, group: str, coverage: float) -> bool:
        group = group if group in self.seen else "cross"
        p = self.probability(group, coverage)
        self.seen[group] += 1
        self.departed[group] += 1
        chosen = self.rng.random() < p
        self.selected[group] += chosen
        return chosen

    def shares(self) -> dict[str, float | None]:
        """Realized share of probes per origin group and overall (for evaluation)."""
        out = {g: (self.selected[g] / self.departed[g] if self.departed[g] else None) for g in self.departed}
        n = sum(self.departed.values())
        out["overall"] = sum(self.selected.values()) / n if n else None
        return out


def report_probability(spec: SamplingSpec, speed: float) -> float:
    """Chance that a probe sends a report this second (state-dependent reporting)."""
    if spec.mechanism == "speed_biased" and speed < HALT_SPEED:
        return spec.stopped_report_prob
    return 1.0
