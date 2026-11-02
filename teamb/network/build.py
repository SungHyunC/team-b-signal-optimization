"""Generate the four-junction corridor with netconvert.

            NN1      NN2      NN3      NN4            y = 450  (cross streets enter/leave)
             |        |        |        |
            N1 ----- N2 ----- N3 ----- N4             y = 250  back street, 30 km/h (detour)
             |        |        |        |
  W0 ====== J1 ===== J2 ===== J3 ===== J4 ====== E5   y = 0    arterial, 2 lanes/dir, 50 km/h
             |        |        |        |
            S1       S2       S3       S4             y = -250
         x = 0      300      600      900

J1–J4 are signalized (Aditya's reference design: junctions every 300 m on a two-way
east–west corridor). N1–N4 are unsignalized priority junctions. Edge ids are
"<from>_<to>", e.g. W0_J1 is the eastbound entry and J4_E5 the eastbound exit.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import quoteattr

from teamb import config
from teamb.sumo_paths import DEVNULL, binary

NETWORK_VERSION = "1"
E2_LENGTH_M = 100.0  # lane-area detector length upstream of each stop line
E1_SETBACK_M = 25.0  # induction loop distance from the stop line


@dataclass(frozen=True)
class NetworkPaths:
    net: Path
    detectors: Path


def _nodes() -> list[tuple[str, float, float, str]]:
    xs = config.JUNCTION_X
    nodes = [("W0", config.ARTERIAL_WEST_X, 0.0, "priority"), ("E5", config.ARTERIAL_EAST_X, 0.0, "priority")]
    for i, j in enumerate(config.JUNCTIONS, start=1):
        x = xs[j]
        nodes += [
            (j, x, 0.0, "traffic_light"),
            (f"N{i}", x, config.BACKSTREET_Y, "priority"),
            (f"NN{i}", x, config.NORTH_EDGE_Y, "priority"),
            (f"S{i}", x, config.SOUTH_EDGE_Y, "priority"),
        ]
    return nodes


def _edges() -> list[tuple[str, str, str, int, float, int]]:
    """(id, from, to, lanes, speed, priority) for every directed edge."""
    chain = ["W0", *config.JUNCTIONS, "E5"]
    edges = []

    def two_way(a, b, lanes, speed, prio):
        edges.append((f"{a}_{b}", a, b, lanes, speed, prio))
        edges.append((f"{b}_{a}", b, a, lanes, speed, prio))

    for a, b in zip(chain, chain[1:]):
        two_way(a, b, config.ARTERIAL_LANES, config.ARTERIAL_SPEED, 3)
    for i, j in enumerate(config.JUNCTIONS, start=1):
        two_way(j, f"S{i}", 1, config.CROSS_SPEED, 2)
        two_way(j, f"N{i}", 1, config.CROSS_SPEED, 2)
        two_way(f"N{i}", f"NN{i}", 1, config.CROSS_SPEED, 2)
    for i in range(1, len(config.JUNCTIONS)):
        two_way(f"N{i}", f"N{i + 1}", 1, config.BACKSTREET_SPEED, 1)
    return edges


def edge_kind(edge_id: str) -> str:
    """'arterial', 'cross' or 'back' (back street)."""
    a, _, b = edge_id.partition("_")
    if a.startswith("N") and b.startswith("N") and not a.startswith("NN") and not b.startswith("NN"):
        return "back"
    arterial_nodes = {"W0", "E5", *config.JUNCTIONS}
    if a in arterial_nodes and b in arterial_nodes:
        return "arterial"
    return "cross"


def _write_plain(out: Path) -> tuple[Path, Path]:
    nod, edg = out / "corridor.nod.xml", out / "corridor.edg.xml"
    nod.write_text(
        "<nodes>\n"
        + "".join(f'  <node id="{n}" x="{x}" y="{y}" type="{t}"/>\n' for n, x, y, t in _nodes())
        + "</nodes>\n"
    )
    edg.write_text(
        "<edges>\n"
        + "".join(
            f'  <edge id="{e}" from="{a}" to="{b}" numLanes="{n}" speed="{s}" priority="{p}"/>\n'
            for e, a, b, n, s, p in _edges()
        )
        + "</edges>\n"
    )
    return nod, edg


def _write_detectors(net_path: Path, out: Path) -> None:
    import sumolib

    net = sumolib.net.readNet(str(net_path))
    lines = ["<additional>"]
    for tls in sorted(t.getID() for t in net.getTrafficLights()):
        for edge in net.getNode(tls).getIncoming():
            for lane in edge.getLanes():
                lid, length = lane.getID(), lane.getLength()
                e2_len = min(E2_LENGTH_M, length - 1.0)
                lines.append(
                    f'  <laneAreaDetector id="e2_{lid}" lane="{lid}" pos="{length - e2_len:.2f}" '
                    f'length="{e2_len:.2f}" freq="60" file={quoteattr(DEVNULL)}/>'
                )
                lines.append(
                    f'  <inductionLoop id="e1_{lid}" lane="{lid}" pos="{max(0.0, length - E1_SETBACK_M):.2f}" '
                    f'freq="60" file={quoteattr(DEVNULL)}/>'
                )
    lines.append("</additional>")
    out.write_text("\n".join(lines) + "\n")


def ensure_network(force: bool = False) -> NetworkPaths:
    """Build the network once (or again when NETWORK_VERSION changes) and return its paths."""
    out = config.GENERATED
    out.mkdir(parents=True, exist_ok=True)
    paths = NetworkPaths(out / "corridor.net.xml", out / "detectors.add.xml")
    stamp = out / "VERSION"
    if not force and paths.net.exists() and paths.detectors.exists() and stamp.exists() and stamp.read_text() == NETWORK_VERSION:
        return paths
    nod, edg = _write_plain(out)
    subprocess.run(
        [
            binary("netconvert"),
            "--node-files", str(nod),
            "--edge-files", str(edg),
            "--output-file", str(paths.net),
            "--no-turnarounds", "true",
            "--offset.disable-normalization", "true",
            "--tls.default-type", "static",
            "--junctions.corner-detail", "5",
            "--no-warnings", "true",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    _write_detectors(paths.net, paths.detectors)
    stamp.write_text(NETWORK_VERSION)
    return paths


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


if __name__ == "__main__":
    p = ensure_network(force=True)
    print(f"network: {p.net}\ndetectors: {p.detectors}")
