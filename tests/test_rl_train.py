"""RL training loop (teamb.controllers.rl_train) with a fake episode runner, plus one short real episode.

The fake runner stands in for the local process pool / Modal containers, so these tests check
the bookkeeping (seeds, scenario and demand sampling, epsilon, visits, checkpoints, resume)
without SUMO. One test runs a real 200 s TrainEnv episode.
"""
from __future__ import annotations

import pytest

from teamb.controllers.rl import QTable, encode_state
from teamb.controllers.rl_train import TRAIN_SEED_BASE, build_parser, episode_runner, run_episode, train, training_seed


class FakeRunner:
    """Answers every job with two synthetic transitions; records the jobs it saw."""

    def __init__(self, out=None, fail_seeds=()):
        self.rounds: list[list[dict]] = []
        self.out, self.fail_seeds = out, set(fail_seeds)
        self.checkpoints: list[int] = []

    def __call__(self, jobs):
        if self.out is not None and self.out.exists():
            self.checkpoints.append(QTable.load(self.out).meta["episodes"])
        self.rounds.append(jobs)
        results, errors = [], []
        for job in jobs:
            if job["seed"] in self.fail_seeds:
                errors.append(f"seed {job['seed']}: boom")
                continue
            s = encode_state("EW", 9, 2, 20, job["seed"] % 2 == 0, job["table"]["features"])
            results.append({
                "scenario": job["scenario"], "seed": job["seed"], "epsilon": job["epsilon"],
                "demand_scale": job["demand_scale"], "end": job["end"],
                "transitions": [(s, 1, -0.5, 2, s), (s, 0, -0.3, 1, s)],
                "reward": -10.0, "mean_delay_s": 30.0 + job["seed"] % 7, "unfinished": 3, "switches": 40,
                "errors": 0, "wall_s": 0.1,
            })
        return results, errors

    @property
    def jobs(self):
        return [j for r in self.rounds for j in r]


def args_for(tmp_path, *extra):
    return build_parser().parse_args(["--out", str(tmp_path / "model.json"), *extra])


def test_training_round_bookkeeping(tmp_path):
    out = tmp_path / "model.json"
    fake = FakeRunner(out)
    args = args_for(tmp_path, "--episodes", "5", "--workers", "2", "--scenarios", "rush_hour,road_closure",
                    "--demand-range", "0.8,1.2", "--features", "v2", "--sweeps", "3")
    table = train(args, run_round=fake)

    assert [len(r) for r in fake.rounds] == [2, 2, 1]
    seeds = [j["seed"] for j in fake.jobs]
    assert seeds == list(range(TRAIN_SEED_BASE, TRAIN_SEED_BASE + 5)), "held-out: training seeds start at 1000"
    assert {j["scenario"] for j in fake.jobs} <= {"rush_hour", "road_closure"}
    assert all(0.8 <= j["demand_scale"] <= 1.2 for j in fake.jobs)
    assert fake.jobs[0]["epsilon"] == pytest.approx(0.3) and fake.jobs[-1]["epsilon"] == pytest.approx(0.02)
    assert all(j["table"]["meta"] == {} for j in fake.jobs), "workers get Q-values, not the training curve"
    assert fake.checkpoints == [2, 4], "a checkpoint after every round, loadable at any time"

    assert table.visits.sum() == 10, "two transitions per episode, counted once despite 3 replay sweeps"
    saved = QTable.load(out)
    meta = saved.meta
    assert saved.version == "v2" and meta["features"] == "v2" and meta["visit_unit"] == "transitions"
    assert meta["episodes"] == 5 and meta["next_episode_index"] == 5 and meta["failed_episodes"] == 0
    assert meta["scenarios"] == ["rush_hour", "road_closure"] and meta["demand_range"] == [0.8, 1.2]
    assert meta["seed_ranges"] == [[1000, 1004]] and meta["episode_s"] == 1800.0
    assert meta["curve_unit"] == "round" and [c["episodes"] for c in meta["curve"]] == [2, 4, 5]
    assert set(meta["curve"][0]["delay_by_scenario"]) <= {"rush_hour", "road_closure"}
    assert meta["episode_log"]["seed"] == seeds and len(meta["episode_log"]["scenario"]) == 5


def test_resume_continues_seeds_curve_and_counts(tmp_path):
    train(args_for(tmp_path, "--episodes", "3", "--workers", "3"), run_round=FakeRunner())
    fake = FakeRunner()
    table = train(args_for(tmp_path, "--episodes", "2", "--workers", "2", "--resume"), run_round=fake)
    assert [j["seed"] for j in fake.jobs] == [1003, 1004], "no seed is trained on twice"
    meta = table.meta
    assert meta["episodes"] == 5 and meta["seed_ranges"] == [[1000, 1002], [1003, 1004]]
    assert [c["round"] for c in meta["curve"]] == [1, 2] and len(meta["episode_log"]["seed"]) == 5
    assert table.visits.sum() == 10
    with pytest.raises(SystemExit, match="features"):
        train(args_for(tmp_path, "--episodes", "1", "--resume", "--features", "v2"), run_round=FakeRunner())


def test_failed_episodes_are_counted_not_fatal_unless_a_whole_round_fails(tmp_path):
    table = train(args_for(tmp_path, "--episodes", "4", "--workers", "2"), run_round=FakeRunner(fail_seeds={1001}))
    assert table.meta["episodes"] == 3 and table.meta["failed_episodes"] == 1 and table.meta["next_episode_index"] == 4
    with pytest.raises(RuntimeError, match="every episode"):
        train(args_for(tmp_path, "--episodes", "2", "--workers", "2"), run_round=FakeRunner(fail_seeds={1000, 1001}))


def test_training_seeds_stay_held_out_and_valid():
    assert training_seed(0, 0) == 1000 and training_seed(1, 5) == 1_001_005
    assert training_seed(1999, 10**6 - 1) < 2**31
    for bad in ((-1, 0), (2000, 0), (0, -1)):
        with pytest.raises(ValueError):
            training_seed(*bad)


def test_cli_parses_scaling_flags(tmp_path):
    args = args_for(tmp_path, "--end", "full", "--backend", "modal", "--workers", "64", "--round-size", "128")
    assert args.end is None and args.backend == "modal" and args.round_size == 128
    with pytest.raises(SystemExit):
        train(args_for(tmp_path, "--scenarios", "rush_hour,nowhere"), run_round=FakeRunner())
    with pytest.raises(SystemExit):
        train(args_for(tmp_path, "--demand-range", "1.2,0.8"), run_round=FakeRunner())
    assert hasattr(episode_runner("local", 1), "__enter__")


def test_run_episode_returns_transitions_from_a_real_short_episode():
    job = {"scenario": "rush_hour", "seed": training_seed(0, 0), "epsilon": 0.3, "demand_scale": 1.0,
           "table": {**QTable().to_dict(), "meta": {}}, "end": 200.0, "coverage": 0.05,
           "switch_penalty": 0.2, "gamma": 0.9}
    result = run_episode(job)
    assert result["scenario"] == "rush_hour" and result["end"] == 200.0 and result["errors"] == 0
    assert result["transitions"], "decisions every 5 s produce transitions"
    s, a, reward, k, s2 = result["transitions"][0]
    assert 0 <= s < 288 and a in (0, 1) and k >= 1 and reward <= 0
