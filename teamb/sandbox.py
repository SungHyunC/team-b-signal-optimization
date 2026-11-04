"""Validated, portable scenario presets for the public sandbox (phase 1).

The builder exports this JSON; SUMO execution is deliberately separate.
Only approved scenario overrides are passed to the existing experiment runner.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

SCHEMA_VERSION = 1
SCENARIOS = frozenset(("rush_hour", "off_peak", "special_event", "emergency",
                       "road_closure", "sinkhole_cross", "earthquake", "fake_data_attack"))
CONTROLLERS = frozenset(("fixed_time", "coordinated", "actuated",
                         "max_pressure", "max_pressure_probe", "ai_recommender", "rl"))


@dataclass(frozen=True)
class SandboxConfig:
    scenario: str = "rush_hour"
    controller: str = "max_pressure"
    seed: int = 1
    demand_scale: float = 1.0
    ev_preemption: bool = True
    duration_s: int | None = None
    schema_version: int = SCHEMA_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def experiment_kwargs(self) -> dict:
        """Arguments understood by the existing experiment matrix builder."""
        return {
            "scenarios": [self.scenario],
            "controllers": [self.controller],
            "seeds": [self.seed],
            "coverages": [1.0],
            "preemption": [self.ev_preemption],
            "end_time": self.duration_s,
            "scenario_params": {"demand_scale": self.demand_scale},
        }


def parse_sandbox_config(value: dict | str) -> SandboxConfig:
    """Reject unknown keys and invalid values instead of silently changing a run."""
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("sandbox configuration must be a JSON object")
    allowed = set(SandboxConfig.__dataclass_fields__)
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unknown sandbox fields: {', '.join(sorted(unknown))}")
    cfg = SandboxConfig(**value)
    if type(cfg.schema_version) is not int or cfg.schema_version != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    if cfg.scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {cfg.scenario}")
    if cfg.controller not in CONTROLLERS:
        raise ValueError(f"unknown controller: {cfg.controller}")
    if type(cfg.seed) is not int or not 0 <= cfg.seed <= 2_147_483_647:
        raise ValueError("seed must be a nonnegative 32-bit integer")
    if type(cfg.demand_scale) not in (float, int) or not math.isfinite(cfg.demand_scale) or not 0.1 <= cfg.demand_scale <= 3.0:
        raise ValueError("demand_scale must be between 0.1 and 3.0")
    if type(cfg.ev_preemption) is not bool:
        raise ValueError("ev_preemption must be a boolean")
    if cfg.duration_s is not None and (type(cfg.duration_s) is not int or not 60 <= cfg.duration_s <= 10800):
        raise ValueError("duration_s must be 60–10800 seconds")
    return cfg
