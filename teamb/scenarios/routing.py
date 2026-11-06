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
    Entry/exit edges are excluded — closing them would strand trips with no alternative.
    Being inner is necessary but not enough: see `closure_error`."""
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


def _reachable(topology, origin: str, avoid: set[str]) -> set[str]:
    """Every normal edge a vehicle on `origin` can drive onto without using `avoid`."""
    net = topology.net
    seen = {origin}
    stack = [net.getEdge(origin)]
    while stack:
        for nxt in stack.pop().getOutgoing():
            nid = nxt.getID()
            if nid in seen or nid in avoid or nxt.getFunction() == "internal":
                continue
            seen.add(nid)
            stack.append(nxt)
    return seen


def stranded_pairs(topology, od_pairs: Iterable[tuple[str, str]], closed: Iterable[str]) -> list[tuple[str, str]]:
    """The origin–destination pairs (deduplicated, in input order) that have no route once
    the `closed` edges are closed: a closed origin or destination, or a set of closures
    that cuts the destination off. SUMO quits when it has to insert such a trip ("not
    allowed to depart" / "has no valid route"), so every closure is checked with this
    first. Pairs naming an unknown edge are skipped (Scenario.validate reports those).
    Same connectivity as `fastest_route` (one search per distinct origin)."""
    closed = set(closed)
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    reach: dict[str, set[str]] = {}
    for origin, destination in od_pairs:
        pair = (origin, destination)
        if pair in seen or not (has_edge(topology, origin) and has_edge(topology, destination)):
            continue
        seen.add(pair)
        if origin in closed or destination in closed:
            out.append(pair)
            continue
        if origin not in reach:
            reach[origin] = _reachable(topology, origin, closed)
        if destination not in reach[origin]:
            out.append(pair)
    return out


def closure_error(
    topology,
    edges: Iterable[str],
    closed: Iterable[str] = (),
    od_pairs: Iterable[tuple[str, str]] = (),
    labels: dict[tuple[str, str], str] | None = None,
) -> str | None:
    """Why closing `edges` (on top of the already `closed` ones) is refused, or None if it
    is safe. One check shared by the scenario runtime (scheduled events and twin commands)
    and Scenario.validate:

    - every edge must exist and be an inner edge (entry/exit edges are where trips start
      and end), and
    - no origin–destination pair in `od_pairs` (the scenario's trips, plus waiting
      emergency vehicles) may lose its last route. Pairs that were already cut off by the
      earlier closures do not count against this closure.
    `labels` maps a pair to a readable name (the flow name) for the message."""
    edges = list(edges)
    for edge in edges:
        if not has_edge(topology, edge):
            return f"unknown edge '{edge}'"
        if not is_inner_edge(topology, edge):
            return f"edge '{edge}' is an entry/exit edge; close an inner segment (J*/N* to J*/N*) instead"
    pairs = list(od_pairs)
    closed = set(closed)
    before = set(stranded_pairs(topology, pairs, closed))
    new = [p for p in stranded_pairs(topology, pairs, closed | set(edges)) if p not in before]
    if not new:
        return None
    origin, destination = new[0]
    name = (labels or {}).get(new[0])
    what = f"flow '{name}' ({origin}→{destination})" if name else f"trips {origin}→{destination}"
    more = f" and {len(new) - 1} more origin–destination pair(s)" if len(new) > 1 else ""
    return f"closing {' + '.join(edges)} would leave {what}{more} with no route"


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
