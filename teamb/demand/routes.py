"""Write SUMO route files from origin–destination flows.

Owner: Scenarios & analysis (Aditya).

- Arrivals are a (non-homogeneous) Poisson process: a Flow's rate can follow a time-of-day
  profile (see `teamb.demand.profiles`), sampled by thinning.
- Every flow has its OWN random stream, seeded from (run seed, flow origin/destination/name).
  The same seed therefore always gives the same vehicles (REP-01), every controller sees the
  identical demand, and two scenarios that share a flow also share its arrivals (common
  random numbers make scenario-to-scenario comparisons less noisy).
- Vehicles are written as <trip>s; SUMO picks the route when the vehicle departs (and it
  respects closed lanes then — see `teamb.scenarios.events`).
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from teamb.demand.profiles import Profile, integral, max_multiplier, multiplier

VTYPES = """\
  <vType id="car" vClass="passenger" length="4.5" minGap="2.5" maxSpeed="16.7" accel="2.6" decel="4.5" sigma="0.5"/>
  <vType id="truck" vClass="truck" length="9.0" minGap="3.0" maxSpeed="14.0" accel="1.3" decel="4.0" sigma="0.5" guiShape="truck"/>
  <vType id="bus" vClass="bus" length="12.0" minGap="3.0" maxSpeed="14.0" accel="1.2" decel="4.0" sigma="0.4" guiShape="bus"/>
  <vType id="ambulance" vClass="emergency" length="6.5" minGap="2.5" maxSpeed="22.0" accel="3.0" decel="6.0" sigma="0.2" speedFactor="1.3" guiShape="emergency" color="1,1,1"/>
  <vType id="firetruck" vClass="emergency" length="9.0" minGap="2.5" maxSpeed="20.0" accel="2.0" decel="5.0" sigma="0.2" speedFactor="1.2" guiShape="firebrigade" color="0.85,0.1,0.1"/>
"""
VTYPE_IDS = ("car", "truck", "bus", "ambulance", "firetruck")


@dataclass
class Flow:
    """Vehicles from one entry edge to one exit edge.

    veh_per_hour  rate when the profile multiplier is 1.0 (the peak rate for a peak profile)
    begin, end    no vehicles outside [begin, end); `end=None` means the scenario duration
    profile       ((t, multiplier), ...) time-of-day shape; None = constant rate
    mix           {"car": 0.96, "truck": 0.04}; each vehicle draws its type. None = `vtype`
    """

    origin: str  # entry edge id, e.g. "W0_J1"
    destination: str  # exit edge id, e.g. "J4_E5"
    veh_per_hour: float
    begin: float = 0.0
    end: float | None = None  # defaults to the scenario duration
    vtype: str = "car"
    name: str = ""
    profile: Profile | None = None
    mix: dict[str, float] | None = None

    def rate_at(self, t: float, duration: float | None = None) -> float:
        """Arrival rate (veh/h) at time t."""
        end = self.end if self.end is not None else duration
        if t < self.begin or (end is not None and t >= end):
            return 0.0
        return self.veh_per_hour * multiplier(self.profile, t)

    def expected(self, t0: float, t1: float, duration: float | None = None) -> float:
        """Expected number of vehicles departing in [t0, t1)."""
        end = self.end if self.end is not None else (duration if duration is not None else t1)
        a, b = max(t0, self.begin), min(t1, end)
        return self.veh_per_hour / 3600.0 * integral(self.profile, a, b) if b > a else 0.0

    def scaled(self, factor: float) -> "Flow":
        return replace(self, veh_per_hour=self.veh_per_hour * factor)


def _stream_key(flow: Flow, seen: dict[str, int]) -> int:
    key = f"{flow.origin}>{flow.destination}|{flow.vtype}|{flow.name}"
    n = seen.get(key, 0)
    seen[key] = n + 1
    if n:
        key += f"#{n}"
    return zlib.crc32(key.encode())


def _arrivals(rng: np.random.Generator, flow: Flow, duration: float) -> list[float]:
    """Departure times of one flow: Poisson at the peak rate, thinned by the profile."""
    end = duration if flow.end is None else min(flow.end, duration)
    top = max_multiplier(flow.profile, flow.begin, end)
    if flow.veh_per_hour <= 0 or end <= flow.begin or top <= 0:
        return []
    mean_gap = 3600.0 / (flow.veh_per_hour * top)
    out = []
    t = flow.begin + rng.exponential(mean_gap)
    while t < end:
        if flow.profile is None or rng.random() * top <= multiplier(flow.profile, t):
            out.append(t)
        t += rng.exponential(mean_gap)
    return out


def _pick_type(rng: np.random.Generator, flow: Flow) -> str:
    if not flow.mix:
        return flow.vtype
    total = sum(flow.mix.values())
    u = rng.random() * total
    for vtype, share in flow.mix.items():
        u -= share
        if u < 0:
            return vtype
    return next(iter(flow.mix))


def generate_trips(flows: list[Flow], *, seed: int, duration: float) -> list[tuple[float, str, str, Flow]]:
    """[(depart, vehicle id, vtype, flow)] sorted by departure time. Pure function of the inputs."""
    trips = []
    seen: dict[str, int] = {}
    for i, f in enumerate(flows):
        rng = np.random.default_rng([int(seed) & 0xFFFFFFFF, _stream_key(f, seen)])
        for n, t in enumerate(_arrivals(rng, f, duration)):
            trips.append((round(t, 2), f"f{i}_{n}", _pick_type(rng, f), f))
    trips.sort(key=lambda x: (x[0], x[1]))
    return trips


def write_routes(path: Path, flows: list[Flow], *, seed: int, duration: float) -> list[float]:
    """Write trips for all flows and return their departure times (sorted)."""
    trips = generate_trips(flows, seed=seed, duration=duration)
    lines = ["<routes>", VTYPES.rstrip("\n")]
    for depart, vid, vtype, f in trips:
        lines.append(
            f'  <trip id="{vid}" type="{vtype}" depart="{depart:.2f}" from="{f.origin}" to="{f.destination}" '
            'departLane="best" departSpeed="max"/>'
        )
    lines.append("</routes>")
    Path(path).write_text("\n".join(lines) + "\n")
    return [depart for depart, _, _, _ in trips]


def expected_counts(flows: list[Flow], t0: float, t1: float, duration: float) -> dict[str, float]:
    """Expected vehicles per flow name in [t0, t1) — used by docs and tests."""
    out: dict[str, float] = {}
    for f in flows:
        key = f.name or f"{f.origin}>{f.destination}"
        out[key] = out.get(key, 0.0) + f.expected(t0, t1, duration)
    return out
