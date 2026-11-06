"""Run an experiment matrix: scenarios x controllers x seeds x coverages (x sampling x preemption).

Each run is one ``SimEnv(...).run()`` writing into
``results/experiments/<name>/runs/<run name>/`` (the usual run outputs plus
``run_spec.json`` and ``events.json``). Finished runs are skipped, so an interrupted
experiment can be resumed and new controllers or seeds can be added to an existing
experiment later (``--force`` re-runs).

A run counts as finished (see :func:`run_status`) only if its ``summary.json`` parses, is not
marked ``"complete": false``, no ``error.json`` sits next to it, and ``sim_time_s`` reached the
run's end time. Before a finished run is skipped, its saved ``run_spec.json`` is compared with
the requested spec; a mismatch is reported as a failure instead of silently reusing another
run's results. A failed or interrupted run (including Ctrl-C) leaves ``error.json`` and no
``summary.json``, so the next invocation runs it again.

Runs execute in parallel worker processes (``workers``); each worker starts its own SUMO.
"""
from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import shutil
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

from teamb import config
from teamb.fsutil import atomic_write_json, atomic_write_text, read_json

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


# the RunSpec fields a saved run_spec.json must match before its results are reused
SPEC_KEYS = ("scenario", "controller", "seed", "coverage", "sampling", "ev_preemption",
             "end_time", "controller_params", "scenario_params")


def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-9)
    return a == b


def spec_mismatch(saved: dict, spec: RunSpec) -> list[str]:
    """Fields where a saved run_spec.json differs from `spec`, e.g. ["end_time (saved 1200.0, requested 2000.0)"].

    end_time None means "the scenario's duration", so None and an explicit end equal to that
    duration are the same run (an experiment from before end_time was part of the run name)."""
    out = []
    for key in SPEC_KEYS:
        if key not in saved:
            continue
        a, b = saved[key], getattr(spec, key)
        if key == "end_time" and (a is None) != (b is None):
            a, b = (scenario_end(spec) if a is None else a), (scenario_end(spec) if b is None else b)
        if not _same(a, b):
            out.append(f"{key} (saved {saved[key]!r}, requested {getattr(spec, key)!r})")
    return out


def scenario_end(spec: RunSpec) -> float | None:
    """The end time `spec` runs to: its end_time, else the scenario's duration (None if unknown)."""
    if spec.end_time is not None:
        return float(spec.end_time)
    try:
        from teamb.scenarios import get_scenario

        return float(get_scenario(spec.scenario, **(spec.scenario_params or {})).duration)
    except Exception:  # unknown scenario or parameters: the completeness check falls back to the manifest
        return None


def _number(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def run_status(run_dir: str | Path, *, expected_end: float | None = None,
               default_end: float | None = None) -> tuple[str, dict | None, str | None]:
    """Did the run in `run_dir` finish? Returns (status, summary or None, reason or None).

    status "ok"         summary.json parses as an object, is not marked "complete": false (legacy
                        summaries have no key), there is no error.json, and sim_time_s reached the
                        end time when it is known: `expected_end`, else the manifest's
                        config.end_time, else `default_end`
    status "failed"     error.json is present (reason = its error message)
    status "incomplete" anything else: no or unreadable summary.json, or a truncated run
    """
    run_dir = Path(run_dir)
    summary = read_json(run_dir / "summary.json")
    summary = summary if isinstance(summary, dict) else None
    if (run_dir / "error.json").exists():
        err = read_json(run_dir / "error.json", {})
        return "failed", summary, (err.get("error") if isinstance(err, dict) else None) or "error.json present"
    if summary is None:
        missing = not (run_dir / "summary.json").exists()
        return "incomplete", None, "no summary.json" if missing else "unreadable summary.json"
    if summary.get("complete", True) is False:
        return "incomplete", summary, "summary.json is marked complete: false"
    end = _number(expected_end)
    if end is None:
        manifest = read_json(run_dir / "manifest.json", {})
        end = _number((manifest.get("config") or {}).get("end_time")) if isinstance(manifest, dict) else None
    if end is None:
        end = _number(default_end)
    sim = _number(summary.get("sim_time_s"))
    if end is not None and sim is not None and sim + 1e-6 < end:
        return "incomplete", summary, f"stopped at sim_time_s {sim:g} before the end time {end:g}"
    return "ok", summary, None


def check_resume(spec: RunSpec, runs_dir: str | Path) -> dict | None:
    """The result for a run that need not execute again, or None if it must (re-)run.

    {"status": "skipped", "summary"} for a finished run of exactly this spec; {"status": "failed",
    "error": "spec mismatch: ..."} when the directory holds a finished run of a different spec
    (its results are kept, never reused). Failed, interrupted or truncated runs return None.
    Also used by the cloud backend, so local and Modal runs resume the same way."""
    out = Path(runs_dir) / spec.name
    if not out.is_dir():
        return None
    status, summary, _ = run_status(out, expected_end=spec.end_time, default_end=scenario_end(spec))
    saved = read_json(out / "run_spec.json")
    if status != "ok" or not isinstance(saved, dict):
        return None
    diff = spec_mismatch(saved, spec)
    if diff:
        return {
            "run": spec.name, "status": "failed",
            "error": f"spec mismatch: {'; '.join(diff)}. {out} holds a different run; delete it or re-run with --force",
        }
    return {"run": spec.name, "status": "skipped", "summary": summary}


def run_one(spec_dict: dict, runs_dir: str, force: bool = False) -> dict:
    """Execute one run (in a worker process). Failures are reported and logged in error.json;
    only an interruption (KeyboardInterrupt, SystemExit) is re-raised, after writing error.json."""
    spec = RunSpec(**spec_dict)
    out = Path(runs_dir) / spec.name
    if not force:
        done = check_resume(spec, runs_dir)
        if done is not None:
            return done
    if out.exists():  # forced, or a failed / interrupted / truncated run: start from a clean directory
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "run_spec.json", {**asdict(spec), "name": spec.name, "variant": spec.variant})
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
        atomic_write_text(out / "events.json", json.dumps(env.events, indent=1, default=str))
        status, _, reason = run_status(out, expected_end=getattr(env, "end_time", None), default_end=scenario_end(spec))
        if status != "ok":
            raise RuntimeError(f"the run returned without a complete summary.json ({reason})")
    except BaseException as exc:  # one broken run must not stop the experiment
        interrupted = not isinstance(exc, Exception)
        error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        # a summary written on the way out describes a partial run: never let it pass as finished
        (out / "summary.json").unlink(missing_ok=True)
        atomic_write_json(out / "error.json", {"error": error, "interrupted": interrupted, "traceback": traceback.format_exc()})
        if interrupted:  # Ctrl-C / SystemExit: leave the failure marker, then stop
            raise
        return {"run": spec.name, "status": "failed", "error": error, "wall_total_s": round(time.time() - t0, 2)}
    wall = round(time.time() - t0, 2)
    atomic_write_json(
        out / "run_spec.json",
        {**asdict(spec), "name": spec.name, "variant": spec.variant, "wall_total_s": wall, "bytes": _dir_bytes(out)},
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
