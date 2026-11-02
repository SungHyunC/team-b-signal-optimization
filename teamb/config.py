"""Shared constants and paths.

The geometry and timing values follow Aditya's reference system design. They are
provisional design assumptions, not field-calibrated values.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = Path(__file__).resolve().parent
GENERATED = PKG / "network" / "generated"
RESULTS = ROOT / "results"
MODELS = ROOT / "models"

# --- Corridor geometry (meters) -------------------------------------------
JUNCTIONS = ("J1", "J2", "J3", "J4")
JUNCTION_X = {"J1": 0.0, "J2": 300.0, "J3": 600.0, "J4": 900.0}
ARTERIAL_WEST_X = -300.0
ARTERIAL_EAST_X = 1200.0
BACKSTREET_Y = 250.0  # parallel street north of the arterial, used as a detour
NORTH_EDGE_Y = 450.0  # where the cross streets enter/leave in the north
SOUTH_EDGE_Y = -250.0

ARTERIAL_LANES = 2
ARTERIAL_SPEED = 13.89  # 50 km/h
CROSS_SPEED = 11.11  # 40 km/h
BACKSTREET_SPEED = 8.33  # 30 km/h

# --- Simulation ---------------------------------------------------------
STEP_LENGTH = 1.0
WARMUP_S = 900
MEASURE_S = 3600

# --- Signal timing (safety supervisor) ----------------------------------
BASE_CYCLE_S = 90
MIN_GREEN_S = 8
PREEMPT_MIN_GREEN_S = 5  # emergency-vehicle preemption may cut a green this short
YELLOW_S = 3
ALL_RED_S = 2
LOST_TIME_PER_SWITCH_S = YELLOW_S + ALL_RED_S

CONTROLLER_TIME_BUDGET_S = 0.25  # wall-clock budget per decision before the fallback takes over
EV_PREEMPT_DISTANCE_M = 150.0
