"""Signal-data API for navigation apps (Busan-style sharing of live signal timing).

Owner: Scenarios & analysis (Aditya) — the optional back-end extra from the prototype plan.
The twin server mounts this router; `get_env` returns the live SimEnv (in the twin: a
thread-safe proxy of it) or None when nothing is running.

Endpoints (JSON, prefix /api/v1)
    GET /api/v1                  index: version, endpoints, units, whether a simulation runs
    GET /api/v1/spat             signal phase & timing (SPaT) for every junction
    GET /api/v1/spat/{junction}  one junction (404 for an unknown id)
    GET /api/v1/advisories       road closures, active emergency preemptions, EV warnings
    GET /api/v1/network          junctions, approaches, lanes and movements (static; works
                                 without a running simulation, for app developers)

Every response shares one envelope: api_version, source, generated_at (UTC wall clock, ISO
8601), t (simulation seconds), scenario, controller and units. Errors: 503 when no
simulation is running (or it has finished), 404 for an unknown junction; the body is
FastAPI's standard {"detail": "..."}.

Thread safety: handlers only read Python-side state — the safety supervisor, the scenario
runtime (closures, EV tracker) and the static topology. They never talk to TraCI, so a web
request thread cannot interfere with the simulation's connection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from fastapi import APIRouter, HTTPException, Response

from teamb import config
from teamb.sim.phases import SIGNALS, approach_colors, axis_of

API_VERSION = "1.0"
SOURCE = "team-b-signal-twin"
UNITS = {
    "time": "s (simulation clock, seconds since the run started)",
    "durations": "s",
    "distance": "m",
    "speed": "m/s",
    "position": "m, SUMO network coordinates (x east, y north)",
    "heading": "deg, 0 = north, clockwise",
}
CONVENTIONS = {
    "approach": "side the traffic comes FROM: W, E, N or S",
    "axis": "EW serves W+E approaches, NS serves N+S approaches",
    "signal_cycle": "EW_G → EW_Y → EW_AR → NS_G → NS_Y → NS_AR → EW_G",
    "left_turns": "permissive: green, but yield to oncoming traffic",
    "next_change": "min/max are bounds from the safety rules; 'likely' comes from the timing plan when the controller has one",
}
STATE_NAMES = {"G": "green", "Y": "yellow", "R": "red"}
SIDE_NAMES = {"W": "west", "E": "east", "N": "north", "S": "south"}
PLAN_HORIZON_S = 300  # how far ahead a timing plan is searched for the next switch
EV_WARNING_DISTANCE_M = 300.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _envelope(env) -> dict:
    scenario = getattr(env, "scenario", None) if env is not None else None
    controller = getattr(env, "controller", None) if env is not None else None
    return {
        "api_version": API_VERSION,
        "source": SOURCE,
        "generated_at": _now_iso(),
        "t": float(env.t) if env is not None else None,
        "scenario": getattr(scenario, "name", None),
        "controller": getattr(controller, "name", None),
        "units": UNITS,
    }


def _round(x: float | None, digits: int = 1) -> float | None:
    return None if x is None else round(float(x), digits)


# --- signal timing ----------------------------------------------------------------
def _plan_switch_in(env, junction: str, axis: str) -> float | None:
    """Seconds until the controller's timing plan (if it has one) asks for the other axis."""
    plan = getattr(getattr(env, "controller", None), "plan", None)
    axis_at = getattr(plan, "axis_at", None)
    if axis_at is None:
        return None
    t = float(env.t)
    try:
        for s in range(0, PLAN_HORIZON_S + 1):
            if axis_at(junction, t + s) != axis:
                return float(s)
    except Exception:  # a plan that cannot answer is simply not used
        return None
    return None


