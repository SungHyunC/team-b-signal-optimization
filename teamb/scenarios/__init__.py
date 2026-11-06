"""Test scenarios: demand plus timed events.

Owner: Scenarios & analysis (Aditya, with Doyoung). The catalog lives in
`teamb/scenarios/catalog.py`; add a scenario there with @register (see
docs/roles/scenarios-analysis.md).

A Scenario is pure data: OD flows (teamb.demand.routes.Flow) and timed Events. Event kinds
are methods of teamb.scenarios.events.ScenarioRuntime (dispatch_ev, close_road, reopen_road,
start_attack, stop_attack); the twin can send the same names as commands.

    get_scenario("rush_hour")                        # a fresh copy
    get_scenario("rush_hour", demand_scale=1.2)      # every flow × 1.2 (sensitivity runs)
    get_scenario("road_closure", events=[{"time": 1200, "kind": "close_road", "params": {"edge": "J2_J3"}}])
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Callable

from teamb import config
from teamb.demand.corridor import CorridorDemand
from teamb.demand.routes import VTYPE_IDS, Flow, write_routes
from teamb.scenarios import routing
from teamb.scenarios.events import EV_KINDS, EVENT_KINDS, MAX_FAKE_REPORTS


@dataclass
class Event:
    time: float
    kind: str  # name of a ScenarioRuntime method (EVENT_KINDS)
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
    defaults: dict = field(default_factory=dict)  # run defaults, e.g. {"coverage": 0.25}
    departs: list[float] = field(default_factory=list)  # filled by build_routes
    category: str = "baseline"  # baseline | demand | emergency | disaster | security
    question: str = ""  # the one question this scenario answers
    measures: list[str] = field(default_factory=list)  # summary fields to read first

    def build_routes(self, path: Path, seed: int) -> Path:
        self.departs = write_routes(path, self.flows, seed=seed, duration=self.duration)
        return Path(path)

    def expected_vehicles(self, t0: float | None = None, t1: float | None = None) -> float:
        """Expected number of scheduled trips in [t0, t1) (default: the measurement window)."""
        t0 = self.warmup if t0 is None else t0
        t1 = self.duration if t1 is None else t1
        return sum(f.expected(t0, t1, self.duration) for f in self.flows)

    def describe(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "title_ko": self.title_ko,
            "description": self.description,
            "category": self.category,
            "question": self.question,
            "measures": list(self.measures),
            "duration": self.duration,
            "warmup": self.warmup,
            "flows": len(self.flows),
            "expected_trips_in_window": round(self.expected_vehicles()),
            "events": [{"time": e.time, "kind": e.kind, "params": e.params} for e in self.events],
            "defaults": dict(self.defaults),
            "owner": self.owner,
        }

    def od_pairs(self) -> dict[tuple[str, str], str]:
        """{(origin edge, destination edge): flow name} for every flow (first name wins)."""
        pairs: dict[tuple[str, str], str] = {}
        for f in self.flows:
            pairs.setdefault((f.origin, f.destination), f.name or f"{f.origin}>{f.destination}")
        return pairs

    def closure_error(self, topology, edges, closed=()) -> str | None:
        """Why closing `edges` (with `closed` already closed) would break this scenario's
        trips, or None. The same check the runtime applies (routing.closure_error)."""
        pairs = self.od_pairs()
        return routing.closure_error(topology, edges, closed, list(pairs), pairs)

    def validate(self, topology) -> list[str]:
        """Problems that would break a run or silently skip an event (empty list = fine).

        Events are replayed in time order, so a closure is checked against the closures
        that are active at that moment, exactly as the runtime will check it."""
        problems = []
        edges = {e.getID() for e in topology.net.getEdges()}
        for f in self.flows:
            for edge in (f.origin, f.destination):
                if edge not in edges:
                    problems.append(f"flow '{f.name}': unknown edge {edge}")
            for vtype in (f.mix or {f.vtype: 1.0}):
                if vtype not in VTYPE_IDS:
                    problems.append(f"flow '{f.name}': unknown vehicle type {vtype}")
        closed: set[str] = set()
        for e in sorted(self.events, key=lambda ev: ev.time):
            where = f"event at {e.time}"
            if e.kind not in EVENT_KINDS:
                problems.append(f"{where}: unknown kind {e.kind}")
            if not 0 <= e.time < self.duration:
                problems.append(f"{where}: outside the run (0–{self.duration} s)")
            params = e.params if isinstance(e.params, dict) else {}
            if not isinstance(e.params, dict):
                problems.append(f"{where}: params must be a dict, got {type(e.params).__name__}")
            unknown = False
            for key in ("edge", "origin", "destination"):
                if key in params and params[key] not in edges:
                    problems.append(f"{where}: unknown edge {params[key]}")
                    unknown = True
            if e.kind in ("close_road", "reopen_road"):
                if "edge" not in params:
                    problems.append(f"{where}: {e.kind} needs an 'edge'")
                    continue
                if unknown:
                    continue
                pair = [params["edge"], routing.reverse_edge(params["edge"])] if params.get("both_directions") else [params["edge"]]
                if e.kind == "reopen_road":
                    closed -= set(pair)
                    continue
                error = self.closure_error(topology, pair, closed)
                if error:
                    problems.append(f"{where}: {error}")
                else:
                    closed |= set(pair)
            elif e.kind == "dispatch_ev":
                if params.get("kind", "ambulance") not in EV_KINDS:
                    problems.append(f"{where}: unknown EV kind {params.get('kind')}")
                origin, destination = params.get("origin", "W0_J1"), params.get("destination", "J4_E5")
                if not unknown and routing.stranded_pairs(topology, [(origin, destination)], closed):
                    problems.append(f"{where}: no open route for the EV from {origin} to {destination} (closed: {sorted(closed)})")
            elif e.kind == "start_attack":
                junction = params.get("junction", "J2")
                if junction not in topology.tls_ids:
                    problems.append(f"{where}: unknown junction {junction}")
                elif params.get("approach", "N") not in topology.approach_lanes[junction]:
                    problems.append(f"{where}: junction {junction} has no approach {params.get('approach')}")
                try:
                    n = int(params.get("n", 99))
                except (TypeError, ValueError):
                    problems.append(f"{where}: n must be an integer, got {params.get('n')!r}")
                else:
                    if not 1 <= n <= MAX_FAKE_REPORTS:
                        problems.append(f"{where}: n must be between 1 and {MAX_FAKE_REPORTS}, got {n}")
        if not 0 <= self.warmup < self.duration:
            problems.append("warmup must be inside the run")
        return problems


REGISTRY: dict[str, Callable[[], Scenario]] = {}
_FIELDS = {f.name for f in fields(Scenario)}


def register(factory: Callable[[], Scenario]) -> Callable[[], Scenario]:
    scenario = factory()
    bad = [e.kind for e in scenario.events if e.kind not in EVENT_KINDS]
    if bad:
        raise ValueError(f"scenario '{scenario.name}' uses unknown event kinds {bad}")
    REGISTRY[scenario.name] = factory
    return factory


def _coerce(key: str, value):
    """Accept plain dicts (from JSON/YAML experiment configs) for flows and events."""
    if key == "events":
        return [e if isinstance(e, Event) else Event(**e) for e in value]
    if key == "flows":
        return [f if isinstance(f, Flow) else Flow(**f) for f in value]
    return value


def get_scenario(name: str, **overrides) -> Scenario:
    """A fresh copy of a registered scenario. Overrides set Scenario fields (e.g. events,
    warmup, duration); `demand_scale=x` multiplies every flow's rate by x."""
    if name not in REGISTRY:
        raise KeyError(f"unknown scenario '{name}'. Available: {sorted(REGISTRY)}")
    scenario = copy.deepcopy(REGISTRY[name]())
    scale = overrides.pop("demand_scale", None)
    for key, value in overrides.items():
        if key not in _FIELDS:
            raise ValueError(f"unknown scenario parameter '{key}' (valid: demand_scale, {', '.join(sorted(_FIELDS))})")
        setattr(scenario, key, _coerce(key, value))
    if scale is not None and float(scale) != 1.0:
        scenario.flows = [f.scaled(float(scale)) for f in scenario.flows]
        scenario.defaults = {**scenario.defaults, "demand_scale": float(scale)}
    return scenario


def available() -> list[dict]:
    return [factory().describe() for factory in REGISTRY.values()]


def corridor_flows(eb: float, wb: float, cross: float, turn: float) -> list[Flow]:
    """Legacy helper (v1 catalog): through traffic both ways, `cross` veh/h each way on every
    cross street and `turn` veh/h for each right turn. New code: teamb.demand.corridor."""
    return CorridorDemand(
        eb_through=eb, wb_through=wb, cross_through=cross, eb_right=turn, wb_right=0, nb_right=turn,
        sb_right=turn, nb_left=0, sb_left=0,
    ).flows()


from teamb.scenarios import catalog  # noqa: E402,F401  (registers the built-in scenarios)
