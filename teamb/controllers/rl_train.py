"""Train the RL controller:  python -m teamb.controllers.rl_train   (defaults = the committed model)

Owner: AI & security (Yunseong).

Batch Q-learning with experience replay (works the same with 1 or several workers):

    table = empty Q-table (or --resume models/rl_qtable.json)
    repeat until --episodes (or --max-minutes) is reached:
        run `--workers` episodes in parallel with the current table, epsilon-greedy:
            rush_hour, a fresh seed (1000+), demand × U(1 − jitter, 1 + jitter)
            → transitions (s, a, R, k, s') from RLController(learn=True)
        keep the last `--buffer` episodes in a replay buffer
        sweep the buffer `--sweeps` times in random order with the Q-learning update
    save models/rl_qtable.json with the training curve (small enough to commit)

Evaluation seeds 1–99 are never used for training, so experiments on them are held out.
Episodes run in TrainEnv (sensors read on decision ticks only, see fast_env.py).

Tunable: --episodes, --workers, --end (episode length), --alpha, --gamma, --eps-start/--eps-end,
--sweeps, --buffer, --jitter, --switch-penalty, --scenario. The defaults (60 episodes ×
1800 s, 2 workers) took 10 minutes here and produced models/rl_qtable.json.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import tempfile
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from teamb.controllers.rl import MODEL_PATH, QTable, RLController

TRAIN_SEED_BASE = 1000  # training seeds start here; evaluation uses small seeds


def run_episode(job: dict) -> dict:
    """One training episode in its own SUMO run (also used by the worker processes)."""
    from teamb.controllers.fast_env import TrainEnv
    from teamb.scenarios import get_scenario

    scenario = get_scenario(job["scenario"], warmup=min(300.0, job["end"] / 2))
    for flow in scenario.flows:
        flow.veh_per_hour *= job["demand_scale"]
    controller = RLController(epsilon=job["epsilon"], learn=True, switch_penalty=job["switch_penalty"], gamma=job["gamma"])
    controller.table = QTable.from_dict(job["table"])
    wall0 = time.time()
    with tempfile.TemporaryDirectory(prefix="teamb_rl_") as tmp:
        env = TrainEnv(scenario, controller, seed=job["seed"], coverage=job["coverage"], end_time=job["end"],
                       output_dir=tmp, observe_every=int(controller.interval))
        summary = env.run()
    return {
        "seed": job["seed"],
        "epsilon": job["epsilon"],
        "demand_scale": round(job["demand_scale"], 3),
        "transitions": controller.transitions,
        "reward": round(controller.episode_reward, 2),
        "mean_delay_s": summary.get("mean_delay_s"),
        "unfinished": summary.get("unfinished"),
        "switches": summary.get("signal_switches"),
        "errors": summary.get("controller_errors", 0) + summary.get("fallback_steps", 0),
        "wall_s": round(time.time() - wall0, 1),
    }


def replay(table: QTable, buffer, *, sweeps: int, alpha: float, gamma: float, rng) -> int:
    transitions = [tr for episode in buffer for tr in episode]
    for _ in range(sweeps):
        for i in rng.permutation(len(transitions)):
            s, a, reward, k, s2 = transitions[i]
            table.update(s, a, reward, k, s2, alpha, gamma)
    return len(transitions)


def train(args) -> QTable:
    rng = np.random.default_rng(args.seed)
    table = QTable.load(args.out) if args.resume else QTable()
    buffer: deque = deque(maxlen=args.buffer)
    curve: list[dict] = []
    wall0 = time.time()
    done = 0
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=ctx) as pool:
        while done < args.episodes and (time.time() - wall0) / 60 < args.max_minutes:
            n = min(args.workers, args.episodes - done)
            frac = done / max(1, args.episodes - 1)
            epsilon = args.eps_start + (args.eps_end - args.eps_start) * frac
            jobs = [
                {
                    "scenario": args.scenario,
                    "seed": TRAIN_SEED_BASE + args.seed * 1000 + done + i,
                    "epsilon": epsilon,
                    "demand_scale": float(rng.uniform(1 - args.jitter, 1 + args.jitter)),
                    "table": table.to_dict(),
                    "end": args.end,
                    "coverage": args.coverage,
                    "switch_penalty": args.switch_penalty,
                    "gamma": args.gamma,
                }
                for i in range(n)
            ]
            results = list(pool.map(run_episode, jobs))
            for r in results:
                buffer.append(r.pop("transitions"))
                curve.append(r)
            n_tr = replay(table, buffer, sweeps=args.sweeps, alpha=args.alpha, gamma=args.gamma, rng=rng)
            done += n
            mean = lambda key: np.mean([r[key] for r in results if r[key] is not None]) if results else float("nan")  # noqa: E731
            print(
                f"episodes {done:3d}/{args.episodes}  eps {epsilon:.3f}  reward {mean('reward'):8.1f}  "
                f"delay {mean('mean_delay_s'):6.1f} s  switches {mean('switches'):5.0f}  replayed {n_tr:6d}  "
                f"visited {int((table.visits.sum(axis=1) > 0).sum())}/{len(table.q)}  {time.time() - wall0:5.0f} s",
                flush=True,
            )
    table.meta = {
        "trained_unix": round(time.time()),
        "episodes": done,
        "wall_minutes": round((time.time() - wall0) / 60, 1),
        "scenario": args.scenario,
        "episode_s": args.end,
        "seeds": [c["seed"] for c in curve],
        "hyper": {k: getattr(args, k) for k in ("alpha", "gamma", "eps_start", "eps_end", "sweeps", "buffer",
                                                 "jitter", "switch_penalty", "coverage", "workers", "seed")},
        "curve": curve,
        "note": "tabular Q-learning, shared policy over J1-J4; see teamb/controllers/rl.py",
    }
    path = table.save(args.out)
    print(f"saved {path}  ({path.stat().st_size / 1024:.0f} KB, {done} episodes, {table.meta['wall_minutes']} min)")
    return table


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m teamb.controllers.rl_train", description="Train the tabular Q-learning controller")
    p.add_argument("--episodes", type=int, default=60)
    p.add_argument("--workers", type=int, default=2, help="parallel SUMO runs (keep ≤ 2 on a laptop)")
    p.add_argument("--end", type=float, default=1800.0, help="episode length in simulated seconds (covers the rush-hour ramp)")
    p.add_argument("--scenario", default="rush_hour")
    p.add_argument("--alpha", type=float, default=0.1)
    p.add_argument("--gamma", type=float, default=0.9, help="discount per 5 s decision tick")
    p.add_argument("--eps-start", type=float, default=0.3)
    p.add_argument("--eps-end", type=float, default=0.02)
    p.add_argument("--sweeps", type=int, default=3, help="replay passes over the buffer per round")
    p.add_argument("--buffer", type=int, default=10, help="episodes kept for replay")
    p.add_argument("--jitter", type=float, default=0.15, help="demand × U(1-j, 1+j) per episode")
    p.add_argument("--switch-penalty", type=float, default=0.2)
    p.add_argument("--coverage", type=float, default=0.05, help="probe share (the RL reads detectors only)")
    p.add_argument("--max-minutes", type=float, default=15.0, help="stop early after this wall time")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=MODEL_PATH)
    p.add_argument("--resume", action="store_true", help="continue from --out instead of an empty table")
    train(p.parse_args(argv))


if __name__ == "__main__":
    main()