def _junction_spat(env, junction: str) -> dict:
    sup = env.supervisor
    js = sup.junctions[junction]
    signal, t_in = js.signal, float(js.t_in)
    axis, part = axis_of(signal), signal[3:]
    yellow, all_red, min_green = float(sup.yellow), float(sup.all_red), float(sup.min_green)
    remaining_min = float(sup.min_time_to_change(junction))
    preempted = js.preempted_by is not None
    likely_green_end = None
    if part == "G" and preempted and js.preempted_by != axis:
        # an emergency vehicle needs the other axis: this green ends as soon as the shorter
        # preemption minimum allows
        remaining_min = max(0.0, float(sup.preempt_min_green) - t_in)
        likely_green_end = remaining_min
    elif part == "G" and not preempted:
        switch = _plan_switch_in(env, junction, axis)
        if switch is not None:
            likely_green_end = max(switch, remaining_min)

    # When does the current signal state end?  Yellow and all-red are fixed; green has a minimum.
    if part == "G":
        state_end = {"min": remaining_min, "max": None, "likely": likely_green_end}
    elif part == "Y":
        left = max(0.0, yellow - t_in)
        state_end = {"min": left, "max": left, "likely": left}
    else:
        left = max(0.0, all_red - t_in)
        state_end = {"min": left, "max": left, "likely": left}

    colors = approach_colors(signal)
    topo = env.topology
    approaches = {}
    for side, edge in sorted(topo.approach_edges[junction].items()):
        color = colors[side]
        served = axis_of(signal) == ("EW" if side in ("W", "E") else "NS")
        if served and part == "G":  # this approach has green now
            change = dict(state_end)
            next_color = "Y"
        elif served and part == "Y":
            change, next_color = dict(state_end), "R"
        elif served:  # all-red at the end of its own green: the other axis is served next
            base = state_end["min"]
            change = {"min": base + min_green + yellow + all_red, "max": None, "likely": None}
            next_color = "G"
        elif part == "G":  # red while the other axis has green
            lk = state_end["likely"]
            change = {"min": remaining_min + yellow + all_red, "max": None, "likely": None if lk is None else lk + yellow + all_red}
            next_color = "G"
        elif part == "Y":
            left = state_end["min"] + all_red
            change, next_color = {"min": left, "max": left, "likely": left}, "G"
        else:
            change, next_color = dict(state_end), "G"
        approaches[side] = {
            "edge": edge,
            "color": color,
            "state": STATE_NAMES[color],
            "next_color": next_color,
            "next_change_in_s": {k: _round(v) for k, v in change.items()},
            "next_change_at_t": {k: _round(None if v is None else float(env.t) + v) for k, v in change.items()},
            "permissive_left": color == "G",
        }
    return {
        "junction": junction,
        # the same fields as frame.signals[J] (ARCHITECTURE.md) ...
        "signal": signal,
        "axis": axis,
        "colors": colors,
        "time_in_state": round(t_in, 1),
        "min_time_to_change": round(remaining_min, 1),
        "preempted_by": js.preempted_by,
        # ... plus timing details for navigation apps
        "phase": {"G": "green", "Y": "yellow", "AR": "all_red"}[part],
        "state_ends_in_s": {k: _round(v) for k, v in state_end.items()},
        "prediction": "timing_plan" if likely_green_end is not None else ("exact" if part != "G" else "minimum_only"),
        "preempted": preempted,
        "approaches": approaches,
    }


# --- advisories -------------------------------------------------------------------
def _closures(env) -> list[dict]:
    runtime = getattr(env, "runtime", None)
    if runtime is None:
        return []
    t = float(env.t)
    out = []
    for c in runtime.closed_edges():
        a, _, b = c["edge"].partition("_")
        detour = list(c.get("detour") or [])
        nodes = [a] + [e.partition("_")[2] for e in detour]
        out.append(
            {
                "edge": c["edge"],
                "from_node": a,
                "to_node": b,
                "direction": c.get("direction"),
                "kind": c.get("kind"),
                "lanes": c.get("lanes"),
                "cause": c.get("cause"),
                "since_t": c.get("since"),
                "closed_for_s": _round(t - float(c.get("since", t))),
                "detour": detour,
                "detour_nodes": nodes if detour else [],
            }
        )
    return out


def _preemptions(env) -> list[dict]:
    sup = env.supervisor
    active = {}
    for vid, junction in set(getattr(env, "_ev_active", set()) or set()):
        active.setdefault(junction, vid)
    starts = {}
    for p in list(getattr(env, "preemptions", []) or []):
        starts[(p.get("vehicle"), p.get("junction"))] = p.get("t")
    runtime = getattr(env, "runtime", None)
    evs = getattr(runtime, "evs", {}) if runtime is not None else {}
    out = []
    for j, js in sup.junctions.items():
        if js.preempted_by is None:
            continue
        vid = active.get(j)
        out.append(
            {
                "junction": j,
                "axis": js.preempted_by,
                "vehicle": vid,
                "kind": (evs.get(vid) or {}).get("kind") if vid else None,
                "since_t": starts.get((vid, j)),
                "signal": js.signal,
            }
        )
    return out


