"""teamb exp screen: the prespecified regression guards, on synthetic run folders (no SUMO)."""
from __future__ import annotations

import json
from dataclasses import asdict

from teamb.experiments.runner import RunSpec
from teamb.experiments.screen import render_markdown, screen

END = 2400.0


def _write(exp, controller, seed, params=None, *, scenario="rush_hour", status="ok", folder=None,
           error="RuntimeError: controller crashed", **metrics):
    """One run folder. status "failed" writes error.json (no summary), "incomplete" a summary
    marked complete: false; `folder` overrides the directory name (e.g. a legacy name)."""
    spec = RunSpec(scenario, controller, seed, 1.0, end_time=END, controller_params=params or {})
    d = exp / "runs" / (folder or spec.name)
    d.mkdir(parents=True)
    (d / "run_spec.json").write_text(json.dumps({**asdict(spec), "name": spec.name, "variant": spec.variant}))
    if status == "failed":
        (d / "error.json").write_text(json.dumps({"error": error}))
        return spec.variant
    summary = {"complete": status != "incomplete", "end_time": END, "sim_time_s": END, "controller_errors": 0,
               "fallback_steps": 0, "rejected_actions": 0, "unfinished_pct": 2.0, "completed": 1000, **metrics}
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


BASE = (30.0, 32.0, 31.0, 29.0, 33.0)


def _pair(exp, seed, scenario="rush_hour", cand_status="ok", base_metrics=None, cand_metrics=None):
    """Baseline max_pressure and candidate max_pressure(rho=0.25) on one seed; returns the candidate variant."""
    base = BASE[(seed - 1) % len(BASE)]
    _write(exp, "max_pressure", seed, scenario=scenario, mean_delay_s=base, **(base_metrics or {}))
    return _write(exp, "max_pressure", seed, {"rho": 0.25}, scenario=scenario, status=cand_status,
                  mean_delay_s=base - 1.0 - 0.1 * seed, **(cand_metrics or {}))


def test_candidate_runs_that_crashed_fail_the_screen(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):
        cand = _pair(exp, seed, cand_status="ok" if seed <= 2 else "failed")
    result = screen(exp, "max_pressure", cand)
    assert result["verdict"] == "FAIL"
    (cond,) = result["conditions"]
    safety = cond["guards"]["safety"]
    assert safety["pass"] is False
    assert sorted(r["seed"] for r in safety["failed_runs"]) == [3, 4, 5]
    assert all(r["status"] == "failed" and "crashed" in r["error"] for r in safety["failed_runs"])
    md = render_markdown(result)
    assert "Failed / incomplete candidate runs" in md and "controller crashed" in md


def test_a_multi_line_run_error_stays_on_its_list_line(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):
        cand = _pair(exp, seed)
    _write(exp, "max_pressure", 6, {"rho": 0.25}, status="failed", error="FatalTraCIError: connection closed\n  by SUMO")
    _write(exp, "max_pressure", 6, mean_delay_s=30.0)
    md = render_markdown(screen(exp, "max_pressure", cand))
    assert "failed: FatalTraCIError: connection closed by SUMO" in md


def test_an_incomplete_candidate_run_fails_the_screen(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):
        cand = _pair(exp, seed, cand_status="incomplete" if seed == 5 else "ok")
    result = screen(exp, "max_pressure", cand)
    assert result["verdict"] == "FAIL"
    assert [r["seed"] for r in result["conditions"][0]["guards"]["safety"]["failed_runs"]] == [5]


def test_a_condition_where_every_candidate_run_failed_is_not_skipped(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):
        cand = _pair(exp, seed)
        _pair(exp, seed, scenario="emergency", cand_status="failed")
    result = screen(exp, "max_pressure", cand)
    assert result["verdict"] == "FAIL"
    by_scenario = {c["scenario"]: c for c in result["conditions"]}
    assert by_scenario["rush_hour"]["pass"] is True
    assert by_scenario["emergency"]["pass"] is False and by_scenario["emergency"]["n_seeds"] == 0
    assert "emergency" in render_markdown(result)


