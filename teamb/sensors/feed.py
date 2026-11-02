"""The traffic feed: one shared set of TraCI subscriptions per SUMO connection.

Why this exists
---------------
Every TraCI getter (``conn.vehicle.getSpeed(...)``) is a round trip to the SUMO process
(about 30-70 microseconds). The first sensor version made ~400 of them per simulated
second, which made ``observe()`` about 25x slower than SUMO itself. A *subscription*
asks SUMO to push the values together with every ``simulationStep``; reading them is
then a dictionary lookup.

What is subscribed
------------------
every step (cheap)
    * all vehicles: lane id and speed (one *context subscription* around a junction
      with a radius that covers the whole network),
    * every E2 lane-area detector: halting number, vehicle number, occupancy, mean speed,
    * every E1 induction loop: seconds since the last detection, vehicles on the loop,
    * lane 0 of every edge: disallowed vehicle classes (a closed road disallows all),
    * the simulation: number of vehicles that started teleporting.
on request, at most once per step (``snapshot_at``)
    * all vehicles: position on the lane (m) and SUMO time loss (s). Taken by a one-shot
      context subscription (subscribe, read, unsubscribe = 2 round trips). The metrics
      ask for it every 5 s.

Who uses it
-----------
``SensorSuite`` (observations for controllers) and ``MetricsCollector`` (evaluation).
Ground truth read here is used for evaluation and for simulating what a probe phone
would report about itself. It never reaches a controller, except in the explicitly
labeled ``oracle`` benchmark.

The feed is attached to the connection object (``conn._teamb_feed``) so the sensors
and the metrics share it without any change to ``SimEnv``. The SensorSuite registers
itself as ``feed.sensors`` so the metrics can read its logs at the end of the run.
"""
from __future__ import annotations

import math

import traci.constants as tc

from teamb.network.build import edge_kind

HALT_SPEED = 0.1  # m/s. SUMO's own threshold for "halting" on lanes (getLastStepHaltingNumber)

E2_VARS = (
    tc.LAST_STEP_VEHICLE_HALTING_NUMBER,
    tc.LAST_STEP_VEHICLE_NUMBER,
    tc.LAST_STEP_OCCUPANCY,
    tc.LAST_STEP_MEAN_SPEED,
)
E1_VARS = (tc.LAST_STEP_TIME_SINCE_DETECTION, tc.LAST_STEP_VEHICLE_ID_LIST)
STEP_VEHICLE_VARS = (tc.VAR_LANE_ID, tc.VAR_SPEED)
SNAPSHOT_VEHICLE_VARS = (tc.VAR_LANEPOSITION, tc.VAR_TIMELOSS)
SIM_VARS = (tc.VAR_TELEPORT_STARTING_VEHICLES_NUMBER,)

# Direct getters used when a subscription value is missing (for example because some
# other code re-subscribed the same object with different variables).
_E2_GETTERS = {
    tc.LAST_STEP_VEHICLE_HALTING_NUMBER: "getLastStepHaltingNumber",
    tc.LAST_STEP_VEHICLE_NUMBER: "getLastStepVehicleNumber",
    tc.LAST_STEP_OCCUPANCY: "getLastStepOccupancy",
    tc.LAST_STEP_MEAN_SPEED: "getLastStepMeanSpeed",
}
_E1_GETTERS = {
    tc.LAST_STEP_TIME_SINCE_DETECTION: "getTimeSinceDetection",
    tc.LAST_STEP_VEHICLE_ID_LIST: "getLastStepVehicleIDs",
}


def lane_edge(lane_id: str) -> str:
    """'J1_J2_0' -> 'J1_J2' (SUMO lane ids are '<edge id>_<lane index>')."""
    return lane_id.rsplit("_", 1)[0]


def origin_group(edge_id: str) -> str:
    """Which driver population a trip belongs to, by the edge it starts on.

    'arterial' = enters on the main road (W0_J1, E5_J4); 'cross' = everything else
    (cross streets and the back street)."""
    return "arterial" if edge_kind(edge_id) == "arterial" else "cross"


def get_feed(conn, topology) -> "TrafficFeed":
    """The feed for this connection; created (and subscribed) on first use."""
    feed = getattr(conn, "_teamb_feed", None)
    if feed is None:
        feed = TrafficFeed(conn, topology)
        try:
            conn._teamb_feed = feed
        except AttributeError:  # an exotic connection object; each caller then gets its own feed
            pass
    return feed


def _radius_covering(net, x0: float, y0: float) -> float:
    xmin, ymin, xmax, ymax = net.getBoundary()
    corners = [(xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)]
    return max(math.hypot(x - x0, y - y0) for x, y in corners) + 50.0