def _emergency_vehicles(env) -> list[dict]:
    runtime = getattr(env, "runtime", None)
    if runtime is None or not hasattr(runtime, "active_evs"):
        return []
    out = []
    for ev in runtime.active_evs():
        live = ev.get("live") or {}
        out.append(
            {
                "vehicle": ev["vehicle"],
                "kind": ev["kind"],
                "status": ev["status"],
                "origin": ev["origin"],
                "destination": ev["destination"],
                "dispatched_t": ev.get("dispatched_at"),
                "edge": live.get("edge"),
                "position": live.get("position"),
                "speed_mps": live.get("speed_mps"),
                "heading_deg": live.get("heading_deg"),
                "next_junction": live.get("next_junction"),
                "approach": live.get("approach"),
                "distance_to_junction_m": live.get("distance_to_junction_m"),
                "eta_s": live.get("eta_s"),
            }
        )
    return out


def _warnings(closures: list[dict], preemptions: list[dict], evs: list[dict]) -> list[dict]:
    warnings = []
    for ev in evs:
        dist = ev.get("distance_to_junction_m")
        if ev.get("next_junction") and dist is not None and dist <= EV_WARNING_DISTANCE_M:
            side = SIDE_NAMES.get(ev.get("approach") or "", "an approach")
            eta = ev.get("eta_s")
            when = f"in about {eta:.0f} s" if eta is not None else "now (stopped in traffic)"
            warnings.append(
                {
                    "type": "emergency_vehicle_approaching",
                    "severity": "high",
                    "junction": ev["next_junction"],
                    "approach": ev.get("approach"),
                    "vehicle": ev["vehicle"],
                    "kind": ev["kind"],
                    "distance_m": dist,
                    "eta_s": eta,
                    "message": f"{ev['kind'].capitalize()} approaching {ev['next_junction']} from the {side} {when}. "
                    "Pull over, yield and keep the junction clear.",
                }
            )
    for p in preemptions:
        warnings.append(
            {
                "type": "signal_preempted",
                "severity": "medium",
                "junction": p["junction"],
                "axis": p["axis"],
                "vehicle": p["vehicle"],
                "message": f"Signals at {p['junction']} are giving {p['axis']} green to an emergency vehicle; "
                "expect a longer red on the other approaches.",
            }
        )
    for c in closures:
        detour = " → ".join(c["detour_nodes"]) if c["detour_nodes"] else "no signed detour"
        warnings.append(
            {
                "type": "road_closed",
                "severity": "medium",
                "edge": c["edge"],
                "message": f"{c['from_node']}→{c['to_node']} {c.get('direction') or ''} closed ({c.get('cause')}). Detour: {detour}.",
            }
        )
    return warnings


# --- static network description -----------------------------------------------------------
_NETWORK_CACHE: dict[int, dict] = {}
TURN_NAMES = {"s": "through", "l": "left", "L": "left", "r": "right", "R": "right", "t": "u-turn", "T": "u-turn"}


def _network(topo) -> dict:
    key = id(topo)
    if key in _NETWORK_CACHE:
        return _NETWORK_CACHE[key]
    from teamb.scenarios import routing

    geo = topo.geometry()
    junctions = []
    for j in topo.tls_ids:
        tls = geo["tls"][j]
        approaches = {}
        for side, a in sorted(tls["approaches"].items()):
            edge = topo.net.getEdge(a["edge"])
            moves: dict[str, dict] = {}
            for link in topo.links[j]:
                if link.approach != side or link.direction in ("t", "T"):
                    continue
                m = moves.setdefault(
                    link.to_edge,
                    {
                        "to_edge": link.to_edge,
                        "turn": TURN_NAMES.get(link.direction, link.direction),
                        "control": "permissive" if link.direction in ("l", "L") else "protected",
                        "from_lanes": [],
                        "link_indices": [],
                    },
                )
                m["from_lanes"].append(link.from_lane)
                m["link_indices"].append(link.index)
            approaches[side] = {
                "edge": a["edge"],
                "lanes": a["lanes"],
                "lane_count": len(a["lanes"]),
                "length_m": round(edge.getLength(), 1),
                "speed_limit_mps": round(edge.getSpeed(), 2),
                "axis": a["axis"],
                "heading_deg": a["heading"],
                "stop_line": a["stop"],
                "movements": sorted(moves.values(), key=lambda m: m["link_indices"][0]),
            }
        junctions.append({"id": j, "x": tls["x"], "y": tls["y"], "signalized": True, "approaches": approaches, "exits": tls["exits"]})
    edges = [{**routing.describe_edge(topo, e["id"]), "id": e["id"]} for e in geo["edges"]]
    data = {
        "junctions": junctions,
        "edges": sorted(edges, key=lambda e: e["id"]),
        "bounds": geo["bounds"],
        "signal_rules": {
            "states": list(SIGNALS),
            "min_green_s": config.MIN_GREEN_S,
            "yellow_s": config.YELLOW_S,
            "all_red_s": config.ALL_RED_S,
            "preempt_min_green_s": config.PREEMPT_MIN_GREEN_S,
            "base_cycle_s": config.BASE_CYCLE_S,
            "ev_preempt_distance_m": config.EV_PREEMPT_DISTANCE_M,
        },
        "conventions": CONVENTIONS,
    }
    _NETWORK_CACHE[key] = data
    return data


