"""Probe estimates against ground truth under biased sampling (scenarios-sensors-9).

approach_biased: arterial drivers run a navigation app twice as often, so queue_est (scaled
by the overall coverage) is biased by approach; queue_est_adj divides by the measured share
on the approach and removes most of it. speed_biased: stopped phones report only 30 % of
the seconds; queue_est_adj does not (and is documented not to) correct that. The fused
queue rests on the detector either way. Two short SUMO runs (about 5 s each)."""
from __future__ import annotations

import pytest

from teamb.sim.env import SimEnv


def _ratios(tmp_path, sampling: str) -> dict:
    env = SimEnv("rush_hour", "fixed_time", seed=1, coverage=0.25, sampling=sampling, end_time=1800, output_dir=tmp_path)
    env.run()
    rows = [r for r in env.sensors.estimation if r[0] >= 600]
    out = {}
    for kind in ("arterial", "cross"):
        sel = [r for r in rows if r[3] == kind]
        truth = sum(r[7] for r in sel)
        out[kind] = {"est": sum(r[12] for r in sel) / truth, "adj": sum(r[13] for r in sel) / truth, "fused": sum(r[15] for r in sel) / truth}
    return out


@pytest.fixture(scope="module")
def approach_biased(tmp_path_factory):
    return _ratios(tmp_path_factory.mktemp("approach_biased"), "approach_biased")


@pytest.fixture(scope="module")
def speed_biased(tmp_path_factory):
    return _ratios(tmp_path_factory.mktemp("speed_biased"), "speed_biased")


def test_queue_est_adj_removes_most_of_the_approach_bias(approach_biased):
    r = approach_biased
    assert r["arterial"]["est"] > 1.2 and r["cross"]["est"] < 0.8  # the bias the research question is about
    for kind in ("arterial", "cross"):
        assert 0.75 <= r[kind]["adj"] <= 1.25, (kind, r[kind])
        assert abs(r[kind]["adj"] - 1) < abs(r[kind]["est"] - 1), (kind, r[kind])
        assert 0.85 <= r[kind]["fused"] <= 1.2, (kind, r[kind])


def test_stopped_phone_bias_is_not_corrected_but_the_fused_queue_is_unaffected(speed_biased):
    for kind, r in speed_biased.items():
        assert 0.2 <= r["adj"] <= 0.45, (kind, r)  # ~ P(report | stopped) = 0.3
        assert 0.85 <= r["fused"] <= 1.2, (kind, r)
