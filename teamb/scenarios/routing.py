"""Static routing helpers on the generated network (pure Python, no TraCI).

Owner: Scenarios & analysis (Aditya). Used by the scenario runtime (to describe closures)
and by the signal-data API (to suggest detours), so they never touch the live SUMO
connection and are safe to call from a web request thread.
"""
from __future__ import annotations

import heapq
from collections.abc import Iterable

from teamb.network.build import edge_kind


def _is_boundary_node(node_id: str) -> bool:
    """W0, E5, NN1–NN4 and S1–S4: where vehicles enter or leave the network."""
    return node_id in ("W0", "E5") or node_id.startswith("NN") or (node_id.startswith("S") and node_id[1:].isdigit())


def is_inner_edge(topology, edge_id: str) -> bool:
    """True for edges between two inner nodes (J*, N*): the ones a closure may block.
    Entry/exit edges are excluded — closing them would strand trips with no alternative."""
    edge = topology.net.getEdge(edge_id)
    return not (_is_boundary_node(edge.getFromNode().getID()) or _is_boundary_node(edge.getToNode().getID()))


def has_edge(topology, edge_id: str) -> bool:
    try:
        topology.net.getEdge(edge_id)
        return True
    except KeyError:
        return False


def reverse_edge(edge_id: str) -> str:
    a, _, b = edge_id.partition("_")
    return f"{b}_{a}"


def free_flow_time(topology, edge_id: str) -> float:
    edge = topology.net.getEdge(edge_id)
    return edge.getLength() / max(0.1, edge.getSpeed())


def heading_label(topology, edge_id: str) -> str:
    """'EB', 'WB', 'NB' or 'SB' from the edge's geometry."""
    edge = topology.net.getEdge(edge_id)
    (x0, y0), (x1, y1) = edge.getFromNode().getCoord(), edge.getToNode().getCoord()
    if abs(x1 - x0) >= abs(y1 - y0):
        return "EB" if x1 > x0 else "WB"
    return "NB" if y1 > y0 else "SB"


def describe_edge(topology, edge_id: str) -> dict:
    edge = topology.net.getEdge(edge_id)
    a, b = edge.getFromNode().getID(), edge.getToNode().getID()
    return {
        "edge": edge_id,
        "from_node": a,
        "to_node": b,
        "kind": edge_kind(edge_id),
        "direction": heading_label(topology, edge_id),
        "lanes": edge.getLaneNumber(),
        "length_m": round(edge.getLength(), 1),
        "speed_limit_mps": round(edge.getSpeed(), 2),
        "label": f"{a}→{b} {heading_label(topology, edge_id)}",
    }


def fastest_route(topology, origin: str, destination: str, avoid: Iterable[str] = ()) -> list[str] | None:
    """Free-flow fastest edge sequence origin → destination that avoids the given edges
    (Dijkstra over edges, respecting the network's connections). None if there is none."""
    net = topology.net
    avoid = set(avoid)
    if origin in avoid or destination in avoid:
        return None
    start = net.getEdge(origin)
    best = {origin: free_flow_time(topology, origin)}
    prev: dict[str, str] = {}
    queue = [(best[origin], origin)]
    while queue:
        cost, eid = heapq.heappop(queue)
        if eid == destination:
            path = [eid]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return path[::-1]
        if cost > best.get(eid, float("inf")):
            continue
        edge = start if eid == origin else net.getEdge(eid)
        for nxt in edge.getOutgoing():
            nid = nxt.getID()
            if nid in avoid or nxt.getFunction() == "internal":
                continue
            c = cost + nxt.getLength() / max(0.1, nxt.getSpeed())
            if c < best.get(nid, float("inf")):
                best[nid], prev[nid] = c, eid
                heapq.heappush(queue, (c, nid))
    return None


def detour(topology, edge_id: str, closed: Iterable[str] = ()) -> list[str] | None:
    """Fastest way around a closed edge: from its start node to its end node, without using
    it or any other closed edge. Returned as the list of edges to drive instead."""
    net = topology.net
    edge = net.getEdge(edge_id)
    avoid = set(closed) | {edge_id}
    start, end = edge.getFromNode(), edge.getToNode()
    best_path, best_cost = None, float("inf")
    for first in start.getOutgoing():
        if first.getID() in avoid:
            continue
        for last in end.getIncoming():
            if last.getID() in avoid:
                continue
            path = fastest_route(topology, first.getID(), last.getID(), avoid)
            if path:
                cost = sum(free_flow_time(topology, e) for e in path)
                if cost < best_cost:
                    best_path, best_cost = path, cost
    return best_path
