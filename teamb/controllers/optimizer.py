"""Timing-plan search for the AI recommender: Optuna (seeded TPE) over short SUMO runs.

Owner: AI & security (Yunseong).

    SearchSpec               everything that determines a search (its hash is the cache key)
    evaluate_plan(plan, s)   one headless SimEnv run of the *estimated* demand with a fixed plan
    run_search(s)            evaluate the current plan, then `trials` Optuna trials → best plan
    SearchJob(s)             run_search in a separate (spawned) process so the live twin never
                             waits; poll() returns progress messages and finally the result
    load_cache / save_cache  results/cache/ai_recommender/<key>.json, so repeated experiment
                             seeds do not redo identical searches

Search space (SearchSpec fields): cycle 60–150 s in 5 s steps; EW share of the usable green
per junction 0.25–0.85; offset of J2–J4 as a fraction of the cycle (J1 is the reference).
Objective (minimised): mean delay (s/veh) + unfinished_penalty_s × share of trips that
did not finish. Every candidate is run on the same demand seed (common random numbers),
so plans are compared on identical cars.

The first trials are engineering guesses — the Webster plan for the estimated flows, with
and without a green wave — so even a short search starts from a sensible plan.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import queue as queue_mod
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from teamb import config
from teamb.controllers.fixed_time import FixedTimeController, TimingPlan

SEARCH_VERSION = 2  # bump when the evaluation changes, so old cache files are not reused
# 2: relative offsets for the Webster seed trials, fixed-cycle green clamp in TimingPlan
CACHE_DIR = config.RESULTS / "cache" / "ai_recommender"


@dataclass
class SearchSpec:
    flows: list[dict]  # asdict(Flow) for the estimated demand
    current: dict  # TimingPlan.to_dict() of the plan running now (the baseline)
    seed_plans: list[dict] = field(default_factory=list)  # plans tried first (Webster, ...)
    junctions: list[str] = field(default_factory=lambda: list(config.JUNCTIONS))
    trials: int = 30
    eval_warmup: float = 300.0  # s of simulated traffic before measuring
    eval_horizon: float = 900.0  # s of measured departures
    cooldown: float = 150.0  # s after the demand stops, so measured cars can finish
    eval_seed: int = 11  # demand seed shared by all candidates
    sampler_seed: int = 0
    unfinished_penalty_s: float = 600.0
    cycle_range: tuple[int, int] = (60, 150)
    cycle_step: int = 5
    split_range: tuple[float, float] = (0.25, 0.85)
    version: int = SEARCH_VERSION

    def key(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True, default=list)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def scenario(self):
        """The estimated demand as a Scenario: flows run until warmup + horizon, then a cool-down."""
        from teamb.demand.routes import Flow
        from teamb.scenarios import Scenario

        stop = self.eval_warmup + self.eval_horizon
        flows = [Flow(**{**f, "begin": 0.0, "end": stop}) for f in self.flows]
        return Scenario(
            name="ai_eval",
            title="AI recommender · estimated demand",
            title_ko="AI 추천 · 추정 수요",
            description="Demand estimated from navigation-app probes, used to score timing plans.",
            flows=flows,
            warmup=self.eval_warmup,
            duration=stop + self.cooldown,
            owner="AI & security (Yunseong)",
        )


# --- plans <-> numbers -----------------------------------------------------------
def plan_from_dict(d: dict) -> TimingPlan:
    return TimingPlan(cycle=float(d["cycle"]), splits=dict(d.get("splits", {})), offsets=dict(d.get("offsets", {})))


def plan_controller(plan: TimingPlan) -> FixedTimeController:
    """A fixed-time controller that runs exactly `plan` (the supervisor still adds yellow/all-red)."""
    ctl = FixedTimeController(cycle=plan.cycle, offsets=plan.offsets)
    ctl.plan.splits.update(plan.splits)  # reset() only fills junctions that are missing
    return ctl


def plan_to_params(plan: TimingPlan, spec: SearchSpec) -> dict:
    lo, hi = spec.cycle_range
    cycle = int(min(hi, max(lo, spec.cycle_step * round(plan.cycle / spec.cycle_step))))
    s_lo, s_hi = spec.split_range
    params = {"cycle": cycle}
    for j in spec.junctions:
        params[f"split_{j}"] = min(s_hi, max(s_lo, plan.splits.get(j, 0.5)))
    # suggest_plan pins the first junction at offset 0, so express the others relative to it
    ref = plan.offsets.get(spec.junctions[0], 0.0)
    for j in spec.junctions[1:]:
        params[f"offset_{j}"] = ((plan.offsets.get(j, 0.0) - ref) / cycle) % 1.0
    return params


def suggest_plan(trial, spec: SearchSpec) -> TimingPlan:
    cycle = trial.suggest_int("cycle", spec.cycle_range[0], spec.cycle_range[1], step=spec.cycle_step)
    splits = {j: round(trial.suggest_float(f"split_{j}", *spec.split_range), 3) for j in spec.junctions}
    offsets = {spec.junctions[0]: 0.0}
    for j in spec.junctions[1:]:
        offsets[j] = round(trial.suggest_float(f"offset_{j}", 0.0, 1.0) * cycle, 1)
    return TimingPlan(cycle=float(cycle), splits=splits, offsets=offsets)


def webster_plan(demand: dict, lanes: dict, *, junction_x=None, sat_flow: float = 1800.0,
                 cycle_range=(60, 150), progression_speed: float = 12.5, green_wave: bool = True) -> TimingPlan:
    """Webster (1958): cycle C0 = (1.5·L + 5) / (1 − Y), greens ∝ critical flow ratios.

    demand: veh/h per (junction, side); lanes: lanes per (junction, side). L = lost time
    per cycle (2 × yellow + all-red); Y = the largest sum of critical flow ratios. With
    `green_wave`, offsets follow the heavier arterial direction at `progression_speed`.
    """
    junction_x = junction_x or config.JUNCTION_X
    junctions = sorted({j for j, _ in demand} | set(junction_x)) if demand else list(junction_x)
    ratios = {}
    for j in junctions:
        y = {}
        for axis, sides in (("EW", ("W", "E")), ("NS", ("N", "S"))):
            y[axis] = max((demand.get((j, s), 0.0) / (max(1, lanes.get((j, s), 1)) * sat_flow) for s in sides), default=0.0)
        ratios[j] = y
    big_y = min(0.9, max(y["EW"] + y["NS"] for y in ratios.values()))
    lost = 2 * config.LOST_TIME_PER_SWITCH_S
    c0 = (1.5 * lost + 5) / (1 - big_y)
    cycle = float(min(cycle_range[1], max(cycle_range[0], 5 * round(c0 / 5))))
    splits = {j: round(y["EW"] / (y["EW"] + y["NS"]), 3) if y["EW"] + y["NS"] > 0 else 0.5 for j, y in ratios.items()}
    offsets = {j: 0.0 for j in junctions}
    if green_wave:
        eastbound = sum(demand.get((j, "W"), 0.0) for j in junctions) >= sum(demand.get((j, "E"), 0.0) for j in junctions)
        x0 = min(junction_x.values()) if eastbound else max(junction_x.values())
        for j in junctions:
            offsets[j] = round((abs(junction_x[j] - x0) / progression_speed) % cycle, 1)
    return TimingPlan(cycle=cycle, splits=splits, offsets=offsets)


# --- one evaluation -----------------------------------------------------------------
def evaluate_plan(plan: TimingPlan, spec: SearchSpec) -> dict:
    """Run the estimated demand once with `plan`; return delay, unfinished and the objective."""
    from teamb.controllers.fast_env import PlanEvalEnv  # lazy: teamb.sim imports controllers

    scenario = spec.scenario()
    with tempfile.TemporaryDirectory(prefix="teamb_ai_eval_") as tmp:
        env = PlanEvalEnv(scenario, plan_controller(plan), seed=spec.eval_seed, end_time=scenario.duration,
                          output_dir=tmp, ev_preemption=False)
        summary = env.run()
    delay = summary.get("mean_delay_s")
    finished, unfinished = summary.get("completed", 0), summary.get("unfinished", 0)
    share = unfinished / max(1, finished + unfinished)
    objective = (delay if delay is not None else 1e4) + spec.unfinished_penalty_s * share
    return {
        "objective": round(objective, 3),
        "mean_delay_s": delay,
        "p95_travel_time_s": summary.get("p95_travel_time_s"),
        "completed": finished,
        "unfinished": unfinished,
    }


# --- the search -----------------------------------------------------------------------
def run_search(spec: SearchSpec, progress=None) -> dict:
    """Baseline + `spec.trials` Optuna trials. progress(done, total, best_objective) after each run."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    wall0 = time.time()
    total = spec.trials + 1
    current = plan_from_dict(spec.current)
    baseline = evaluate_plan(current, spec)
    if progress:
        progress(1, total, baseline["objective"])

    sampler = optuna.samplers.TPESampler(seed=spec.sampler_seed, n_startup_trials=min(10, max(3, spec.trials // 3)),
                                         multivariate=True)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    for plan in spec.seed_plans[: max(0, spec.trials - 1)]:
        study.enqueue_trial(plan_to_params(plan_from_dict(plan), spec), skip_if_exists=True)

    def objective(trial):
        plan = suggest_plan(trial, spec)
        result = evaluate_plan(plan, spec)
        trial.set_user_attr("plan", plan.to_dict())
        trial.set_user_attr("result", result)
        return result["objective"]

    def report(study, trial):
        if progress:
            progress(trial.number + 2, total, min(study.best_value, baseline["objective"]))

    study.optimize(objective, n_trials=spec.trials, callbacks=[report])
    ranked = sorted((t for t in study.trials if t.value is not None), key=lambda t: t.value)
    best = study.best_trial if ranked else None  # trials=0: nothing to compare, keep the current plan
    better = best is not None and best.value < baseline["objective"]
    chosen = best.user_attrs["result"] if better else baseline
    base_delay, new_delay = baseline["mean_delay_s"], chosen["mean_delay_s"]
    improvement = 100.0 * (base_delay - new_delay) / base_delay if base_delay and new_delay is not None else 0.0
    if best is None:
        note = "no search trials were run; keep the current plan"
    else:
        note = "" if better else "no candidate beat the current plan; keep it"
    return {
        "plan": best.user_attrs["plan"] if better else current.to_dict(),
        "expected": {
            "mean_delay_s": new_delay,
            "baseline_mean_delay_s": base_delay,
            "improvement_pct": round(improvement, 1),
            "objective": chosen["objective"],
            "baseline_objective": baseline["objective"],
            "unfinished": chosen["unfinished"],
        },
        "note": note,
        "top_trials": [{"number": t.number, "objective": round(t.value, 2), **t.user_attrs["plan"]} for t in ranked[:5]],
        "trials": len(study.trials),
        "wall_s": round(time.time() - wall0, 1),
    }


# --- cache -------------------------------------------------------------------------------
def _cache_path(spec: SearchSpec, cache_dir) -> Path:
    return Path(cache_dir) / f"{spec.key()}.json"


def load_cache(spec: SearchSpec, cache_dir=CACHE_DIR) -> dict | None:
    path = _cache_path(spec, cache_dir)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    same = json.dumps(data.get("spec"), sort_keys=True, default=list) == json.dumps(asdict(spec), sort_keys=True, default=list)
    return data.get("result") if same else None  # guards against stale or edited files


def save_cache(spec: SearchSpec, result: dict, cache_dir=CACHE_DIR) -> Path:
    path = _cache_path(spec, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"spec": asdict(spec), "result": result, "created_unix": round(time.time())}
    path.write_text(json.dumps(payload, indent=1, default=list))
    return path


# --- background worker -----------------------------------------------------------------
def _search_worker(spec_dict: dict, out) -> None:
    """Runs in the spawned process: progress messages, then ("result", ...) or ("error", ...)."""
    try:
        spec = SearchSpec(**spec_dict)
        result = run_search(spec, progress=lambda done, total, best: out.put(("progress", done, total, best)))
        out.put(("result", result))
    except Exception as exc:  # report, never crash silently
        out.put(("error", f"{type(exc).__name__}: {exc}"))


class SearchJob:
    """run_search in its own process (spawn), so the simulation thread never blocks."""

    def __init__(self, spec: SearchSpec):
        ctx = mp.get_context("spawn")
        self.spec = spec
        self.queue = ctx.Queue()
        self.process = ctx.Process(target=_search_worker, args=(asdict(spec), self.queue), daemon=True,
                                   name="teamb-ai-search")
        self.process.start()

    def poll(self) -> list[tuple]:
        """All messages that arrived since the last poll (never blocks)."""
        # Check liveness *before* draining: a worker that was already dead has flushed everything
        # it sent into the pipe, so an empty drain really means "no result". Checking after the
        # drain could miss a result put just before the worker exited.
        alive = self.process.is_alive()
        messages = []
        while True:
            try:
                messages.append(self.queue.get_nowait())
            except queue_mod.Empty:
                break
        if not alive:
            self.process.join(timeout=0)  # reap it, no zombie
            if not messages:
                messages.append(("error", f"search process ended without a result (exit code {self.process.exitcode})"))
        return messages

    def cancel(self) -> None:
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=2)

