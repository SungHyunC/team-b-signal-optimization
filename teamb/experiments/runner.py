"""Run an experiment matrix: scenarios x controllers x seeds x coverages (x sampling x preemption).

Each run is one ``SimEnv(...).run()`` writing into
``results/experiments/<name>/runs/<run name>/`` (the usual run outputs plus
``run_spec.json`` and ``events.json``). Runs that already have a ``summary.json`` are
skipped, so an interrupted experiment can be resumed and new controllers or seeds can be
added to an existing experiment later (``--force`` re-runs).

Runs execute in parallel worker processes (``workers``); each worker starts its own SUMO.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import shutil
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

from teamb import config

EXPERIMENTS_DIR = config.RESULTS / "experiments"


def short_hash(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:6]


@dataclass
class RunSpec:
    scenario: str
    controller: str
    seed: int
    coverage: float
    sampling: str = "uniform"
    ev_preemption: bool = True
    end_time: float | None = None
    controller_params: dict = field(default_factory=dict)
    scenario_params: dict = field(default_factory=dict)

    @property
    def variant(self) -> str:
        """Controller name plus a short hash of its parameters (if any)."""
        return self.controller + (f"-{short_hash(self.controller_params)}" if self.controller_params else "")

    @property
    def scenario_variant(self) -> str:
        return self.scenario + (f"-{short_hash(self.scenario_params)}" if self.scenario_params else "")

    @property
    def name(self) -> str:
        """Run directory name and resume key: every field that changes the run is in it.

        Default specs keep the historic names (so existing experiments still resume). A
        coverage that is not a whole percentage gets a decimal token (c12.5, not c12) and an
        explicit end time adds ``__e<seconds>``, so runs that differ never share a directory."""
        sampling = self.sampling.replace(":", "-")
        pre = "" if self.ev_preemption else "__nopre"
        end = "" if self.end_time is None else f"__e{_num_token(self.end_time)}"
        return (
            f"{self.scenario_variant}__{self.variant}__s{self.seed}__c{_num_token(self.coverage * 100)}"
            f"__{sampling}{pre}{end}"
        )


def _num_token(x: float) -> str:
    """'100' for a whole number (within float noise, e.g. 0.07 * 100), else the shortest decimal ('12.5')."""
    x = float(x)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.10g}"


def parse_seeds(text: str) -> list[int]:
    """'1-5' -> [1..5]; '1,3,7' -> [1, 3, 7]; '1-3,10' -> [1, 2, 3, 10]."""
    seeds: list[int] = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            if int(b) < int(a):
                raise ValueError(f"invalid seed range '{part}' (write low-high, e.g. 1-5)")
            seeds.extend(range(int(a), int(b) + 1))
        else:
            seeds.append(int(part))
    return sorted(dict.fromkeys(seeds))


def parse_coverages(text: str) -> list[float | None]:
    """'0.1,0.25,1' or percentages '10,25,100' / '1%,5%' -> [0.1, 0.25, 1.0]; 'default' -> [None]
    (None = the scenario's own default coverage, usually 1.0).

    A bare number above 1 is a percentage; a number with '%' is always a percentage, so
    '1%' is 0.01 (not 100 %) and '0.5%' is 0.005."""
    out: list[float | None] = []
    for part in str(text).split(","):
        part = part.strip()
        if part.lower() == "default":
            out.append(None)
        elif part:
            pct = part.endswith("%")
            v = float(part.rstrip("%").strip())
            out.append(v / 100.0 if (pct or v > 1.0) else v)
    return out


def scenario_default_coverage(scenario: str) -> float:
    from teamb.scenarios import get_scenario

    return float(get_scenario(scenario).defaults.get("coverage", 1.0))


def split_controller_params(params: dict | None, controllers: list[str]) -> dict[str, dict]:
    """--controller-params is either {"param": value} for every controller or
    {"controller_name": {"param": value}, ...} per controller."""
    params = params or {}
    if params and all(k in controllers and isinstance(v, dict) for k, v in params.items()):
        return {c: dict(params.get(c, {})) for c in controllers}
    return {c: dict(params) for c in controllers}


def build_matrix(
    scenarios: list[str],
    controllers: list[str],
    seeds: list[int],
    coverages: list[float],
    samplings: list[str] | None = None,
    preemption: list[bool] | None = None,
    end_time: float | None = None,
    controller_params: dict | None = None,
    scenario_params: dict | None = None,
    counterfactual: bool = False,
) -> list[RunSpec]:
    """All combinations. counterfactual=True adds, for every scenario with events, the same runs
    with the events removed (scenario_params events=[]): the "what if nothing had happened"
    reference used for recovery time under time-varying demand."""
    # repeated list entries (e.g. --controllers a,b,a) would give two specs with one run directory
    scenarios, controllers, seeds = list(dict.fromkeys(scenarios)), list(dict.fromkeys(controllers)), list(dict.fromkeys(seeds))
    samplings = list(dict.fromkeys(samplings)) if samplings else None
    preemption = list(dict.fromkeys(bool(p) for p in preemption)) if preemption else None
    per_controller = split_controller_params(controller_params, controllers)
    base_params = dict(scenario_params or {})
    twins: list[RunSpec] = []
    if counterfactual:
        from teamb.scenarios import get_scenario

        for scenario in scenarios:
            if "events" not in base_params and get_scenario(scenario, **base_params).events:
                twins += build_matrix(
                    [scenario], controllers, seeds, coverages, samplings, preemption, end_time,
                    controller_params, {**base_params, "events": []},
                )
    specs = []
    for scenario in scenarios:
        resolved = list(dict.fromkeys(scenario_default_coverage(scenario) if c is None else c for c in coverages))
        for controller in controllers:
            for coverage in resolved:
                for sampling in samplings or ["uniform"]:
                    for pre in preemption or [True]:
                        for seed in seeds:
                            specs.append(
                                RunSpec(
                                    scenario, controller, int(seed), float(coverage), sampling, bool(pre), end_time,
                                    per_controller[controller], dict(base_params),
                                )
                            )
    # the counterfactual twins run after the main runs; identical specs (same name) collapse to one
    return list({s.name: s for s in specs + twins}.values())


def validate_matrix(specs: list[RunSpec]) -> list[str]:
    """Problems that would make runs fail immediately (unknown names, bad sampling)."""
    from teamb.controllers import REGISTRY as CONTROLLERS
    from teamb.scenarios import REGISTRY as SCENARIOS
    from teamb.sensors.sampling import parse_sampling

    problems = []
    for name in sorted({s.controller for s in specs}):
        if name not in CONTROLLERS:
            problems.append(f"unknown controller '{name}' (registered: {', '.join(sorted(CONTROLLERS))})")
    for name in sorted({s.scenario for s in specs}):
        if name not in SCENARIOS:
            problems.append(f"unknown scenario '{name}' (registered: {', '.join(sorted(SCENARIOS))})")
    for sampling in sorted({s.sampling for s in specs}):
        try:
            parse_sampling(sampling)
        except ValueError as exc:
            problems.append(str(exc))
    for c in sorted({s.coverage for s in specs}):
        if not 0.0 < c <= 1.0:
            problems.append(f"coverage {c} outside (0, 1]")
    problems += name_collisions(specs)
    return problems


def name_collisions(specs: list[RunSpec]) -> list[str]:
    """Specs that would share a run directory: two different specs with one name, or a repeated spec."""
    by_name: dict[str, list[RunSpec]] = {}
    for s in specs:
        by_name.setdefault(s.name, []).append(s)
    problems = []
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        distinct = {json.dumps(asdict(s), sort_keys=True) for s in group}
        if len(distinct) > 1:
            problems.append(f"run name collision: {name} is used by {len(distinct)} different specs")
        else:
            problems.append(f"duplicate run: {name} appears {len(group)} times")
    return problems


def _dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def run_one(spec_dict: dict, runs_dir: str, force: bool = False) -> dict:
    """Execute one run (in a worker process). Never raises: failures are reported and logged."""
    spec = RunSpec(**spec_dict)
    out = Path(runs_dir) / spec.name
    if (out / "summary.json").exists() and not force:
        return {"run": spec.name, "status": "skipped", "summary": json.loads((out / "summary.json").read_text())}
    if out.exists() and force:
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "run_spec.json").write_text(json.dumps({**asdict(spec), "name": spec.name, "variant": spec.variant}, indent=2))
    (out / "error.json").unlink(missing_ok=True)
    t0 = time.time()
    try:
        from teamb.sim.env import SimEnv

        env = SimEnv(
            spec.scenario,
            spec.controller,
            seed=spec.seed,
            coverage=spec.coverage,
            sampling=spec.sampling,
            ev_preemption=spec.ev_preemption,
            controller_params=spec.controller_params or None,
            scenario_params=spec.scenario_params or None,
            end_time=spec.end_time,
            output_dir=out,
        )
        summary = env.run()
        (out / "events.json").write_text(json.dumps(env.events, indent=1, default=str))
    except Exception as exc:  # one broken run must not stop the experiment
        (out / "error.json").write_text(
            json.dumps({"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}, indent=2)
        )
        return {"run": spec.name, "status": "failed", "error": f"{type(exc).__name__}: {exc}", "wall_total_s": round(time.time() - t0, 2)}
    wall = round(time.time() - t0, 2)
    (out / "run_spec.json").write_text(
        json.dumps({**asdict(spec), "name": spec.name, "variant": spec.variant, "wall_total_s": wall, "bytes": _dir_bytes(out)}, indent=2)
    )
    return {"run": spec.name, "status": "ok", "summary": summary, "wall_total_s": wall}


def _progress_line(i: int, n: int, res: dict) -> str:
    if res["status"] == "failed":
        return f"[{i}/{n}] {res['run']}: FAILED {res['error']}"
    s = res.get("summary") or {}
    delay = s.get("mean_delay_s")
    tag = "skipped (already done)" if res["status"] == "skipped" else f"{res.get('wall_total_s', 0):.1f} s wall"
    return f"[{i}/{n}] {res['run']}: delay {delay} s/veh, unfinished {s.get('unfinished_pct')} %, {tag}"


def run_matrix(
    specs: list[RunSpec],
    exp_dir: Path,
    *,
    workers: int = 2,
    force: bool = False,
    quiet: bool = False,
    command: str | None = None,
    backend: str = "local",
) -> dict:
    """Run every spec (in parallel when workers > 1); returns an invocation record.

    backend="local" uses worker processes on this machine; backend="modal" runs each spec in
    its own Modal cloud container (see teamb/experiments/cloud.py) with ``workers`` containers.
    """
    collisions = name_collisions(specs)
    if collisions:  # two workers must never write into one run directory
        raise ValueError("; ".join(collisions))
    exp_dir = Path(exp_dir)
    runs_dir = exp_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    results = []
    n = len(specs)
    main_file = getattr(sys.modules.get("__main__"), "__file__", None)
    if workers > 1 and main_file and not Path(main_file).exists():
        # spawned workers re-import the main script; code piped in on stdin cannot be re-imported
        print("note: running sequentially (worker processes need a script file, not stdin)", flush=True)
        workers = 1
    if backend == "modal":
        from teamb.experiments import cloud
        from teamb.sim.env import _git_revision

        stream = cloud.run_specs(specs, runs_dir, workers=workers, force=force, git_revision=_git_revision())
        for i, res in enumerate(stream, 1):
            results.append(res)
            if not quiet:
                print(_progress_line(i, n, res), flush=True)
    elif backend != "local":
        raise ValueError(f"unknown backend '{backend}' (local or modal)")
    elif workers <= 1:
        for i, spec in enumerate(specs, 1):
            res = run_one(asdict(spec), str(runs_dir), force)
            results.append(res)
            if not quiet:
                print(_progress_line(i, n, res), flush=True)
    else:
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
            futures = [pool.submit(run_one, asdict(spec), str(runs_dir), force) for spec in specs]
            for i, fut in enumerate(as_completed(futures), 1):
                res = fut.result()
                results.append(res)
                if not quiet:
                    print(_progress_line(i, n, res), flush=True)
    record = {
        "command": command,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)),
        "wall_time_s": round(time.time() - t0, 1),
        "backend": backend,
        "workers": workers,
        "runs": n,
        "ok": sum(r["status"] == "ok" for r in results),
        "skipped": sum(r["status"] == "skipped" for r in results),
        "failed": [r["run"] for r in results if r["status"] == "failed"],
        "matrix": {
            "scenarios": sorted({s.scenario_variant for s in specs}),
            "controllers": sorted({s.variant for s in specs}),
            "seeds": sorted({s.seed for s in specs}),
            "coverages": sorted({s.coverage for s in specs}),
            "samplings": sorted({s.sampling for s in specs}),
            "ev_preemption": sorted({s.ev_preemption for s in specs}),
            "end_time": sorted({s.end_time for s in specs if s.end_time is not None}),
            "controller_params": {s.variant: s.controller_params for s in specs if s.controller_params},
            "scenario_params": {s.scenario_variant: s.scenario_params for s in specs if s.scenario_params},
        },
    }
    meta_path = exp_dir / "experiment.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"name": exp_dir.name, "created": record["started"], "invocations": []}
    meta["invocations"].append(record)
    meta_path.write_text(json.dumps(meta, indent=2))
    return record
