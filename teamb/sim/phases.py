"""Signal states and how they turn into SUMO state strings.

Each junction cycles through six signal states. Controllers only ever ask for a green
axis ("EW" or "NS"); the safety supervisor inserts yellow and all-red in between.

    EW_G → EW_Y → EW_AR → NS_G → NS_Y → NS_AR → EW_G ...

Left turns get a permissive green ('g': go, but yield to oncoming traffic). U-turns
stay red. A state string is built per junction from the link list in Topology, so the
order of characters always matches the generated network.
"""
from __future__ import annotations

from collections.abc import Iterable

SIGNALS = ("EW_G", "EW_Y", "EW_AR", "NS_G", "NS_Y", "NS_AR")
NEXT_SIGNAL = {"EW_G": "EW_Y", "EW_Y": "EW_AR", "EW_AR": "NS_G", "NS_G": "NS_Y", "NS_Y": "NS_AR", "NS_AR": "EW_G"}
AXES = ("EW", "NS")


def axis_of(signal: str) -> str:
    return signal[:2]


def other_axis(axis: str) -> str:
    return "NS" if axis == "EW" else "EW"


def green_signal(axis: str) -> str:
    return f"{axis}_G"


def link_char(link, signal: str) -> str:
    if link.direction in ("t", "T"):
        return "r"
    axis, part = signal[:2], signal[3:]
    if link.axis != axis:
        return "r"
    if part == "G":
        return "g" if link.direction in ("l", "L") else "G"
    if part == "Y":
        return "y"
    return "r"


def build_state(links: Iterable, n_links: int, signal: str) -> str:
    chars = ["r"] * n_links
    for link in links:
        chars[link.index] = link_char(link, signal)
    return "".join(chars)


def approach_colors(signal: str) -> dict[str, str]:
    """Color shown to each approach: 'G', 'Y' or 'R' (left turns are permissive during G)."""
    axis, part = signal[:2], signal[3:]
    color = {"G": "G", "Y": "Y", "AR": "R"}[part]
    on = ("W", "E") if axis == "EW" else ("N", "S")
    return {a: (color if a in on else "R") for a in ("W", "E", "N", "S")}


def is_conflict_free(links: Iterable, state: str) -> bool:
    """SIG-01: never green (or yellow) on both axes at once."""
    active = {link.axis for link in links if state[link.index] in "Ggy"}
    return len(active) <= 1
