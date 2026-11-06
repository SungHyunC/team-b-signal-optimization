"""Scenario events at runtime: scheduled by a Scenario or triggered from the twin.

Owner: Scenarios & analysis (Aditya). Every method named in EVENT_KINDS can be used as a
scenario Event kind or as a twin command ({"type": "close_road", "edge": "J2_J3"}).

Rules every event follows
- Bad parameters (unknown edge, junction or vehicle kind) raise ValueError with a readable
  message. Scheduled events never stop a run: `on_step` catches the error and logs an
  `event_failed` event instead.
- Idempotent: closing a closed road, reopening an open one, starting the same attack twice
  or stopping when nothing runs changes nothing and logs nothing.
- Every real change is logged with `env.log_event` (road_closed, road_reopened,
  ev_dispatched, attack_started, attack_stopped) so the twin can show it.

Road closures (flood, sinkhole, earthquake damage)
1. The edge's lanes stop admitting vehicles (lane permissions). SUMO's router respects
   permissions, so trips inserted later are routed around the closure when they depart.
   Vehicles already on the edge, or inside the junction in front of it, drive off normally.
2. Every vehicle whose remaining route uses the edge is re-routed at once, and every newly
   departed vehicle is checked again (should SUMO ever insert one through it).
3. While a closure lasts, navigation-app users (the probe vehicles, see `coverage`) that are
   on a detour re-route every REROUTE_PERIOD_S on smoothed live travel times, so detour
   traffic spreads over the back street instead of piling onto one turn. Everyone else keeps
   the signed (free-flow fastest) detour.
4. Reopening restores the original lane permissions and free-flow routing weights and
   re-routes the vehicles still in the network, so traffic returns to the arterial.
A closure is refused (ValueError, so a scheduled one becomes `event_failed` and a twin
command gets ok: false) unless every edge is an inner edge (between J* and N* nodes) AND
every trip the scenario can still insert keeps a route: an inner edge can be a flow's origin
(the stadium garage exit N3_J3 in special_event), and several closures together can cut an
exit off (all three roads into N2). SUMO quits on such a trip, so `routing.closure_error`
checks every origin-destination pair of the scenario's flows (and of waiting emergency
vehicles) against the closures before anything is closed. Scenario.validate runs the same
check over the scheduled events.
"""
from __future__ import annotations

import traci

from teamb import config
from teamb.scenarios import routing

EVENT_KINDS = ("dispatch_ev", "close_road", "reopen_road", "start_attack", "stop_attack")
EV_KINDS = ("ambulance", "firetruck")

CLOSED_WEIGHT_S = 1e6  # routing weight of a closed edge (belt and braces next to permissions)
REROUTE_PERIOD_S = 60.0  # navigation-app re-routing period while a closure is active
TT_SAMPLE_PERIOD_S = 10.0  # live travel-time sampling period for that re-routing
TT_SMOOTHING = 0.3  # weight of the newest travel-time sample (exponential smoothing)
TT_CAP_FACTOR = 6.0  # a congested edge counts at most 6 × its free-flow time + 60 s
EV_WARNING_DISTANCE_M = 300.0  # the signal-data API warns drivers this far ahead of an EV
MAX_FAKE_REPORTS = 500