# --- the router -------------------------------------------------------------------------
def build_router(get_env: Callable[[], object | None]) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["signal data"])
    errors = {503: {"description": "no simulation running"}}

    def _live_env():
        try:
            env = get_env()
        except Exception:  # e.g. the twin is restarting the simulation
            env = None
        if env is None or getattr(env, "conn", None) is None or getattr(env, "supervisor", None) is None:
            raise HTTPException(status_code=503, detail="no simulation running")
        if getattr(env, "summary", None) is not None:
            raise HTTPException(status_code=503, detail="the simulation has finished")
        return env

    def _no_store(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    def _index(response: Response):
        try:
            env = get_env()
        except Exception:
            env = None
        running = env is not None and getattr(env, "conn", None) is not None and getattr(env, "summary", None) is None
        _no_store(response)
        return {
            **_envelope(env if running else None),
            "running": running,
            "endpoints": {
                "/api/v1/spat": "signal phase and timing for every junction",
                "/api/v1/spat/{junction}": "one junction, e.g. /api/v1/spat/J2",
                "/api/v1/advisories": "road closures, emergency-vehicle preemptions and warnings",
                "/api/v1/network": "junctions, approaches, lanes and movements (static)",
            },
            "conventions": CONVENTIONS,
        }

    router.add_api_route("", _index, methods=["GET"], summary="API index")
    router.add_api_route("/", _index, methods=["GET"], include_in_schema=False)

    @router.get("/spat", responses=errors, summary="Signal phase & timing for all junctions")
    def spat(response: Response):
        env = _live_env()
        _no_store(response)
        sup = env.supervisor
        return {
            **_envelope(env),
            "timing_rules": {
                "min_green_s": sup.min_green,
                "preempt_min_green_s": sup.preempt_min_green,
                "yellow_s": sup.yellow,
                "all_red_s": sup.all_red,
            },
            "junctions": {j: _junction_spat(env, j) for j in sorted(sup.junctions)},
        }

    @router.get(
        "/spat/{junction}",
        responses={**errors, 404: {"description": "unknown junction"}},
        summary="Signal phase & timing for one junction",
    )
    def spat_one(junction: str, response: Response):
        env = _live_env()
        known = sorted(env.supervisor.junctions)
        match = next((j for j in known if j.lower() == junction.lower()), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"unknown junction '{junction}' (known: {', '.join(known)})")
        _no_store(response)
        return {**_envelope(env), **_junction_spat(env, match)}

    @router.get("/advisories", responses=errors, summary="Closures, emergency preemptions and warnings")
    def advisories(response: Response):
        env = _live_env()
        _no_store(response)
        closures = _closures(env)
        preemptions = _preemptions(env)
        evs = _emergency_vehicles(env)
        return {
            **_envelope(env),
            "counts": {"closures": len(closures), "preemptions": len(preemptions), "emergency_vehicles": len(evs)},
            "closures": closures,
            "preemptions": preemptions,
            "emergency_vehicles": evs,
            "warnings": _warnings(closures, preemptions, evs),
        }

    @router.get("/network", summary="Static network description for app developers")
    def network():
        try:
            env = get_env()
        except Exception:
            env = None
        topo = getattr(env, "topology", None) if env is not None else None
        if topo is None:
            from teamb.network.topology import load_topology

            topo = load_topology()
        live = env is not None and getattr(env, "conn", None) is not None
        return {**_envelope(env if live else None), **_network(topo)}

    return router