def test_seeds_the_candidate_never_ran_fail_the_screen(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 4):
        cand = _pair(exp, seed)
    for seed in (4, 5):  # the candidate's runs were lost (cloud backend, dead worker): no folder at all
        _write(exp, "max_pressure", seed, mean_delay_s=BASE[seed - 1])
    result = screen(exp, "max_pressure", cand)
    assert result["verdict"] == "FAIL"
    assert result["conditions"][0]["guards"]["safety"]["missing_seeds"] == [4, 5]


def test_a_failed_folder_with_a_finished_rerun_of_the_seed_does_not_count(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):
        cand = _pair(exp, seed)
    _write(exp, "max_pressure", 3, {"rho": 0.25}, status="failed", folder="old_name_of_seed_3")
    assert screen(exp, "max_pressure", cand)["verdict"] == "PASS"


def test_a_condition_with_too_few_paired_seeds_fails_instead_of_disappearing(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):
        cand = _pair(exp, seed)
    _pair(exp, 1, scenario="emergency")
    result = screen(exp, "max_pressure", cand)
    assert result["verdict"] == "FAIL"
    emergency = next(c for c in result["conditions"] if c["scenario"] == "emergency")
    assert emergency["pass"] is False and emergency["guards"]["seeds"] == {"pass": False, "n": 1, "min": 2}
    render_markdown(result)


EV_BASE = {"ev_count": 1, "ev_mean_travel_time_s": 120.0, "ev_unfinished": 0}


def test_a_stranded_emergency_vehicle_fails_the_emergency_guard(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):  # two EVs; the candidate strands one, so the other's faster time is the mean
        cand = _pair(exp, seed, scenario="emergency", base_metrics={**EV_BASE, "ev_count": 2},
                     cand_metrics={"ev_count": 2, "ev_mean_travel_time_s": 100.0, "ev_unfinished": 1})
    result = screen(exp, "max_pressure", cand)
    guard = result["conditions"][0]["guards"]["emergency"]
    assert guard["pass"] is False and guard["more_unfinished_seeds"] == [1, 2, 3, 4, 5]
    assert result["verdict"] == "FAIL"
    assert result["conditions"][0]["metrics"]["ev_unfinished"]["diff"] == 1.0


def test_no_emergency_vehicle_arriving_fails_instead_of_dropping_the_seed(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):
        stranded = seed == 2
        cand = _pair(exp, seed, scenario="emergency", base_metrics=EV_BASE,
                     cand_metrics={"ev_count": 1, "ev_mean_travel_time_s": None if stranded else 118.0,
                                   "ev_unfinished": 1 if stranded else 0})
    guard = screen(exp, "max_pressure", cand)["conditions"][0]["guards"]["emergency"]
    assert guard["pass"] is False and guard["no_ev_arrived_seeds"] == [2]


def test_every_emergency_vehicle_stranded_still_runs_the_guard(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):
        cand = _pair(exp, seed, scenario="emergency", base_metrics=EV_BASE,
                     cand_metrics={"ev_count": 1, "ev_mean_travel_time_s": None, "ev_unfinished": 1})
    result = screen(exp, "max_pressure", cand)
    assert result["conditions"][0]["guards"]["emergency"]["pass"] is False
    assert result["verdict"] == "FAIL"
    assert "| – | 1.00 |" in render_markdown(result)  # no arrived EV to time; one more EV not arrived


def test_faster_emergency_vehicles_that_all_arrive_pass(tmp_path):
    exp = tmp_path / "exp"
    for seed in range(1, 6):
        cand = _pair(exp, seed, scenario="emergency", base_metrics=EV_BASE,
                     cand_metrics={"ev_count": 1, "ev_mean_travel_time_s": 110.0 + seed, "ev_unfinished": 0})
    result = screen(exp, "max_pressure", cand)
    assert result["conditions"][0]["guards"]["emergency"]["pass"] is True
    assert result["verdict"] == "PASS"


def test_screen_of_an_unknown_experiment_writes_nothing(tmp_path, monkeypatch, capsys):
    import teamb.experiments.runner as runner
    from teamb.experiments.screen import main

    monkeypatch.setattr(runner, "EXPERIMENTS_DIR", tmp_path)
    assert main(["--name", "typo_nope", "--baseline", "max_pressure", "--candidate", "x"]) == 2
    assert not (tmp_path / "typo_nope").exists()
    assert "typo_nope" in capsys.readouterr().err