class ScenarioRuntime:
    def __init__(self, env, scenario):
        self.env = env
        self.scenario = scenario
        self.pending = sorted(scenario.events, key=lambda e: e.time)
        self.closed: dict[str, dict] = {}  # edge -> {"edge", "cause", "since", ...}
        self.attack: dict | None = None
        self.evs: dict[str, dict] = {}  # every EV dispatched here: status, times, live position
        self.history: list[dict] = []  # finished closures and attacks, for analysis
        self.teleports = 0  # SUMO teleports (vehicles stuck > --time-to-teleport) seen so far
        self.failed_events = 0
        self.rerouted = 0  # vehicles re-routed because of closures (all causes)
        self._ev_seq = 0
        self._permissions: dict[str, list[str]] = {}  # lane -> allowed classes before closing
        self._detour_edges: set[str] = set()
        self._retry: set[str] = set()  # vehicles whose re-route did not avoid a closure yet
        self._live_tt: dict[str, float] = {}
        self._next_tt_sample = 0.0
        self._next_reroute = 0.0

    # --- plumbing --------------------------------------------------------------
    @property
    def conn(self):
        return self.env.conn

    @property
    def topology(self):
        return self.env.topology

    def _t(self) -> float:
        return float(getattr(self.env, "t", 0.0))

    def on_step(self, t: float) -> None:
        """Called by the env after every SUMO step."""
        while self.pending and self.pending[0].time <= t:
            event = self.pending.pop(0)
            try:
                if event.kind not in EVENT_KINDS:
                    raise ValueError(f"unknown event kind '{event.kind}' (expected one of {EVENT_KINDS})")
                getattr(self, event.kind)(**event.params)
            except traci.FatalTraCIError:
                raise
            except Exception as exc:  # a broken scheduled event must never stop the run
                self.failed_events += 1
                params = dict(event.params) if isinstance(event.params, dict) else repr(event.params)
                self.env.log_event("event_failed", kind=str(event.kind), params=params, error=f"{type(exc).__name__}: {exc}")
        sim = self.conn.simulation
        self.teleports += sim.getStartingTeleportNumber()
        if self.closed:
            self._check_departures(sim.getDepartedIDList())
            if self._retry:
                self._retry_reroutes()
            if t >= self._next_tt_sample:
                self._sample_travel_times()
                self._next_tt_sample = t + TT_SAMPLE_PERIOD_S
            if t >= self._next_reroute:
                self._navigation_reroute()
                self._next_reroute = t + REROUTE_PERIOD_S
        if any(ev["status"] in ("dispatched", "en_route") for ev in self.evs.values()):
            self._track_evs(t, sim)

    # --- emergency vehicles ------------------------------------------------------
    def dispatch_ev(self, origin: str = "W0_J1", destination: str = "J4_E5", kind: str = "ambulance") -> str:
        """Send an ambulance or fire truck from `origin` to `destination` (edge ids) on the
        fastest open route. Returns the vehicle id (e.g. 'ambulance_3')."""
        if kind not in EV_KINDS:
            raise ValueError(f"unknown emergency vehicle kind '{kind}' (expected one of {EV_KINDS})")
        for name, edge in (("origin", origin), ("destination", destination)):
            if not routing.has_edge(self.topology, edge):
                raise ValueError(f"unknown {name} edge '{edge}'")
        if origin in self.closed:
            raise ValueError(f"origin edge '{origin}' is closed")
        edges = self._route_for(origin, destination, kind)
        self._ev_seq += 1
        vid = f"{kind}_{self._ev_seq}"
        while vid in self.evs:  # never reuse an id, even if the counter was reset
            self._ev_seq += 1
            vid = f"{kind}_{self._ev_seq}"
        route_id = f"route_{vid}"
        self.conn.route.add(route_id, edges)
        self.conn.vehicle.add(vid, route_id, typeID=kind, depart="now", departLane="best", departSpeed="max")
        self.env.note_extra_vehicle()
        now = self._t()
        self.evs[vid] = {
            "vehicle": vid,
            "kind": kind,
            "origin": origin,
            "destination": destination,
            "route": list(edges),
            "status": "dispatched",
            "dispatched_at": now,
            "departed_at": None,
            "arrived_at": None,
            "travel_time_s": None,
            "response_time_s": None,
            "live": None,
        }
        self.env.log_event("ev_dispatched", vehicle=vid, kind=kind, origin=origin, destination=destination)
        return vid

    def _route_for(self, origin: str, destination: str, kind: str) -> list[str]:
        """Fastest open route: SUMO's router (respects closed lanes and the routing weights);
        falls back to the static network graph if SUMO finds nothing."""
        edges: list[str] = []
        try:
            edges = list(self.conn.simulation.findRoute(origin, destination, vType=kind).edges)
        except traci.TraCIException:
            edges = []
        if not edges:
            edges = routing.fastest_route(self.topology, origin, destination, avoid=self.closed) or []
        if not edges:
            raise ValueError(f"no open route from {origin} to {destination}")
        return edges

    def _track_evs(self, t: float, sim) -> None:
        departed = set(sim.getDepartedIDList())
        arrived = set(sim.getArrivedIDList())
        v = self.conn.vehicle
        for vid, ev in self.evs.items():
            if ev["status"] in ("arrived", "lost"):
                continue
            if vid in departed:
                ev["status"], ev["departed_at"] = "en_route", t
            if vid in arrived:
                ev.update(status="arrived", arrived_at=t, live=None)
                ev["travel_time_s"] = round(t - (ev["departed_at"] if ev["departed_at"] is not None else ev["dispatched_at"]), 1)
                ev["response_time_s"] = round(t - ev["dispatched_at"], 1)
                continue
            if ev["status"] != "en_route":
                continue
            try:
                road = v.getRoadID(vid)
                if not road:  # teleporting right now: no position to publish
                    ev["live"] = None
                    continue
                x, y = v.getPosition(vid)
                speed = v.getSpeed(vid)
                upcoming = v.getNextTLS(vid)
                live = {
                    "edge": road,
                    "position": [round(x, 2), round(y, 2)],
                    "speed_mps": round(speed, 2),
                    "heading_deg": round(v.getAngle(vid), 1),
                    "next_junction": None,
                    "approach": None,
                    "distance_to_junction_m": None,
                    "eta_s": None,
                }
                if upcoming:
                    tls, link_index, dist, _state = upcoming[0]
                    links = self.topology.links.get(tls, [])
                    approach = next((l.approach for l in links if l.index == link_index), None)
                    live.update(
                        next_junction=tls,
                        approach=approach,
                        distance_to_junction_m=round(dist, 1),
                        eta_s=round(dist / speed, 1) if speed > 0.5 else None,
                    )
                ev["live"] = live
            except traci.TraCIException:  # removed by SUMO (e.g. teleported away)
                ev.update(status="lost", live=None)

    def active_evs(self) -> list[dict]:
        """EVs dispatched or driving right now (copies, safe to serialize)."""
        return [dict(ev) for ev in list(self.evs.values()) if ev["status"] in ("dispatched", "en_route")]

    # --- road closures ------------------------------------------------------------
    def close_road(self, edge: str, cause: str = "flood", both_directions: bool = False) -> dict:
        """Close an inner edge to all traffic (optionally the opposite direction too).
        Refused (ValueError) if it would leave a trip of the scenario without a route."""
        edges = [edge, routing.reverse_edge(edge)] if both_directions else [edge]
        self._check_closable(edges)
        results = [self._close_one(e, cause) for e in edges]
        return results[0] if len(results) == 1 else {"edges": results}

    def _check_closable(self, edges: list[str]) -> None:
        """All edges are checked together (both directions of a closure at once)."""
        pairs, labels = self._od_pairs()
        error = routing.closure_error(self.topology, edges, self.closed, pairs, labels)
        if error:
            raise ValueError(error)

    def _od_pairs(self) -> tuple[list[tuple[str, str]], dict[tuple[str, str], str]]:
        """Origin-destination pairs that must keep a route: every scenario flow (their trips
        are inserted until the end of the run) and every EV still waiting to depart."""
        if not hasattr(self, "_flow_pairs"):
            labels: dict[tuple[str, str], str] = {}
            for f in getattr(self.scenario, "flows", []):
                labels.setdefault((f.origin, f.destination), f.name or f"{f.origin}>{f.destination}")
            self._flow_pairs, self._flow_labels = list(labels), labels
        waiting = [(ev["origin"], ev["destination"]) for ev in self.evs.values() if ev["status"] == "dispatched"]
        labels = dict(self._flow_labels)
        for vid, ev in self.evs.items():
            if ev["status"] == "dispatched":
                labels.setdefault((ev["origin"], ev["destination"]), vid)
        return self._flow_pairs + waiting, labels

    def _close_one(self, edge: str, cause: str) -> dict:
        if edge in self.closed:
            return {"edge": edge, "closed": False, "reason": "already closed"}
        lanes = self.topology.edge_lanes(edge)
        on_edge = list(self.conn.edge.getLastStepVehicleIDs(edge))
        for lane in lanes:
            self._permissions[lane] = list(self.conn.lane.getAllowed(lane))
            self.conn.lane.setDisallowed(lane, ["all"])
        self.conn.edge.adaptTraveltime(edge, CLOSED_WEIGHT_S)
        self.closed[edge] = {"edge": edge, "cause": str(cause), "since": self._t()}
        self._refresh_detours()
        rerouted, unavoidable = self._reroute_around({edge})
        info = routing.describe_edge(self.topology, edge)
        self.closed[edge].update(
            direction=info["direction"],
            kind=info["kind"],
            lanes=info["lanes"],
            detour=routing.detour(self.topology, edge, self.closed) or [],
            rerouted=rerouted,
            vehicles_on_edge=len(on_edge),
        )
        self._next_reroute = self._t() + REROUTE_PERIOD_S / 2  # first navigation update soon
        self.env.log_event(
            "road_closed", edge=edge, cause=str(cause), rerouted=rerouted, unavoidable=unavoidable, vehicles_on_edge=len(on_edge)
        )
        return {"edge": edge, "closed": True, "rerouted": rerouted, "unavoidable": unavoidable, "vehicles_on_edge": len(on_edge)}

    def reopen_road(self, edge: str, cause: str | None = None, both_directions: bool = False) -> dict:
        """Reopen a closed edge (no-op if it is open). `cause` is accepted and ignored so the
        twin can send the same parameters as for close_road."""
        edges = [edge, routing.reverse_edge(edge)] if both_directions else [edge]
        for e in edges:
            if not routing.has_edge(self.topology, e):
                raise ValueError(f"unknown edge '{e}'")
        results = [self._reopen_one(e) for e in edges]
        return results[0] if len(results) == 1 else {"edges": results}

    def _reopen_one(self, edge: str) -> dict:
        if edge not in self.closed:
            return {"edge": edge, "reopened": False, "reason": "not closed"}
        for lane in self.topology.edge_lanes(edge):
            self.conn.lane.setAllowed(lane, self._permissions.pop(lane, []))
        closure = self.closed.pop(edge)
        self._refresh_detours()
        self._set_static_weights()
        rerouted = self._reroute_all()
        if not self.closed:
            self._retry.clear()
        now = self._t()
        self.history.append({**closure, "type": "closure", "until": now, "duration_s": round(now - closure["since"], 1)})
        self.env.log_event("road_reopened", edge=edge, rerouted=rerouted)
        return {"edge": edge, "reopened": True, "rerouted": rerouted, "closed_for_s": round(now - closure["since"], 1)}

    def closed_edges(self) -> list[dict]:
        """Active closures for the frame / API: [{"edge", "cause", "since", ...}]."""
        return [dict(c) for c in list(self.closed.values())]

    def _refresh_detours(self) -> None:
        self._detour_edges = set()
        for e in self.closed:
            self._detour_edges.update(routing.detour(self.topology, e, self.closed) or [])

    def _route_blocked(self, vid: str) -> bool:
        v = self.conn.vehicle
        route = v.getRoute(vid)
        return any(e in self.closed for e in route[max(0, v.getRouteIndex(vid)) + 1 :])

    def _reroute(self, vid: str) -> bool:
        """Re-route one vehicle on the current routing weights; True if it now avoids closures."""
        try:
            self.conn.vehicle.rerouteTraveltime(vid, False)
            ok = not self._route_blocked(vid)
        except traci.TraCIException:
            return False
        if ok:
            self.rerouted += 1
        return ok

    def _reroute_around(self, edges: set[str]) -> tuple[int, int]:
        """Re-route every vehicle whose remaining route uses one of `edges`."""
        rerouted = unavoidable = 0
        v = self.conn.vehicle
        for vid in v.getIDList():
            try:
                route = v.getRoute(vid)
                ahead = route[max(0, v.getRouteIndex(vid)) + 1 :]
            except traci.TraCIException:
                continue
            if not any(e in edges for e in ahead):
                continue
            if self._reroute(vid):
                rerouted += 1
            else:
                # Inside the junction in front of the closure (it will drive onto the closed edge
                # and off again), or too close to the stop line: SUMO then re-routes from the NEXT
                # edge to avoid an emergency brake. Retried every step until it works.
                unavoidable += 1
                self._retry.add(vid)
        return rerouted, unavoidable

    def _retry_reroutes(self) -> None:
        for vid in list(self._retry):
            try:
                if not self._route_blocked(vid) or self._reroute(vid):
                    self._retry.discard(vid)
            except traci.TraCIException:  # left the network
                self._retry.discard(vid)

    def _reroute_all(self) -> int:
        """Re-route every vehicle in the network (EVs too) on the current static weights."""
        n = 0
        v = self.conn.vehicle
        for vid in v.getIDList():
            try:
                before = v.getRoute(vid)
                v.rerouteTraveltime(vid, False)
                n += v.getRoute(vid) != before
            except traci.TraCIException:
                continue
        return n

    def _check_departures(self, departed) -> None:
        """Safety net: a vehicle that departs with a closed edge ahead is re-routed at once."""
        for vid in departed:
            try:
                if self._route_blocked(vid) and not self._reroute(vid):
                    self._retry.add(vid)
            except traci.TraCIException:
                continue

    # --- navigation-app re-routing while closures last ------------------------------
    def _sample_travel_times(self) -> None:
        edge = self.conn.edge
        for eid in self._normal_edges():
            if eid in self.closed:
                continue
            ff = routing.free_flow_time(self.topology, eid)
            sample = min(max(edge.getTraveltime(eid), ff), TT_CAP_FACTOR * ff + 60.0)
            old = self._live_tt.get(eid, ff)
            self._live_tt[eid] = old + TT_SMOOTHING * (sample - old)

    def _navigation_reroute(self) -> None:
        """Probe vehicles on a detour re-route on live travel times; the routing weights are
        set back to free-flow right after, so everyone else keeps the signed detour."""
        sensors = getattr(self.env, "sensors", None)
        if sensors is None or not self._detour_edges:
            return
        v = self.conn.vehicle
        users = []
        for vid in v.getIDList():
            if vid in self.evs or not sensors.is_probe(vid):
                continue
            try:
                route = v.getRoute(vid)
                ahead = route[max(0, v.getRouteIndex(vid)) :]
            except traci.TraCIException:
                continue
            if any(e in self._detour_edges for e in ahead):
                users.append(vid)
        if not users:
            return
        edge = self.conn.edge
        for eid, tt in self._live_tt.items():
            edge.adaptTraveltime(eid, tt)
        for vid in users:
            self._reroute(vid)
        self._set_static_weights()

    def _set_static_weights(self) -> None:
        edge = self.conn.edge
        for eid in self._normal_edges():
            edge.adaptTraveltime(eid, CLOSED_WEIGHT_S if eid in self.closed else routing.free_flow_time(self.topology, eid))
        if not self.closed:
            self._live_tt.clear()

    def _normal_edges(self) -> list[str]:
        if not hasattr(self, "_edge_ids"):
            self._edge_ids = [e.getID() for e in self.topology.net.getEdges()]
        return self._edge_ids

    # --- fake navigation data (security test) -----------------------------------------
    def start_attack(self, junction: str = "J2", approach: str = "N", n: int = 99) -> dict:
        """Phantom probe reports claim `n` stopped cars on one approach (Berlin 2020 style)."""
        if junction not in self.topology.tls_ids:
            raise ValueError(f"unknown junction '{junction}' (expected one of {self.topology.tls_ids})")
        if approach not in self.topology.approach_lanes[junction]:
            raise ValueError(f"junction {junction} has no approach '{approach}' (W, E, N or S)")
        n = int(n)
        if not 1 <= n <= MAX_FAKE_REPORTS:
            raise ValueError(f"n must be between 1 and {MAX_FAKE_REPORTS}")
        current = self.attack
        if current and (current["junction"], current["approach"], current["n"]) == (junction, approach, n):
            return {**current, "started": False, "reason": "already running"}
        if current:
            self._end_attack(replaced=True)
        self.env.sensors.inject_fake_reports(junction, approach, n)
        self.attack = {"junction": junction, "approach": approach, "n": n, "since": self._t()}
        self.env.log_event("attack_started", junction=junction, approach=approach, n=n)
        return {**self.attack, "started": True}

    def stop_attack(self, junction: str | None = None, approach: str | None = None, n: int | None = None) -> dict:
        """Stop the running attack. The parameters are accepted (the twin may send the same
        ones as for start_attack) but there is only ever one attack, so they are ignored."""
        if self.attack is None:
            return {"stopped": False, "reason": "no attack running"}
        ended = self._end_attack()
        return {**ended, "stopped": True}

    def _end_attack(self, replaced: bool = False) -> dict:
        self.env.sensors.clear_fake_reports()
        now = self._t()
        ended = {**self.attack, "type": "attack", "until": now, "duration_s": round(now - self.attack["since"], 1)}
        self.history.append(ended)
        self.attack = None
        self.env.log_event("attack_stopped", **({"replaced": True} if replaced else {}))
        return ended

    # --- summary for analysis ------------------------------------------------------------
    def report(self) -> dict:
        """What happened during the run (JSON-serializable)."""
        now = self._t()
        ongoing = [{**c, "type": "closure", "until": None, "duration_s": round(now - c["since"], 1)} for c in self.closed.values()]
        if self.attack:
            ongoing.append({**self.attack, "type": "attack", "until": None, "duration_s": round(now - self.attack["since"], 1)})
        return {
            "teleports": self.teleports,
            "failed_events": self.failed_events,
            "rerouted": self.rerouted,
            "closures_and_attacks": self.history + ongoing,
            "emergency_vehicles": [{k: v for k, v in ev.items() if k != "live"} for ev in self.evs.values()],
            "ev_preempt_distance_m": config.EV_PREEMPT_DISTANCE_M,
        }
