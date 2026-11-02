"""Write SUMO route files from origin–destination flows.

Arrivals are Poisson with a numpy generator seeded per run, so the same seed always
gives the same vehicles (REP-01) and every controller sees identical demand.
Vehicles are written as <trip>s; SUMO picks the route when the vehicle departs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

VTYPES = """\
  <vType id="car" vClass="passenger" length="4.5" minGap="2.5" maxSpeed="16.7" accel="2.6" decel="4.5" sigma="0.5"/>
  <vType id="truck" vClass="truck" length="9.0" minGap="3.0" maxSpeed="14.0" accel="1.3" decel="4.0" sigma="0.5" guiShape="truck"/>
  <vType id="bus" vClass="bus" length="12.0" minGap="3.0" maxSpeed="14.0" accel="1.2" decel="4.0" sigma="0.4" guiShape="bus"/>
  <vType id="ambulance" vClass="emergency" length="6.5" minGap="2.5" maxSpeed="22.0" accel="3.0" decel="6.0" sigma="0.2" speedFactor="1.3" guiShape="emergency" color="1,1,1"/>
  <vType id="firetruck" vClass="emergency" length="9.0" minGap="2.5" maxSpeed="20.0" accel="2.0" decel="5.0" sigma="0.2" speedFactor="1.2" guiShape="firebrigade" color="0.85,0.1,0.1"/>
"""


@dataclass
class Flow:
    origin: str  # entry edge id, e.g. "W0_J1"
    destination: str  # exit edge id, e.g. "J4_E5"
    veh_per_hour: float
    begin: float = 0.0
    end: float | None = None  # defaults to the scenario duration
    vtype: str = "car"
    name: str = ""


def write_routes(path: Path, flows: list[Flow], *, seed: int, duration: float) -> list[float]:
    """Write trips for all flows and return their departure times (sorted)."""
    rng = np.random.default_rng(seed)
    trips = []
    for i, f in enumerate(flows):
        end = duration if f.end is None else min(f.end, duration)
        rate = f.veh_per_hour / 3600.0
        if rate <= 0 or end <= f.begin:
            continue
        t = f.begin + rng.exponential(1.0 / rate)
        n = 0
        while t < end:
            trips.append((round(t, 2), f"f{i}_{n}", f))
            n += 1
            t += rng.exponential(1.0 / rate)
    trips.sort(key=lambda x: (x[0], x[1]))
    lines = ["<routes>", VTYPES.rstrip("\n")]
    for depart, vid, f in trips:
        lines.append(
            f'  <trip id="{vid}" type="{f.vtype}" depart="{depart:.2f}" from="{f.origin}" to="{f.destination}" '
            'departLane="best" departSpeed="max"/>'
        )
    lines.append("</routes>")
    Path(path).write_text("\n".join(lines) + "\n")
    return [depart for depart, _, _ in trips]