class TrafficFeed:
    def __init__(self, conn, topology):
        self.conn = conn
        self.topo = topology
        self.sensors = None  # the SensorSuite registers itself here
        self.events: list[dict] = []  # road_closed / road_reopened (seen here), attack_* (logged by sensors)
        self.t: float | None = None
        self.vehicles: dict[str, tuple[str, float]] = {}  # vehicle id -> (lane id, speed m/s)
        self.by_lane: dict[str, list[tuple[str, float]]] = {}  # lane id -> [(vehicle id, speed)]
        self.teleports_started = 0  # in the last step
        self.snapshot_t: float | None = None
        self.snapshot: dict[str, tuple[float, float]] = {}  # vehicle id -> (lane position m, time loss s)
        self._e2: dict = {}
        self._e1: dict = {}
        self._closed: set[str] = set()

        net = topology.net
        nodes = [n.getID() for n in net.getNodes()]
        self._ego = topology.tls_ids[0] if topology.tls_ids else nodes[0]
        self._snap_ego = next(n for n in nodes if n != self._ego)  # must differ from the step ego
        self._radius = _radius_covering(net, *net.getNode(self._ego).getCoord())
        self._snap_radius = _radius_covering(net, *net.getNode(self._snap_ego).getCoord())
        self.detector_lanes = sorted({l for j in topology.tls_ids for ls in topology.approach_lanes[j].values() for l in ls})
        self._closure_lanes = {e.getLanes()[0].getID(): e.getID() for e in net.getEdges()}
        self._subscribe()

    # --- set-up -----------------------------------------------------------------
    def _subscribe(self) -> None:
        c = self.conn
        c.junction.subscribeContext(self._ego, tc.CMD_GET_VEHICLE_VARIABLE, self._radius, list(STEP_VEHICLE_VARS))
        for lane in self.detector_lanes:
            c.lanearea.subscribe(f"e2_{lane}", list(E2_VARS))
            c.inductionloop.subscribe(f"e1_{lane}", list(E1_VARS))
        for lane in self._closure_lanes:
            c.lane.subscribe(lane, [tc.LANE_DISALLOWED])
        c.simulation.subscribe(list(SIM_VARS))

    # --- every step -------------------------------------------------------------
    def update(self, t: float) -> None:
        """Index this step's subscription results. Cheap; repeated calls for the same t are free."""
        if t == self.t:
            return
        self.t = t
        c = self.conn
        ctx = c.junction.getContextSubscriptionResults(self._ego) or {}
        vehicles: dict[str, tuple[str, float]] = {}
        by_lane: dict[str, list[tuple[str, float]]] = {}
        lane_var, speed_var = tc.VAR_LANE_ID, tc.VAR_SPEED
        for vid, r in ctx.items():
            lane, speed = r[lane_var], r[speed_var]
            vehicles[vid] = (lane, speed)
            by_lane.setdefault(lane, []).append((vid, speed))
        self.vehicles, self.by_lane = vehicles, by_lane
        self._e2 = c.lanearea.getAllSubscriptionResults()
        self._e1 = c.inductionloop.getAllSubscriptionResults()
        sim = c.simulation.getSubscriptionResults() or {}
        n = sim.get(tc.VAR_TELEPORT_STARTING_VEHICLES_NUMBER)
        self.teleports_started = int(n) if n is not None else c.simulation.getStartingTeleportNumber()
        self._detect_closures(t, c.lane.getAllSubscriptionResults())

    def _detect_closures(self, t: float, lanes: dict) -> None:
        for lane, edge in self._closure_lanes.items():
            disallowed = (lanes.get(lane) or {}).get(tc.LANE_DISALLOWED, ())
            closed = "passenger" in disallowed
            if closed and edge not in self._closed:
                self._closed.add(edge)
                self.events.append({"t": t, "type": "road_closed", "edge": edge})
            elif not closed and edge in self._closed:
                self._closed.discard(edge)
                self.events.append({"t": t, "type": "road_reopened", "edge": edge})

    def on_lane(self, lane: str) -> list[tuple[str, float]]:
        """[(vehicle id, speed)] on a lane this step, ordered as SUMO reports them."""
        return self.by_lane.get(lane, ())

    def e2(self, lane: str, var: int) -> float:
        """Value of an E2 lane-area detector variable for the detector on `lane`."""
        det = f"e2_{lane}"
        value = (self._e2.get(det) or {}).get(var)
        if value is None:
            value = getattr(self.conn.lanearea, _E2_GETTERS[var])(det)
        return value

    def e1(self, lane: str, var: int):
        """Value of an E1 induction-loop variable for the loop on `lane`."""
        det = f"e1_{lane}"
        value = (self._e1.get(det) or {}).get(var)
        if value is None:
            value = getattr(self.conn.inductionloop, _E1_GETTERS[var])(det)
        return value

    def origin_group(self, vid: str) -> str:
        """Driver population of a vehicle that just departed (see `origin_group`)."""
        lane = self.vehicles.get(vid, (None, 0.0))[0]
        edge = lane_edge(lane) if lane else self.conn.vehicle.getRoadID(vid)
        return origin_group(edge)

    # --- on request ---------------------------------------------------------------
    def snapshot_at(self, t: float) -> dict[str, tuple[float, float]]:
        """{vehicle id: (lane position m, time loss s)} for all vehicles at time t (cached per t)."""
        if self.snapshot_t == t:
            return self.snapshot
        c = self.conn
        c.junction.subscribeContext(self._snap_ego, tc.CMD_GET_VEHICLE_VARIABLE, self._snap_radius, list(SNAPSHOT_VEHICLE_VARS))
        res = c.junction.getContextSubscriptionResults(self._snap_ego) or {}
        pos_var, tl_var = tc.VAR_LANEPOSITION, tc.VAR_TIMELOSS
        self.snapshot = {vid: (r[pos_var], r[tl_var]) for vid, r in res.items()}
        c.junction.unsubscribeContext(self._snap_ego, tc.CMD_GET_VEHICLE_VARIABLE, self._snap_radius)
        self.snapshot_t = t
        return self.snapshot

    def closed_edges(self) -> set[str]:
        return set(self._closed)
