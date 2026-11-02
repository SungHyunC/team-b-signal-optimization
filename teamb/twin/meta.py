"""What the twin UI can offer: controllers, scenarios, roads that can be closed, emergency
routes, fake-data attack targets. Everything is derived from the registries and the network
geometry, so new controllers/scenarios show up without touching the twin.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from teamb.twin.session import SPEEDS, SessionConfig, jsonable

APPROACH_NAMES = {"N": "north", "S": "south", "E": "east", "W": "west"}

# Curated emergency-vehicle routes for the Actions panel (origin/destination are edge ids).
# Routes whose edges are not in the current network are dropped automatically.
EMERGENCY_ROUTES = [
    {"id": "eb_arterial", "label": "Eastbound arterial (W0 → E5)", "origin": "W0_J1", "destination": "J4_E5"},
    {"id": "wb_arterial", "label": "Westbound arterial (E5 → W0)", "origin": "E5_J4", "destination": "J1_W0"},
    {"id": "nb_j2", "label": "Northbound through J2 (S2 → NN2)", "origin": "S2_J2", "destination": "N2_NN2"},
    {"id": "sb_j3", "label": "Southbound through J3 (NN3 → S3)", "origin": "NN3_N3", "destination": "J3_S3"},
    {"id": "s4_west", "label": "From S4, then west on the arterial (S4 → W0)", "origin": "S4_J4", "destination": "J1_W0"},
]

CLOSURE_CAUSES = [
    {"id": "flood", "label": "Flood"},
    {"id": "sinkhole", "label": "Sinkhole"},
    {"id": "accident", "label": "Crash / incident"},
]


@lru_cache(maxsize=1)
def geometry() -> dict:
    """Network geometry for the 3D scene. Same data as SimEnv.geometry(); computed once because
    the network does not change while the server runs."""
    from teamb.network.topology import load_topology

    return load_topology().geometry()


@lru_cache(maxsize=1)
def geometry_json() -> str:
    return json.dumps(geometry(), separators=(",", ":"))


def _direction(dx: float, dy: float) -> str:
    if abs(dx) >= abs(dy):
        return "eastbound" if dx > 0 else "westbound"
    return "northbound" if dy > 0 else "southbound"


def closable_edges(geo: dict) -> list[dict]:
    """Edges between two real junctions. Entry/exit edges (at dead ends) are left out because
    closing them blocks vehicle insertion or leaves trips with no route at all."""
    nodes = {j["id"]: j for j in geo["junctions"]}
    out = []
    for e in geo["edges"]:
        a, b = nodes.get(e["from"]), nodes.get(e["to"])
        if not a or not b or a["type"] == "dead_end" or b["type"] == "dead_end":
            continue
        direction = _direction(b["x"] - a["x"], b["y"] - a["y"])
        out.append(
            {
                "id": e["id"],
                "kind": e["kind"],
                "from": e["from"],
                "to": e["to"],
                "direction": direction,
                "label": f"{e['from']} → {e['to']} · {e['kind']}, {direction}",
            }
        )
    order = {"arterial": 0, "cross": 1, "back": 2}
    return sorted(out, key=lambda e: (order.get(e["kind"], 9), e["id"]))


def attack_targets(geo: dict) -> list[dict]:
    targets = []
    for j in sorted(geo["tls"]):
        approaches = geo["tls"][j]["approaches"]
        for side in ("N", "S", "W", "E"):
            if side in approaches:
                targets.append(
                    {
                        "junction": j,
                        "approach": side,
                        "edge": approaches[side]["edge"],
                        "label": f"{j} · {APPROACH_NAMES[side]} approach",
                    }
                )
    # The scenario's default target first.
    targets.sort(key=lambda t: (t["junction"], t["approach"]) != ("J2", "N"))
    return targets


def controllers() -> list[dict]:
    from teamb import controllers as ctl
    from teamb.controllers.base import Controller

    try:
        items = [dict(d) for d in ctl.available()]
    except Exception:  # one broken constructor must not take the whole UI down
        items = [
            {"name": n, "label": getattr(c, "label", n), "description": getattr(c, "description", ""), "owner": getattr(c, "owner", "")}
            for n, c in ctl.REGISTRY.items()
        ]
    for item in items:
        cls = ctl.REGISTRY.get(item.get("name"))
        if cls is not None:
            item.setdefault("observation_source", getattr(cls, "observation_source", None))
            # True when the controller implements the "AI recommends -> engineer approves" hook.
            item.setdefault("recommends", getattr(cls, "pending_recommendation", None) is not Controller.pending_recommendation)
    return items


def scenarios() -> list[dict]:
    from teamb import scenarios as sc

    items = [dict(d) for d in sc.available()]
    for item in items:
        factory = sc.REGISTRY.get(item.get("name"))
        if factory is not None and "defaults" not in item:
            try:
                item["defaults"] = dict(getattr(factory(), "defaults", {}) or {})
            except Exception:
                item["defaults"] = {}
    return items


def build_meta() -> dict:
    geo = geometry()
    edges = {e["id"] for e in geo["edges"]}
    return jsonable(
        {
            "controllers": controllers(),
            "scenarios": scenarios(),
            "closable_edges": closable_edges(geo),
            "closure_causes": CLOSURE_CAUSES,
            "emergency_routes": [r for r in EMERGENCY_ROUTES if r["origin"] in edges and r["destination"] in edges],
            "ev_kinds": [{"id": "ambulance", "label": "Ambulance"}, {"id": "firetruck", "label": "Fire truck"}],
            "junctions": sorted(geo["tls"]),
            "attack_targets": attack_targets(geo),
            "speeds": list(SPEEDS),
            "defaults": SessionConfig().to_dict(),
        }
    )


def list_reports(results_dir: Path) -> list[dict]:
    """Experiment reports written by teamb.experiments to <results_dir>/<name>/report.json."""
    reports = []
    for path in sorted(Path(results_dir).glob("*/report.json")):
        try:
            data = json.loads(path.read_text())
            mtime = path.stat().st_mtime
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        data.setdefault("name", path.parent.name)
        data["dir"] = path.parent.name
        data["modified_unix"] = round(mtime)
        reports.append(jsonable(data))
    reports.sort(key=lambda r: (str(r.get("created") or ""), r["modified_unix"]), reverse=True)
    return reports
