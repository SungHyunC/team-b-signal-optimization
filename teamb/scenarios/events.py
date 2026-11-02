"""Scenario events at runtime: scheduled by a Scenario or triggered from the twin.

Owner: Scenarios & analysis (Aditya). Every public method here can be used as an
Event kind or as a twin command.
"""
from __future__ import annotations

import traci


class ScenarioRuntime:
    def __init__(self, env, scenario):
        self.env = env
        self.pending = sorted(scenario.events, key=lambda e: e.time)
        self.closed: dict[str, dict] = {}
        self.attack: dict | None = None
        self._ev_seq = 0

    @property
    def conn(self):
        return self.env.conn

    def on_step(self, t: float) -> None:
        while self.pending and self.pending[0].time <= t:
            event = self.pending.pop(0)
            getattr(self, event.kind)(**event.params)

    # --- emergency vehicles ------------------------------------------------
    def dispatch_ev(self, origin: str = "W0_J1", destination: str = "J4_E5", kind: str = "ambulance") -> str:
        self._ev_seq += 1
        vid = f"{kind}_{self._ev_seq}"
        route_id = f"route_{vid}"
        edges = self.env.topology.shortest_path(origin, destination)
        self.conn.route.add(route_id, edges)
        self.conn.vehicle.add(vid, route_id, typeID=kind, depart="now", departLane="best", departSpeed="max")
        self.env.note_extra_vehicle()
        self.env.log_event("ev_dispatched", vehicle=vid, kind=kind, origin=origin, destination=destination)
        return vid

    # --- road closures ------------------------------------------------------
    def close_road(self, edge: str, cause: str = "flood") -> None:
        if edge in self.closed:
            return
        for lane in self.env.topology.edge_lanes(edge):
            self.conn.lane.setDisallowed(lane, ["all"])
        self.conn.edge.adaptTraveltime(edge, 1e6)
        self.closed[edge] = {"edge": edge, "cause": cause, "since": self.env.t}
        rerouted = self._reroute_around(edge)
        self.env.log_event("road_closed", edge=edge, cause=cause, rerouted=rerouted)

    def reopen_road(self, edge: str) -> None:
        if edge not in self.closed:
            return
        for lane in self.env.topology.edge_lanes(edge):
            self.conn.lane.setDisallowed(lane, [])
        lane0 = self.env.topology.net.getEdge(edge)
        self.conn.edge.adaptTraveltime(edge, lane0.getLength() / lane0.getSpeed())
        self.closed.pop(edge)
        self.env.log_event("road_reopened", edge=edge)

    def _reroute_around(self, edge: str) -> int:
        n = 0
        v = self.conn.vehicle
        for vid in v.getIDList():
            route = v.getRoute(vid)
            idx = v.getRouteIndex(vid)
            if edge in route[idx + 1 :]:
                try:
                    v.rerouteTraveltime(vid, currentTravelTimes=False)
                    n += 1
                except traci.TraCIException:
                    pass
        return n

    def closed_edges(self) -> list[dict]:
        return list(self.closed.values())

    # --- fake navigation data ------------------------------------------------
    def start_attack(self, junction: str = "J2", approach: str = "N", n: int = 99) -> None:
        self.env.sensors.inject_fake_reports(junction, approach, n)
        self.attack = {"junction": junction, "approach": approach, "n": n, "since": self.env.t}
        self.env.log_event("attack_started", junction=junction, approach=approach, n=n)

    def stop_attack(self) -> None:
        self.env.sensors.clear_fake_reports()
        self.attack = None
        self.env.log_event("attack_stopped")
