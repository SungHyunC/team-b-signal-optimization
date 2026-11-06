"""RL training on Modal (teamb.experiments.cloud.rl_episode_runner) with a fake Modal function.

No network: the Modal app, output and function are replaced, so this checks only the glue
(job order, lost episodes reported instead of raised).
"""
from __future__ import annotations

import contextlib
import types

import pytest

cloud = pytest.importorskip("teamb.experiments.cloud")


class FakeFunction:
    def __init__(self):
        self.options, self.calls = {}, []

    def with_options(self, **options):
        self.options = options
        return self

    def map(self, jobs, order_outputs=True, return_exceptions=False):
        self.calls.append((list(jobs), order_outputs, return_exceptions))
        for job in jobs:
            yield RuntimeError("container lost") if job["seed"] == 1001 else {"seed": job["seed"], "transitions": []}


def test_modal_runner_keeps_job_order_and_reports_lost_episodes(monkeypatch):
    if cloud.modal is None:
        pytest.skip("modal is not installed")
    fake = FakeFunction()
    monkeypatch.setattr(cloud, "rl_episode_remote", fake)
    monkeypatch.setattr(cloud, "app", types.SimpleNamespace(run=contextlib.nullcontext))
    monkeypatch.setattr(cloud.modal, "enable_output", contextlib.nullcontext)
    jobs = [{"seed": 1000 + i, "scenario": "rush_hour"} for i in range(3)]
    with cloud.rl_episode_runner(workers=8) as run_round:
        results, errors = run_round(jobs)
    assert fake.options == {"max_containers": 8}
    assert fake.calls[0][1:] == (True, True), "ordered outputs, exceptions returned not raised"
    assert [r["seed"] for r in results] == [1000, 1002]
    assert len(errors) == 1 and "seed 1001" in errors[0] and "container lost" in errors[0]
