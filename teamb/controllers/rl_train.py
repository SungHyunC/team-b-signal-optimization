"""Train the RL controller:  python -m teamb.controllers.rl_train   (or: teamb train-rl)

Owner: AI & security (Yunseong).

Batch Q-learning with experience replay (works the same with 1 or many workers):

    table = empty Q-table with --features v1|v2 (or --resume: continue from --out)
    repeat until --episodes (or --max-minutes) is reached:
        run one round of --round-size episodes (default: --workers) with the current table,
        epsilon-greedy (linear from --eps-start to --eps-end over the episodes), each with
            a scenario drawn at random from --scenarios (default: --scenario, rush_hour),
            a fresh training seed (>= 1000), demand × U(--demand-range) (default 1 ± --jitter)
            → transitions (s, a, R, k, s') from RLController(learn=True)
        on --backend local (spawned worker processes) or modal (one cloud container per
        episode, teamb.experiments.cloud.rl_episode_runner)
        count every collected transition once as a visit (replays are not visits)
        keep the last --buffer episodes (at least one round) in a replay buffer
        sweep the buffer --sweeps times in random order with the Q-learning update
        every --checkpoint-every rounds: save --out (atomic write, so it is always loadable)
    save --out with the training curve (one record per round) and a per-episode log

Held-out seeds: episode i of `--seed k` uses SUMO seed 1000 + 1 000 000·k + i, always ≥ 1000.
Evaluate on seeds below 1000 (the experiments use 1–99), so evaluation never sees training
traffic. --resume continues the episode index, so no seed is trained on twice, and keeps what
earlier invocations trained on: meta.scenarios is the union of every session's scenarios and
meta.sessions holds each invocation's seed range, scenarios, demand range, episode length and hyper.
Episodes run in TrainEnv (sensors read on decision ticks only, see fast_env.py).

Tunable: --episodes, --workers, --round-size, --backend, --end (s, or "full" = each
scenario's own duration), --scenario/--scenarios, --demand-range or --jitter, --features,
--alpha, --gamma, --eps-start/--eps-end, --sweeps, --buffer, --switch-penalty, --coverage,
--checkpoint-every, --max-minutes, --seed, --out, --resume.
The defaults (60 episodes × 1800 s of rush hour, 2 workers) took 10 minutes here and are the
recipe of the first committed model (models/rl_qtable_v1_rush_hour.json).
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import tempfile
import time
from collections import Counter, deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path

import numpy as np

from teamb.controllers.rl import FEATURE_SETS, MODEL_PATH, QTable, RLController

TRAIN_SEED_BASE = 1000  # training seeds start here; evaluation uses seeds below it
SEED_STRIDE = 1_000_000  # --seed k trains on seeds 1000 + k·SEED_STRIDE + episode index
MAX_SEED_ARG = 2000  # keeps every SUMO seed below 2**31
BACKENDS = ("local", "modal")
LOG_KEYS = ("seed", "scenario", "epsilon", "demand_scale", "reward", "mean_delay_s", "unfinished", "switches")


def training_seed(seed: int, index: int) -> int:
    """SUMO seed of training episode `index` (0-based) for `--seed seed`; always ≥ TRAIN_SEED_BASE."""
    if not 0 <= seed < MAX_SEED_ARG or index < 0:
        raise ValueError(f"--seed must be in [0, {MAX_SEED_ARG}) and the episode index >= 0")
    return TRAIN_SEED_BASE + seed * SEED_STRIDE + index


def run_episode(job: dict) -> dict:
    """One training episode in its own SUMO run (worker processes and Modal containers call this).

    Returns the episode's transitions and its stats. `job["end"]` None means the scenario's
    full duration.
    """
    from teamb.controllers.fast_env import TrainEnv
    from teamb.scenarios import get_scenario

    end = float(job["end"]) if job.get("end") else float(get_scenario(job["scenario"]).duration)
    scenario = get_scenario(job["scenario"], warmup=min(300.0, end / 2))
    for flow in scenario.flows:
        flow.veh_per_hour *= job["demand_scale"]
    controller = RLController(epsilon=job["epsilon"], learn=True, switch_penalty=job["switch_penalty"], gamma=job["gamma"])
    controller.table = QTable.from_dict(job["table"])
    wall0 = time.time()
    with tempfile.TemporaryDirectory(prefix="teamb_rl_") as tmp:
        env = TrainEnv(scenario, controller, seed=job["seed"], coverage=job["coverage"], end_time=end,
                       output_dir=tmp, observe_every=int(controller.interval))
        summary = env.run()
    return {
        "scenario": job["scenario"],
        "seed": job["seed"],
        "epsilon": round(job["epsilon"], 4),
        "demand_scale": round(job["demand_scale"], 3),
        "end": end,
        "transitions": controller.transitions,
        "reward": round(controller.episode_reward, 2),
        "mean_delay_s": summary.get("mean_delay_s"),
        "unfinished": summary.get("unfinished"),
        "switches": summary.get("signal_switches"),
        "errors": summary.get("controller_errors", 0) + summary.get("fallback_steps", 0),
        "wall_s": round(time.time() - wall0, 1),
    }


def epsilon_at(index: int, episodes: int, start: float, end: float) -> float:
    """Exploration rate of episode `index` (0-based): linear from `start` to exactly `end` at the last one.

    Computed per episode, not per parallel batch, so the last episode really uses `end`.
    """
    return start + (end - start) * min(1.0, index / max(1, episodes - 1))


def replay(table: QTable, buffer, *, sweeps: int, alpha: float, gamma: float, rng) -> int:
    transitions = [tr for episode in buffer for tr in episode]
    for _ in range(sweeps):
        for i in rng.permutation(len(transitions)):
            s, a, reward, k, s2 = transitions[i]
            table.update(s, a, reward, k, s2, alpha, gamma)
    return len(transitions)


# --- where episodes run ------------------------------------------------------------------
@contextmanager
def local_runner(workers: int):
    """Yield run_round(jobs) -> (results in job order, error messages), on spawned local processes."""
    with ProcessPoolExecutor(max_workers=max(1, int(workers)), mp_context=mp.get_context("spawn")) as pool:
        def run_round(jobs):
            futures = [pool.submit(run_episode, job) for job in jobs]
            results, errors = [], []
            for job, future in zip(jobs, futures):
                try:
                    results.append(future.result())
                except Exception as exc:  # one broken episode must not end a long training
                    errors.append(f"seed {job['seed']} ({job['scenario']}): {type(exc).__name__}: {exc}")
            return results, errors

        yield run_round


def episode_runner(backend: str, workers: int):
    if backend == "modal":
        from teamb.experiments.cloud import rl_episode_runner

        return rl_episode_runner(workers)
    return local_runner(workers)


# --- training --------------------------------------------------------------------------------
def _mean(results: list[dict], key: str):
    values = [r[key] for r in results if r.get(key) is not None]
    return round(float(np.mean(values)), 2) if values else None


def _round_record(n_round: int, episodes: int, results: list[dict], errors: list[str], eps: list[float],
                  n_tr: int, table: QTable, wall_s: float) -> dict:
    by_scenario: dict[str, list[dict]] = {}
    for r in results:
        by_scenario.setdefault(r["scenario"], []).append(r)
    return {
        "round": n_round,
        "episodes": episodes,
        "n": len(results),
        "failed": len(errors),
        "epsilon": round(float(np.mean(eps)), 4),
        "reward": _mean(results, "reward"),
        "mean_delay_s": _mean(results, "mean_delay_s"),
        "unfinished": _mean(results, "unfinished"),
        "switches": _mean(results, "switches"),
        "delay_by_scenario": {name: _mean(rs, "mean_delay_s") for name, rs in sorted(by_scenario.items())},
        "replayed": n_tr,
        "visited": int((table.visits.sum(axis=1) > 0).sum()),
        "wall_s": round(wall_s, 1),
    }


def _parse_scenarios(args) -> list[str]:
    from teamb.scenarios import REGISTRY

    names = [s.strip() for s in (args.scenarios or args.scenario).split(",") if s.strip()]
    unknown = [n for n in names if n not in REGISTRY]
    if not names or unknown:
        raise SystemExit(f"unknown scenario(s) {unknown or names}; available: {', '.join(sorted(REGISTRY))}")
    return names


def _parse_demand_range(args) -> tuple[float, float]:
    if not args.demand_range:
        return 1.0 - args.jitter, 1.0 + args.jitter
    try:
        lo, hi = (float(x) for x in args.demand_range.split(","))
    except ValueError:
        raise SystemExit("--demand-range must be 'lo,hi', e.g. 0.75,1.25") from None
    if not 0 < lo <= hi:
        raise SystemExit("--demand-range needs 0 < lo <= hi")
    return lo, hi


def _meta_scenarios(meta: dict) -> list[str]:
    """The scenario pool a model file records (`scenarios`, or the comma-joined `scenario` of older files)."""
    if meta.get("scenarios"):
        return [str(s) for s in meta["scenarios"]]
    return [s for s in str(meta.get("scenario") or "").split(",") if s]


def _prior_sessions(prior: dict) -> list[dict]:
    """Per-invocation records of a resumed file. A file from before `sessions` gets one record built
    from its top-level fields, so a resume does not lose what those earlier episodes were trained on."""
    if "sessions" in prior:
        return [dict(s) for s in prior["sessions"]]
    if not int(prior.get("episodes", 0)):
        return []
    legacy = {"episodes": int(prior["episodes"]), "scenarios": _meta_scenarios(prior)}
    legacy |= {k: prior[k] for k in ("demand_range", "episode_s", "backend", "hyper", "seed_ranges") if k in prior}
    return [legacy | {"note": "earlier sessions, recorded before per-session meta"}]


def train(args, run_round=None) -> QTable:
    """Train and save `args.out`. `run_round(jobs) -> (results, errors)` overrides the backend (tests)."""
    scenarios = _parse_scenarios(args)
    lo, hi = _parse_demand_range(args)
    if args.backend not in BACKENDS:
        raise SystemExit(f"--backend must be one of {BACKENDS}")
    training_seed(args.seed, 0)  # validates --seed
    rng = np.random.default_rng(args.seed)
    if args.resume:
        table = QTable.load(args.out)
        if args.features and FEATURE_SETS[args.features] != table.features:
            raise SystemExit(f"--features {args.features} differs from {args.out} ({table.version}); drop --resume")
        prior = dict(table.meta)
    else:
        table = QTable(features=FEATURE_SETS[args.features or "v1"])
        prior = {}
    # A file without visit_unit "transitions" counted every replay update (or is already "mixed").
    # New transitions are added on top of those counts, so the result must not claim pure transitions.
    mixed_visits = bool(args.resume) and prior.get("visit_unit") != "transitions" and bool(table.visits.any())
    if mixed_visits:
        print(f"note: {args.out} counted replay updates as visits; the resumed counts are labelled "
              f"visit_unit 'mixed' (fallback_min_visits trusts them more than it should; retrain from scratch "
              f"for pure transition counts)", flush=True)
    start_index = int(prior.get("next_episode_index", prior.get("episodes", 0)))
    prior_episodes = int(prior.get("episodes", 0))
    round_size = max(1, int(args.round_size or args.workers))
    buffer: deque = deque(maxlen=max(int(args.buffer), round_size))  # never drop part of the newest round
    resumed_rounds = prior.get("curve_unit") == "round"
    curve: list[dict] = list(prior.get("curve", [])) if resumed_rounds else []
    log = {k: list(v) for k, v in (prior.get("episode_log") or {}).items()} if resumed_rounds else {}
    log = {k: log.get(k, []) for k in LOG_KEYS}
    failed = int(prior.get("failed_episodes", 0))
    wall0 = time.time()
    done = trained = 0  # episodes attempted / completed in this invocation

    def finish_meta() -> None:
        last = training_seed(args.seed, start_index + done - 1) if done else None
        seed_ranges = list(prior.get("seed_ranges", []))
        session = {
            "seed_range": None,
            "episodes": trained,
            "scenarios": scenarios,
            "demand_range": [round(lo, 3), round(hi, 3)],
            "episode_s": args.end if args.end else "full",
            "backend": args.backend,
            "hyper": {k: getattr(args, k) for k in ("alpha", "gamma", "eps_start", "eps_end", "sweeps", "buffer",
                                                     "jitter", "switch_penalty", "coverage", "workers", "seed")}
            | {"round_size": round_size},
        }
        # On --resume the model describes every session, not just this invocation: the scenario pool
        # is the union (RLController.summary() reports it), the demand range the envelope, and the
        # per-invocation settings stay in `sessions`. A session that trained nothing is not recorded.
        sessions = _prior_sessions(prior)
        if last is not None:
            seed_ranges.append([training_seed(args.seed, start_index), last])
            sessions.append(session | {"seed_range": seed_ranges[-1]})
        pool = list(dict.fromkeys([*_meta_scenarios(prior), *(scenarios if last is not None else [])])) or scenarios
        ranges = [s["demand_range"] for s in sessions if s.get("demand_range")] or [session["demand_range"]]
        latest = sessions[-1] if sessions else session
        table.meta = {
            "trained_unix": round(time.time()),
            "episodes": prior_episodes + trained,
            "next_episode_index": start_index + done,
            "failed_episodes": failed,
            "wall_minutes": round(float(prior.get("wall_minutes", 0.0)) + (time.time() - wall0) / 60, 1),
            "scenario": ",".join(pool),
            "scenarios": pool,
            "demand_range": [min(r[0] for r in ranges), max(r[1] for r in ranges)],
            "episode_s": latest.get("episode_s", session["episode_s"]),
            "features": table.version,
            "visit_unit": "mixed" if mixed_visits else "transitions",
            "backend": latest.get("backend", session["backend"]),
            "seed_ranges": seed_ranges,
            "sessions": sessions,
            "held_out": f"training seeds >= {TRAIN_SEED_BASE}; evaluate on seeds below {TRAIN_SEED_BASE}",
            "hyper": latest.get("hyper", session["hyper"]),
            "curve_unit": "round",
            "curve": curve,
            "episode_log": log,
            "note": "tabular Q-learning, shared policy over J1-J4; see teamb/controllers/rl.py",
        }
        if prior and not resumed_rounds and prior.get("curve"):
            table.meta["legacy_curve"] = prior["curve"]  # a file from the old trainer (one record per episode)

    backend = nullcontext(run_round) if run_round is not None else episode_runner(args.backend, args.workers)
    with backend as run_round:
        while done < args.episodes and (time.time() - wall0) / 60 < args.max_minutes:
            n = min(round_size, args.episodes - done)
            table_body = {**table.to_dict(), "meta": {}}  # workers need Q and features, not the curve
            jobs = []
            for i in range(n):
                jobs.append({
                    "scenario": scenarios[0] if len(scenarios) == 1 else str(rng.choice(scenarios)),
                    "seed": training_seed(args.seed, start_index + done + i),
                    "epsilon": epsilon_at(done + i, args.episodes, args.eps_start, args.eps_end),
                    "demand_scale": float(rng.uniform(lo, hi)),
                    "table": table_body,
                    "end": args.end,
                    "coverage": args.coverage,
                    "switch_penalty": args.switch_penalty,
                    "gamma": args.gamma,
                })
            results, errors = run_round(jobs)
            for message in errors:
                print(f"  episode failed: {message}", flush=True)
            if not results:
                raise RuntimeError(f"every episode of a round failed, stopping: {errors[:3]}")
            for r in results:
                transitions = r.pop("transitions")
                table.count_visits(transitions)  # real experience, counted once
                buffer.append(transitions)
                for key in LOG_KEYS:
                    log[key].append(r.get(key))
            n_tr = replay(table, buffer, sweeps=args.sweeps, alpha=args.alpha, gamma=args.gamma, rng=rng)
            done += n
            trained += len(results)
            failed += len(errors)
            record = _round_record(len(curve) + 1, prior_episodes + trained, results, errors,
                                   [j["epsilon"] for j in jobs], n_tr, table, time.time() - wall0)
            curve.append(record)
            mix = Counter(r["scenario"] for r in results)
            print(
                f"episodes {done:4d}/{args.episodes}  eps {record['epsilon']:.3f}  reward {record['reward'] or float('nan'):8.1f}  "
                f"delay {record['mean_delay_s'] or float('nan'):6.1f} s  switches {record['switches'] or float('nan'):5.0f}  "
                f"replayed {n_tr:6d}  visited {record['visited']}/{len(table.q)}  "
                f"{' '.join(f'{k}:{v}' for k, v in sorted(mix.items())) if len(scenarios) > 1 else ''}  "
                f"{time.time() - wall0:5.0f} s",
                flush=True,
            )
            if args.checkpoint_every and len(curve) % args.checkpoint_every == 0 and done < args.episodes:
                finish_meta()
                table.save(args.out)  # atomic: a crash leaves the previous checkpoint
    finish_meta()
    path = table.save(args.out)
    print(f"saved {path}  ({path.stat().st_size / 1024:.0f} KB, {table.meta['episodes']} episodes, "
          f"{table.meta['wall_minutes']} min, features {table.version})")
    return table


def _end(text: str) -> float | None:
    if str(text).lower() in ("full", "0", "none"):
        return None  # each scenario's own duration
    value = float(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("--end must be > 0 seconds or 'full'")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m teamb.controllers.rl_train", description="Train the tabular Q-learning controller")
    p.add_argument("--episodes", type=int, default=60)
    p.add_argument("--workers", type=int, default=2,
                   help="parallel SUMO runs: local processes (keep <= 2 on a laptop) or Modal containers")
    p.add_argument("--round-size", type=int, default=None,
                   help="episodes per learning round, all run with the same table (default: --workers)")
    p.add_argument("--backend", choices=BACKENDS, default="local",
                   help="local worker processes, or modal: one cloud container per episode (pip install modal; modal setup)")
    p.add_argument("--end", type=_end, default=1800.0,
                   help="episode length in simulated seconds, or 'full' for each scenario's own duration")
    p.add_argument("--scenario", default="rush_hour", help="the training scenario (when --scenarios is not given)")
    p.add_argument("--scenarios", default=None, help="comma list; each episode draws one at random, e.g. rush_hour,road_closure")
    p.add_argument("--demand-range", default=None, help="per-episode demand scale U(lo, hi), e.g. 0.75,1.25 (overrides --jitter)")
    p.add_argument("--jitter", type=float, default=0.15, help="demand × U(1-j, 1+j) per episode")
    p.add_argument("--features", choices=sorted(FEATURE_SETS), default=None,
                   help="state features of a new table (default v1; --resume keeps the file's)")
    p.add_argument("--alpha", type=float, default=0.1)
    p.add_argument("--gamma", type=float, default=0.9, help="discount per 5 s decision tick")
    p.add_argument("--eps-start", type=float, default=0.3)
    p.add_argument("--eps-end", type=float, default=0.02)
    p.add_argument("--sweeps", type=int, default=3, help="replay passes over the buffer per round")
    p.add_argument("--buffer", type=int, default=10, help="episodes kept for replay (at least one round)")
    p.add_argument("--switch-penalty", type=float, default=0.2)
    p.add_argument("--coverage", type=float, default=0.05, help="probe share (the RL reads detectors only)")
    p.add_argument("--checkpoint-every", type=int, default=1, help="save --out every N rounds (0 = only at the end)")
    p.add_argument("--max-minutes", type=float, default=15.0, help="stop early after this wall time")
    p.add_argument("--seed", type=int, default=0, help=f"training seeds are 1000 + {SEED_STRIDE}·seed + episode index")
    p.add_argument("--out", type=Path, default=MODEL_PATH)
    p.add_argument("--resume", action="store_true", help="continue from --out instead of an empty table")
    return p


def main(argv=None) -> None:
    train(build_parser().parse_args(argv))


if __name__ == "__main__":
    main()
