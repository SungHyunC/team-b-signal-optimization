"""Test scenarios: demand plus timed events.

Owner: Scenarios & analysis (Aditya, with Doyoung). Baseline registry with the
rush-hour scenario; add scenarios with @register.

A Scenario is pure data: OD flows (teamb.demand.routes.Flow) and timed Events. Event
kinds map to methods of teamb.scenarios.events.ScenarioRuntime (dispatch_ev,
close_road, reopen_road, start_attack, stop_attack).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from teamb import config
from teamb.demand.routes import Flow, write_routes


@dataclass
class Event:
    time: float
    kind: str  # name of a ScenarioRuntime method
    params: dict = field(default_factory=dict)


@dataclass
class Scenario:
    name: str
    title: str
    title_ko: str
    description: str
    flows: list[Flow]
    events: list[Event] = field(default_factory=list)
    warmup: float = config.WARMUP_S
    duration: float = config.WARMUP_S + config.MEASURE_S
    owner: str = ""
    defaults: dict = field(default_factory=dict)
    departs: list[float] = field(default_factory=list)  # filled by build_routes

    def build_routes(self, path: Path, seed: int) -> Path:
        self.departs = write_routes(path, self.flows, seed=seed, duration=self.duration)
        return Path(path)

    def describe(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "title_ko": self.title_ko,
            "description": self.description,
            "duration": self.duration,
            "warmup": self.warmup,
            "events": [{"time": e.time, "kind": e.kind, "params": e.params} for e in self.events],
            "owner": self.owner,
        }


REGISTRY: dict[str, Callable[[], Scenario]] = {}


def register(factory: Callable[[], Scenario]) -> Callable[[], Scenario]:
    REGISTRY[factory().name] = factory
    return factory


def get_scenario(name: str, **overrides) -> Scenario:
    if name not in REGISTRY:
        raise KeyError(f"unknown scenario '{name}'. Available: {sorted(REGISTRY)}")
    scenario = copy.deepcopy(REGISTRY[name]())
    for key, value in overrides.items():
        setattr(scenario, key, value)
    return scenario


def available() -> list[dict]:
    return [factory().describe() for factory in REGISTRY.values()]


# --- built-in scenarios ------------------------------------------------------
def corridor_flows(eb: float, wb: float, cross: float, turn: float) -> list[Flow]:
    """Through traffic both ways on the arterial, cross-street traffic at every junction,
    and turning traffic between them (veh/h)."""
    flows = [Flow("W0_J1", "J4_E5", eb, name="EB through"), Flow("E5_J4", "J1_W0", wb, name="WB through")]
    for i, j in enumerate(config.JUNCTIONS, start=1):
        flows += [
            Flow(f"NN{i}_N{i}", f"{j}_S{i}", cross, name=f"SB cross {j}"),
            Flow(f"S{i}_{j}", f"N{i}_NN{i}", cross, name=f"NB cross {j}"),
            Flow("W0_J1", f"{j}_S{i}", turn, name=f"EB right at {j}"),
            Flow(f"S{i}_{j}", "J4_E5", turn, name=f"NB left onto arterial at {j}"),
            Flow(f"NN{i}_N{i}", "J1_W0", turn, name=f"SB right onto arterial at {j}"),
        ]
    return flows


@register
def rush_hour() -> Scenario:
    return Scenario(
        name="rush_hour",
        title="Baseline · Rush hour",
        title_ko="기본 · 출퇴근 혼잡",
        description="Heavy eastbound traffic on the arterial. Measures mean delay, stops and travel time.",
        flows=corridor_flows(eb=1100, wb=550, cross=130, turn=45),
        owner="Scenarios & analysis (Aditya)",
    )


from teamb.scenarios import catalog  # noqa: E402,F401  (registers the remaining scenarios)
