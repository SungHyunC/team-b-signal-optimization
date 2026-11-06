"""Origin–destination demand for the four-junction corridor, by named movement.

Owner: Scenarios & analysis (Aditya).

    NN1..NN4 (north entries/exits)      the arterial: W0 → J1 … J4 → E5 (eastbound) and back
       |                                 cross streets: NN{i} ↔ N{i} ↔ J{i} ↔ S{i}
  W0 = J1 = J2 = J3 = J4 = E5
       |
    S1..S4 (south entries/exits)

All rates are veh/h at a profile multiplier of 1.0 (the peak). Movements are named by the
direction of travel when the vehicle reaches the junction, e.g. "NB right at J2" is a
northbound car from S2 turning right (east) onto the arterial.

Left turns from the arterial are left out by default: the network has no left-turn bays and
the two-phase signal only gives them a permissive green, so a waiting left-turner would block
a through lane (a network limitation, see docs/scenarios.md). Cross-street left turns face
light opposing traffic and are included.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from teamb import config
from teamb.demand.profiles import Profile
from teamb.demand.routes import Flow

JunctionValues = dict[str, float]


def _per_junction(value: float | JunctionValues, j: str) -> float:
    return float(value.get(j, 0.0)) if isinstance(value, dict) else float(value)


@dataclass
class CorridorDemand:
    eb_through: float = 1150.0  # W0 → E5
    wb_through: float = 550.0  # E5 → W0
    cross_through: float | JunctionValues = 130.0  # per direction (NB and SB) at each junction
    eb_right: float | JunctionValues = 35.0  # W → S at J{i}
    wb_right: float | JunctionValues = 25.0  # E → N at J{i}
    nb_right: float | JunctionValues = 40.0  # S → E (joins eastbound)
    sb_right: float | JunctionValues = 30.0  # N → W (joins westbound)
    nb_left: float | JunctionValues = 15.0  # S → W (joins westbound), permissive
    sb_left: float | JunctionValues = 20.0  # N → E (joins eastbound), permissive
    eb_left: float | JunctionValues = 0.0  # W → N, permissive across eastbound-opposing traffic
    wb_left: float | JunctionValues = 0.0  # E → S
    truck_share: float = 0.0  # share of trucks in the arterial through flows
    bus_per_hour: float = 0.0  # buses each way along the whole arterial
    junctions: tuple[str, ...] = field(default=config.JUNCTIONS)  # cross streets to load (a subset is fine)

    def flows(self, profile: Profile | None = None, *, begin: float = 0.0, end: float | None = None) -> list[Flow]:
        """All flows, sharing one time-of-day profile."""

        def flow(origin, destination, rate, name, **kw):
            return Flow(origin, destination, rate, begin=begin, end=end, name=name, profile=profile, **kw)

        mix = {"car": 1.0 - self.truck_share, "truck": self.truck_share} if self.truck_share > 0 else None
        out = [
            flow("W0_J1", "J4_E5", self.eb_through, "EB through", mix=mix),
            flow("E5_J4", "J1_W0", self.wb_through, "WB through", mix=mix),
        ]
        if self.bus_per_hour > 0:
            out += [
                flow("W0_J1", "J4_E5", self.bus_per_hour, "EB bus", vtype="bus"),
                flow("E5_J4", "J1_W0", self.bus_per_hour, "WB bus", vtype="bus"),
            ]
        unknown = [j for j in self.junctions if j not in config.JUNCTIONS]
        if unknown:
            raise ValueError(f"unknown junctions {unknown} (the network has {config.JUNCTIONS})")
        for j in self.junctions:
            # cross-street nodes are numbered by the junction's place in the network (build.py),
            # not by its place in self.junctions, so a subset such as ('J2', 'J4') stays right
            i = config.JUNCTIONS.index(j) + 1
            north_in, north_out = f"NN{i}_N{i}", f"N{i}_NN{i}"
            south_in, south_out = f"S{i}_{j}", f"{j}_S{i}"
            movements = [
                (north_in, south_out, self.cross_through, f"SB through at {j}"),
                (south_in, north_out, self.cross_through, f"NB through at {j}"),
                ("W0_J1", south_out, self.eb_right, f"EB right at {j}"),
                ("E5_J4", north_out, self.wb_right, f"WB right at {j}"),
                (south_in, "J4_E5", self.nb_right, f"NB right at {j}"),
                (north_in, "J1_W0", self.sb_right, f"SB right at {j}"),
                (south_in, "J1_W0", self.nb_left, f"NB left at {j}"),
                (north_in, "J4_E5", self.sb_left, f"SB left at {j}"),
                ("W0_J1", north_out, self.eb_left, f"EB left at {j}"),
                ("E5_J4", south_out, self.wb_left, f"WB left at {j}"),
            ]
            for origin, destination, value, name in movements:
                rate = _per_junction(value, j)
                if rate > 0:
                    out.append(flow(origin, destination, rate, name))
        return out

    def scaled(self, factor: float) -> "CorridorDemand":
        """Every movement times `factor` (bus service unchanged)."""

        def s(v):
            return {k: x * factor for k, x in v.items()} if isinstance(v, dict) else v * factor

        return CorridorDemand(
            eb_through=self.eb_through * factor,
            wb_through=self.wb_through * factor,
            cross_through=s(self.cross_through),
            eb_right=s(self.eb_right),
            wb_right=s(self.wb_right),
            nb_right=s(self.nb_right),
            sb_right=s(self.sb_right),
            nb_left=s(self.nb_left),
            sb_left=s(self.sb_left),
            eb_left=s(self.eb_left),
            wb_left=s(self.wb_left),
            truck_share=self.truck_share,
            bus_per_hour=self.bus_per_hour,
            junctions=self.junctions,
        )


def approach_volumes(flows: list[Flow], topology, t: float, duration: float | None = None) -> dict[str, dict[str, float]]:
    """Demand (veh/h) arriving at each signalized approach at time t, from the static
    shortest paths — a quick capacity check (volume / capacity) without running SUMO."""
    volumes = {j: {side: 0.0 for side in topology.approach_edges[j]} for j in topology.tls_ids}
    side_of = {edge: (j, side) for j, sides in topology.approach_edges.items() for side, edge in sides.items()}
    net = topology.net
    for f in flows:
        rate = f.rate_at(t, duration)
        if rate <= 0:
            continue
        path, _ = net.getFastestPath(net.getEdge(f.origin), net.getEdge(f.destination))  # like SUMO's router
        for edge in path or []:
            if edge.getID() in side_of:
                j, side = side_of[edge.getID()]
                volumes[j][side] += rate
    return volumes
