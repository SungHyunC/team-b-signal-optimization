"""Spillback: a queue that fills a road back to its entrance AND blocks the junction upstream.

A long queue alone is only a *queue warning* (the old `spillback_samples` count:
queue length >= 90 % of the storage). Real spillback needs evidence that the queue
actually blocks traffic upstream (role document: "actual spillback requires upstream
blocking evidence, not just threshold exceedance"). For every link L that is fed by a
junction (e.g. J1_J2, fed by J1) we check, every 5-s sample:

    1. entrance blocked: some lane of L holds a slow vehicle (< 1 m/s) within
       ENTRANCE_ZONE_M (15 m) of where L starts, and at least MIN_FILL_SHARE (50 %) of that
       lane's storage (length / 7 m) is taken by slow vehicles;
    2. upstream blocked: at the upstream junction, the first vehicle of some lane that
       feeds L is stopped (< 1 m/s) at its stop line (last STOPLINE_ZONE_M = 12 m), its next
       link leads into L, and that link is NOT red or yellow (so it is allowed to go but
       cannot, because L is full).

Both together, in MIN_PERSIST_SAMPLES (2) consecutive samples, confirm spillback on L.
Duration is counted per 5-s sample from the second confirming sample on, inside the
measurement window. One TraCI call (`vehicle.getNextLinks`) is made per stopped feeder
vehicle, and only for links whose entrance is blocked (rare), so the check is cheap.
"""
from __future__ import annotations

from teamb.network.build import edge_kind

ENTRANCE_ZONE_M = 15.0
STOPLINE_ZONE_M = 12.0
SLOW_SPEED = 1.0  # m/s
MIN_FILL_SHARE = 0.5
MIN_PERSIST_SAMPLES = 2
JAM_SPACING_M = 7.0
RED_STATES = frozenset("ryu")  # SUMO link states: red, yellow, red-yellow


def lane_edge(lane_id: str) -> str:
    return lane_id.rsplit("_", 1)[0]


def entrance_blocked(lane_vehicles: list[tuple[str, float]], positions: dict, length: float) -> bool:
    """lane_vehicles: [(vehicle id, speed)]; positions: vehicle id -> (lane position, ...)."""
    slow = [vid for vid, speed in lane_vehicles if speed < SLOW_SPEED and vid in positions]
    if len(slow) * JAM_SPACING_M < MIN_FILL_SHARE * length:
        return False
    return any(positions[vid][0] <= ENTRANCE_ZONE_M for vid in slow)


def stopped_front_vehicle(lane_vehicles: list[tuple[str, float]], positions: dict, length: float) -> str | None:
    """Id of the vehicle closest to the stop line if it is stopped at the stop line, else None."""
    best, best_pos, best_speed = None, -1.0, 0.0
    for vid, speed in lane_vehicles:
        p = positions.get(vid)
        if p is not None and p[0] > best_pos:
            best, best_pos, best_speed = vid, p[0], speed
    if best is None or best_speed >= SLOW_SPEED or best_pos < length - STOPLINE_ZONE_M:
        return None
    return best


class SpillbackMonitor:
    def __init__(self, topology):
        net = topology.net
        self.links: dict[str, dict] = {}
        for edge in net.getEdges():
            feeders = sorted({inc.getID() for lane in edge.getLanes() for inc in lane.getIncoming()})
            if not feeders:  # network entry: a full entry road shows up as insertion backlog instead
                continue
            self.links[edge.getID()] = {
                "lanes": [(lane.getID(), lane.getLength()) for lane in edge.getLanes()],
                "feeders": [(f, net.getLane(f).getLength()) for f in feeders],
                "kind": edge_kind(edge.getID()),
                "from": edge.getFromNode().getID(),
            }
        self.streak = {e: 0 for e in self.links}
        self.seconds = {e: 0.0 for e in self.links}
        self.episodes = {e: 0 for e in self.links}
        self.network_seconds = 0.0
        self.active: list[str] = []

    def is_spillback(self, edge: str, by_lane: dict, positions: dict, next_link) -> bool:
        info = self.links[edge]
        if not any(entrance_blocked(by_lane.get(lane, ()), positions, length) for lane, length in info["lanes"]):
            return False
        for feeder, length in info["feeders"]:
            vid = stopped_front_vehicle(by_lane.get(feeder, ()), positions, length)
            if vid is None:
                continue
            link = next_link(vid)  # (next lane id, link state) or None
            if link and lane_edge(link[0]) == edge and link[1] not in RED_STATES:
                return True
        return False

    def check(self, by_lane: dict, positions: dict, next_link, dt: float, count: bool) -> list[str]:
        """One sample; returns the links in confirmed spillback. `count`: inside the measurement window."""
        active = []
        for edge in self.links:
            if self.is_spillback(edge, by_lane, positions, next_link):
                self.streak[edge] += 1
            else:
                self.streak[edge] = 0
            if self.streak[edge] >= MIN_PERSIST_SAMPLES:
                active.append(edge)
                if count:
                    self.seconds[edge] += dt
                    if self.streak[edge] == MIN_PERSIST_SAMPLES:
                        self.episodes[edge] += 1
        if active and count:
            self.network_seconds += dt
        self.active = active
        return active

    def summary(self) -> dict:
        by_link = {e: round(s, 1) for e, s in self.seconds.items() if s > 0}
        return {
            "spillback_duration_s": round(self.network_seconds, 1),
            "spillback_link_s": round(sum(self.seconds.values()), 1),
            "spillback_events": sum(self.episodes.values()),
            "spillback_by_link": by_link,
        }
