"""Validated, portable scenario presets for the public sandbox (phase 1).

The builder exports this JSON; SUMO execution is deliberately separate.
Only approved scenario overrides are passed to the existing experiment runner.

The allowed scenarios and controllers come from the scenario and controller registries, and
GET /api/sandbox/schema (``schema()``) publishes them with the numeric limits, so the web
builder never has to keep its own copy in sync.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

from teamb.controllers import REGISTRY as _CONTROLLER_REGISTRY
from teamb.scenarios import REGISTRY as _SCENARIO_REGISTRY, get_scenario

SCHEMA_VERSION = 1
SCENARIO_NAMES = tuple(_SCENARIO_REGISTRY)  # catalog order, for menus
CONTROLLER_NAMES = tuple(_CONTROLLER_REGISTRY)
SCENARIOS = frozenset(SCENARIO_NAMES)
CONTROLLERS = frozenset(CONTROLLER_NAMES)
SEED_RANGE = (0, 2_147_483_647)
DEMAND_SCALE_RANGE = (0.1, 3.0)
MIN_MEASURED_S = 300  # a run must measure at least this long after the warm-up
# 900 s warm-up + 300 s measured, up to the longest run the hosted twin accepts.
DURATION_RANGE = (1200, 10800)
# A sandbox run is headless: nobody can approve the AI recommender's plan, so it is approved
# automatically, as `teamb run` does (otherwise the run stays on the starting plan).
HEADLESS_CONTROLLER_PARAMS = {"ai_recommender": {"auto_approve": True}}


def _json_number(value):
    """1.0 -> 1, as JavaScript's JSON.stringify writes it; other numbers unchanged.

    The run name hashes scenario_params as JSON, so {"demand_scale": 1.0} and {"demand_scale": 1}
    would name the same run differently. The web builder can only write 1.
    """
    return int(value) if isinstance(value, float) and value.is_integer() else value


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
        """Arguments understood by the existing experiment matrix builder.

        Exactly the runs `experiment_command()` gives: coverage None is the scenario's own
        default (what the CLI's --coverages default means; fake_data_attack runs at 25 %), and
        end_time is a float like the CLI's --end; a whole-number demand_scale is written like the
        web builder writes it (1, not 1.0), so both give the same run name. ai_recommender gets
        auto_approve (HEADLESS_CONTROLLER_PARAMS): its run name then carries a parameter hash.
        """
        kwargs = {
            "scenarios": [self.scenario],
            "controllers": [self.controller],
            "seeds": [self.seed],
            "coverages": [None],
            "preemption": [self.ev_preemption],
            "end_time": None if self.duration_s is None else float(self.duration_s),
            "scenario_params": {"demand_scale": _json_number(self.demand_scale)},
        }
        params = _controller_params(self.controller)
        if params:
            kwargs["controller_params"] = params
        return kwargs


def _controller_params(controller: str) -> dict | None:
    """--controller-params for a sandbox run of `controller` ({controller: {...}}), or None."""
    params = HEADLESS_CONTROLLER_PARAMS.get(controller)
    return {controller: dict(params)} if params else None


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
    lo, hi = SEED_RANGE
    if type(cfg.seed) is not int or not lo <= cfg.seed <= hi:
        raise ValueError("seed must be a nonnegative 32-bit integer")
    lo, hi = DEMAND_SCALE_RANGE
    if type(cfg.demand_scale) not in (float, int) or not math.isfinite(cfg.demand_scale) or not lo <= cfg.demand_scale <= hi:
        raise ValueError(f"demand_scale must be between {lo} and {hi}")
    if type(cfg.ev_preemption) is not bool:
        raise ValueError("ev_preemption must be a boolean")
    if cfg.duration_s is not None:
        lo, hi = DURATION_RANGE
        if type(cfg.duration_s) is not int or not lo <= cfg.duration_s <= hi:
            raise ValueError(f"duration_s must be null or {lo}–{hi} seconds (the {lo - MIN_MEASURED_S:.0f} s warm-up "
                             f"plus at least {MIN_MEASURED_S} s measured)")
        warmup = get_scenario(cfg.scenario).warmup
        if cfg.duration_s < warmup + MIN_MEASURED_S:  # a scenario with a longer warm-up than usual
            raise ValueError(f"duration_s must be at least {warmup + MIN_MEASURED_S:.0f} s for {cfg.scenario} "
                             f"({warmup:.0f} s warm-up plus {MIN_MEASURED_S} s measured)")
    return cfg


def schema() -> dict:
    """What GET /api/sandbox/schema returns: the allowed values the web builder validates against."""
    return {
        "schema_version": SCHEMA_VERSION,
        "scenarios": list(SCENARIO_NAMES),
        "controllers": list(CONTROLLER_NAMES),
        "limits": {
            "seed": list(SEED_RANGE),
            "demand_scale": list(DEMAND_SCALE_RANGE),
            "duration_s": list(DURATION_RANGE),
        },
    }


def experiment_command(cfg: SandboxConfig, name: str = "sandbox_trial") -> str:
    """The equivalent `teamb exp run` command line (what the sandbox page shows).

    It builds exactly the specs of ``build_matrix(**cfg.experiment_kwargs())``: no --coverages
    (the CLI default is the scenario's own coverage), --end only when duration_s is set, and
    --controller-params only for a controller in HEADLESS_CONTROLLER_PARAMS.
    """
    import shlex

    parts = [
        "teamb", "exp", "run", "--name", name, "--scenarios", cfg.scenario, "--controllers", cfg.controller,
        "--seeds", str(cfg.seed), "--ev-preemption", "on" if cfg.ev_preemption else "off",
        "--scenario-params", json.dumps({"demand_scale": _json_number(cfg.demand_scale)}),
    ]
    if cfg.duration_s is not None:
        parts += ["--end", str(cfg.duration_s)]
    params = _controller_params(cfg.controller)
    if params:
        parts += ["--controller-params", json.dumps(params)]
    return " ".join(shlex.quote(p) for p in parts)


def main(argv: list[str] | None = None) -> int:
    """`teamb sandbox validate|run <export.json>`: check or execute a Scenario Sandbox export."""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(prog="teamb sandbox", description="Validate or run a Scenario Sandbox JSON export.")
    sub = parser.add_subparsers(dest="command", required=True)
    val = sub.add_parser("validate", help="check the file and print the equivalent experiment command")
    val.add_argument("config", type=Path)
    run = sub.add_parser("run", help="run the exported scenario in SUMO and write a report")
    run.add_argument("config", type=Path)
    run.add_argument("--name", default="sandbox_trial", help="experiment folder under results/experiments/")
    run.add_argument("--backend", choices=("local", "modal"), default="local")
    run.add_argument("--force", action="store_true", help="re-run even if results exist")
    args = parser.parse_args(argv)

    try:
        cfg = parse_sandbox_config(args.config.read_text())
    except (OSError, ValueError, TypeError) as exc:
        print(f"invalid sandbox file {args.config}: {exc}")
        return 2
    print(cfg.to_json())
    command = experiment_command(cfg, getattr(args, "name", "sandbox_trial"))
    if args.command == "validate":
        print(f"\nvalid. equivalent command:\n  {command}")
        return 0

    from teamb.experiments.analysis import write_report
    from teamb.experiments.runner import EXPERIMENTS_DIR, build_matrix, run_matrix

    specs = build_matrix(**cfg.experiment_kwargs())
    exp_dir = EXPERIMENTS_DIR / args.name
    record = run_matrix(specs, exp_dir, workers=1, force=args.force, command=command, backend=args.backend)
    if record["failed"]:
        print(f"run failed: see {exp_dir / 'runs'}/*/error.json")
        return 1
    summary = json.loads(next((exp_dir / "runs").glob(f"{specs[0].name}/summary.json")).read_text())
    keys = ("mean_delay_s", "completed", "unfinished_pct", "stops_per_veh", "max_queue_veh", "controller_errors")
    print("\n" + "\n".join(f"  {k:<18s} {summary.get(k)}" for k in keys))
    write_report(exp_dir, baseline=cfg.controller)
    print(f"\nresults: {exp_dir}")
    return 0
