"""teamb exp screen: the prespecified regression guards, on synthetic run folders (no SUMO)."""
from __future__ import annotations

import json
from dataclasses import asdict

from teamb.experiments.runner import RunSpec
from teamb.experiments.screen import render_markdown, screen

END = 2400.0


def _write(exp, controller, seed, params=None, **metrics):
    spec = RunSpec("rush_hour", controller, seed, 1.0, end_time=END, controller_params=params or {})
    d = exp / "runs" / spec.name
    d.mkdir(parents=True)
    (d / "run_spec.json").write_text(json.dumps({**asdict(spec), "name": spec.name, "variant": spec.variant}))
    summary = {"complete": True, "end_time": END, "sim_time_s": END, "controller_errors": 0, "fallback_steps": 0,
               "rejected_actions": 0, "unfinished_pct": 2.0, "completed": 1000, **metrics}
    (d / "summary.json").write_text(json.dumps(summary))
    return spec.variant


def _experiment(tmp_path, cand_delay, cand_unfinished=2.0, errors=0):
    exp = tmp_path / "exp"
    variant = None
    for seed, base in enumerate((30.0, 32.0, 31.0, 29.0, 33.0), start=1):
        _write(exp, "max_pressure", seed, mean_delay_s=base)
        variant = _write(exp, "max_pressure", seed, {"rho": 0.25}, mean_delay_s=base + cand_delay(seed),
                         unfinished_pct=cand_unfinished + 0.01 * seed, controller_errors=errors)
    return exp, variant


def test_small_improvement_passes(tmp_path):
    exp, cand = _experiment(tmp_path, lambda s: -1.0 - 0.1 * s)
    result = screen(exp, "max_pressure", cand)
    assert result["verdict"] == "PASS"
    (cond,) = result["conditions"]
    assert cond["n_seeds"] == 5 and "mean_delay_s" in cond["significant_benefits"]
    assert "PASS" in render_markdown(result)


def test_delay_regression_above_five_percent_fails(tmp_path):
    exp, cand = _experiment(tmp_path, lambda s: 2.0 + 0.1 * s)  # about +7 %
    result = screen(exp, "max_pressure", cand)
    assert result["verdict"] == "FAIL"
    assert result["conditions"][0]["guards"]["delay"]["pass"] is False


def test_fewer_unfinished_trips_is_not_a_regression_but_more_is(tmp_path):
    exp, cand = _experiment(tmp_path, lambda s: -0.5, cand_unfinished=3.5)  # +1.5 pp, every seed
    result = screen(exp, "max_pressure", cand)
    assert result["conditions"][0]["guards"]["throughput"]["pass"] is False
    assert result["verdict"] == "FAIL"


def test_any_controller_error_fails_the_safety_guard(tmp_path):
    exp, cand = _experiment(tmp_path, lambda s: -1.0, errors=1)
    result = screen(exp, "max_pressure", cand)
    assert result["conditions"][0]["guards"]["safety"]["pass"] is False


def test_no_paired_data_is_reported_as_such(tmp_path):
    exp, _ = _experiment(tmp_path, lambda s: 0.0)
    assert screen(exp, "max_pressure", "does_not_exist")["verdict"] == "NO DATA"


def test_a_significant_but_negligible_unfinished_increase_passes(tmp_path):
    exp, cand = _experiment(tmp_path, lambda s: -1.0, cand_unfinished=2.0)  # +0.01..0.05 pp, every seed
    assert screen(exp, "max_pressure", cand)["conditions"][0]["guards"]["throughput"]["pass"] is True
