"""Read the generated network and describe it for controllers, sensors and the twin.

Signal link indices are always read from the generated network (Aditya's rule: never
hard-code the signal state order).

Conventions shared with the twin:
- Coordinates are SUMO meters (x east, y north).
- Headings/angles use SUMO's navigational convention: 0° = north, 90° = east, clockwise.
- An approach is the side a vehicle comes FROM: "W", "E", "N" or "S".
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from functools import lru_cache

import sumolib

from teamb.network.build import edge_kind, ensure_network

APPROACHES = ("W", "E", "N", "S")


def axis_of(approach: str) -> str:
    return "EW" if approach in ("W", "E") else "NS"


@dataclass(frozen=True)
class Link:
    index: int
    from_lane: str
    to_lane: str
    from_edge: str
    to_edge: str
    approach: str  # W/E/N/S — side the movement comes from
    direction: str  # SUMO direction: s (straight), l, r, t, L, R
    axis: str  # EW / NS


def _side(origin: tuple[float, float], other: tuple[float, float]) -> str:
    dx, dy = other[0] - origin[0], other[1] - origin[1]
    if abs(dx) >= abs(dy):
        return "W" if dx < 0 else "E"
    return "S" if dy < 0 else "N"


def _heading(p0, p1) -> float:
    return math.degrees(math.atan2(p1[0] - p0[0], p1[1] - p0[1])) % 360.0


class Topology:
    def __init__(self, net_path):
        self.net = sumolib.net.readNet(str(net_path))
        self.tls_ids: list[str] = sorted(t.getID() for t in self.net.getTrafficLights())
        self.links: dict[str, list[Link]] = {}
        self.n_links: dict[str, int] = {}
        self.link_axis: dict[str, dict[int, str]] = {}
        self.approach_edges: dict[str, dict[str, str]] = {}
        self.approach_lanes: dict[str, dict[str, list[str]]] = {}
        self.exit_edges: dict[str, dict[str, str]] = {}
        self.exit_lanes: dict[str, dict[str, list[str]]] = {}
        for tls in self.net.getTrafficLights():
            self._read_tls(tls)

    def _read_tls(self, tls) -> None:
        j = tls.getID()
        node = self.net.getNode(j)
        here = node.getCoord()
        self.approach_edges[j], self.approach_lanes[j] = {}, {}
        for edge in node.getIncoming():
            side = _side(here, edge.getFromNode().getCoord())
            self.approach_edges[j][side] = edge.getID()
            self.approach_lanes[j][side] = [lane.getID() for lane in edge.getLanes()]
        self.exit_edges[j], self.exit_lanes[j] = {}, {}
        for edge in node.getOutgoing():
            side = _side(here, edge.getToNode().getCoord())
            self.exit_edges[j][side] = edge.getID()
            self.exit_lanes[j][side] = [lane.getID() for lane in edge.getLanes()]

        links = []
        for in_lane, out_lane, index in tls.getConnections():
            direction = "s"
            for c in in_lane.getOutgoing():
                if c.getToLane() is out_lane or c.getToLane().getID() == out_lane.getID():
                    direction = c.getDirection()
                    break
            approach = _side(here, in_lane.getEdge().getFromNode().getCoord())
            links.append(
                Link(
                    index=index,
                    from_lane=in_lane.getID(),
                    to_lane=out_lane.getID(),
                    from_edge=in_lane.getEdge().getID(),
                    to_edge=out_lane.getEdge().getID(),
                    approach=approach,
                    direction=direction,
                    axis=axis_of(approach),
                )
            )
        links.sort(key=lambda l: l.index)
        self.links[j] = links
        self.n_links[j] = max(l.index for l in links) + 1
        self.link_axis[j] = {l.index: l.axis for l in links}

    # --- helpers --------------------------------------------------------
    def lane_length(self, lane_id: str) -> float:
        return self.net.getLane(lane_id).getLength()

    def edge_lanes(self, edge_id: str) -> list[str]:
        return [lane.getID() for lane in self.net.getEdge(edge_id).getLanes()]

    def shortest_path(self, from_edge: str, to_edge: str) -> list[str]:
        path, _ = self.net.getShortestPath(self.net.getEdge(from_edge), self.net.getEdge(to_edge))
        if not path:
            raise ValueError(f"no route from {from_edge} to {to_edge}")
        return [e.getID() for e in path]

    def downstream_junction(self, edge_id: str) -> str | None:
        to = self.net.getEdge(edge_id).getToNode().getID()
        return to if to in self.tls_ids else None

    # --- geometry for the digital twin -----------------------------------
    def geometry(self) -> dict:
        lanes, edges = [], []
        for edge in self.net.getEdges():
            kind = edge_kind(edge.getID())
            edges.append(
                {
                    "id": edge.getID(),
                    "from": edge.getFromNode().getID(),
                    "to": edge.getToNode().getID(),
                    "kind": kind,
                    "lanes": [lane.getID() for lane in edge.getLanes()],
                }
            )
            for lane in edge.getLanes():
                lanes.append(
                    {
                        "id": lane.getID(),
                        "edge": edge.getID(),
                        "index": lane.getIndex(),
                        "kind": kind,
                        "width": lane.getWidth(),
                        "speed": lane.getSpeed(),
                        "length": round(lane.getLength(), 2),
                        "shape": [[round(x, 2), round(y, 2)] for x, y in lane.getShape()],
                    }
                )
        junctions = []
        for node in self.net.getNodes():
            x, y = node.getCoord()
            junctions.append(
                {
                    "id": node.getID(),
                    "x": x,
                    "y": y,
                    "type": node.getType(),
                    "signalized": node.getID() in self.tls_ids,
                    "shape": [[round(px, 2), round(py, 2)] for px, py in node.getShape()],
                }
            )
        tls = {}
        for j in self.tls_ids:
            x, y = self.net.getNode(j).getCoord()
            approaches = {}
            for side, lane_ids in self.approach_lanes[j].items():
                shapes = [self.net.getLane(l).getShape() for l in lane_ids]
                ends = [s[-1] for s in shapes]
                stop = [sum(p[0] for p in ends) / len(ends), sum(p[1] for p in ends) / len(ends)]
                approaches[side] = {
                    "edge": self.approach_edges[j][side],
                    "lanes": lane_ids,
                    "axis": axis_of(side),
                    "stop": [round(stop[0], 2), round(stop[1], 2)],
                    "heading": round(_heading(shapes[0][-2], shapes[0][-1]), 1),
                }
            tls[j] = {
                "x": x,
                "y": y,
                "approaches": approaches,
                "exits": self.exit_edges[j],
                "links": [asdict(l) for l in self.links[j]],
            }
        xmin, ymin, xmax, ymax = self.net.getBoundary()
        return {"bounds": [xmin, ymin, xmax, ymax], "lanes": lanes, "edges": edges, "junctions": junctions, "tls": tls}


@lru_cache(maxsize=1)
def load_topology() -> Topology:
    return Topology(ensure_network().net)
