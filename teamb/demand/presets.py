"""Demand presets shared by the scenario catalog (tuned values; see docs/scenarios.md).

Owner: Scenarios & analysis (Aditya).

Capacity reference for the 90 s fixed-time baseline (50/50 split, 40 s green per axis):
one lane discharges about 1,800 veh/h of green, so an approach gets about
1,800 × 41/90 ≈ 820 veh/h per lane — about 1,640 veh/h for the two-lane arterial and
820 veh/h for a one-lane cross street. The rush-hour peak loads the eastbound arterial to a
volume/capacity ratio near 0.9 (queues, occasional cycle failures) while the cross streets
stay near 0.3–0.4, so a controller that re-balances green time has real room to win.
"""
from __future__ import annotations

from teamb.demand.corridor import CorridorDemand
from teamb.demand.profiles import flat, peak

# Morning peak toward downtown (east). Rates are the peak hour; RUSH_PROFILE shapes them:
# shoulder during warm-up, ramp up 900–1800 s, 25-minute peak, ramp down to 4500 s.
RUSH_HOUR = CorridorDemand(
    eb_through=1200,
    wb_through=550,
    cross_through={"J1": 110, "J2": 200, "J3": 170, "J4": 110},
    eb_right=35,
    wb_right=25,
    nb_right=40,
    sb_right=30,
    nb_left=15,
    sb_left=20,
    truck_share=0.04,
    bus_per_hour=4,
)
RUSH_PROFILE = peak(start=900, ramp_up=900, hold=1500, ramp_down=1200, base=0.85, top=1.0, end_level=0.75, pre=(0, 0.80))

# Night: light, balanced traffic with more freight. Fixed-time makes drivers wait at empty
# junctions; detector-actuated control should shine here.
OFF_PEAK = CorridorDemand(
    eb_through=300,
    wb_through=260,
    cross_through={"J1": 35, "J2": 60, "J3": 50, "J4": 35},
    eb_right=10,
    wb_right=10,
    nb_right=10,
    sb_right=10,
    nb_left=5,
    sb_left=5,
    truck_share=0.10,
    bus_per_hour=2,
)
OFF_PEAK_PROFILE = flat(1.0)

# Weekend evening before/after a stadium event: balanced arterial, normal cross streets.
EVENING = CorridorDemand(
    eb_through=800,
    wb_through=750,
    cross_through={"J1": 90, "J2": 150, "J3": 130, "J4": 90},
    eb_right=25,
    wb_right=25,
    nb_right=30,
    sb_right=30,
    nb_left=15,
    sb_left=15,
    truck_share=0.02,
    bus_per_hour=4,
)
