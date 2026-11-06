"""Experiment report pairing on synthetic run folders (no SUMO): run end, preemption, header,
counterfactual twins (ext-79, ext-83, evaluation-2, evaluation-8, evaluation-12)."""
from __future__ import annotations

import json

import pytest
from dataclasses import asdict

from teamb.evaluation.stats import mean_ci
from teamb.experiments.analysis import build_report, load_runs, render_markdown
from teamb.experiments.runner import RunSpec


def make_run(root, spec: RunSpec, delay: float, *, sim_time=None, manifest_end=None, folder=None, **summary):
    """A finished run folder; folder = the name an older runner gave it (default: spec.name)."""
    name = folder or spec.name
    d = root / "runs" / name
    d.mkdir(parents=True)
    (d / "run_spec.json").write_text(json.dumps({**asdict(spec), "name": name, "variant": spec.variant}))
    sim = sim_time if sim_time is not None else (spec.end_time or manifest_end)
    body = {"mean_delay_s": delay, "completed": 100, "unfinished": 0, "unfinished_pct": 0.0, **summary}
    if sim is not None:
        body["sim_time_s"] = sim
    (d / "summary.json").write_text(json.dumps(body))
    if manifest_end is not None:
        (d / "manifest.json").write_text(json.dumps({"config": {"end_time": manifest_end, "warmup": 900.0}}))
    return d


def rows_by(report, **match):
    return [r for r in report["rows"] if all(r.get(k) == v for k, v in match.items())]


def test_runs_with_another_end_time_are_never_paired(tmp_path):
    for seed in (1, 2, 3):
        make_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0, end_time=1500.0), 60.0 + seed)
        make_run(tmp_path, RunSpec("rush_hour", "max_pressure", seed, 1.0, end_time=3600.0), 40.0 + seed)
    report = build_report(tmp_path)
    mp = rows_by(report, controller="max_pressure")[0]
    assert mp["baseline_match"] is None and mp["delta_vs_baseline_pct"]["mean"] is None and mp["n_paired"] == 0
    assert mp["end_time"] == 3600.0 and report["warnings"]
    assert "end s" in render_markdown(report) and "**Warning:**" in render_markdown(report)
    for seed in (1, 2, 3):
        make_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0, end_time=3600.0), 50.0 + seed)
    report = build_report(tmp_path)
    mp = rows_by(report, controller="max_pressure")[0]
    assert mp["baseline_match"] == "exact" and mp["n_paired"] == 3
    assert mp["delta_vs_baseline_pct"]["mean"] is not None and mp["mean_delay_diff_s"]["mean"] == -10.0
    assert sorted(r["end_time"] for r in rows_by(report, controller="fixed_time")) == [1500.0, 3600.0]


def test_default_end_time_comes_from_the_manifest_and_groups_with_an_explicit_end(tmp_path):
    for seed in (1, 2):
        make_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0), 60.0, manifest_end=3600.0)
        make_run(tmp_path, RunSpec("rush_hour", "coordinated", seed, 1.0, end_time=3600.0), 50.0)
    runs = load_runs(tmp_path)
    assert {r["end_time"] for r in runs} == {3600.0}
    report = build_report(tmp_path)
    coord = rows_by(report, controller="coordinated")[0]
    assert coord["baseline_match"] == "exact" and coord["n_paired"] == 2
    assert "run end 3600 s" in render_markdown(report)


def test_unknown_end_time_sorts_without_crashing(tmp_path):
    make_run(tmp_path, RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=1500.0), 60.0)
    d = make_run(tmp_path, RunSpec("rush_hour", "fixed_time", 2, 1.0), 61.0)  # no sim_time_s, no manifest
    assert load_runs(tmp_path)[1]["end_time"] is None and d.exists()
    report = build_report(tmp_path)
    assert [r["end_time"] for r in report["rows"]] == [1500.0, None]
    render_markdown(report)


def test_baseline_is_never_taken_from_another_preemption_setting(tmp_path):
    for seed in (1, 2, 3):
        make_run(tmp_path, RunSpec("emergency", "fixed_time", seed, 1.0, ev_preemption=True, end_time=900.0), 60.0)
        for pre in (True, False):
            make_run(tmp_path, RunSpec("emergency", "coordinated", seed, 1.0, ev_preemption=pre, end_time=900.0), 50.0 - seed)
    report = build_report(tmp_path)
    on = rows_by(report, controller="coordinated", ev_preemption=True)[0]
    off = rows_by(report, controller="coordinated", ev_preemption=False)[0]
    assert on["baseline_match"] == "exact"
    assert off["baseline_match"] is None and off["delta_vs_baseline_pct"]["mean"] is None
    assert off.get("p_holm") is None


def test_counterfactual_twin_must_have_the_same_run_end(tmp_path):
    for seed in (1, 2):
        make_run(tmp_path, RunSpec("road_closure", "fixed_time", seed, 1.0, end_time=1500.0), 90.0, disruptions=1)
        make_run(tmp_path, RunSpec("road_closure", "fixed_time", seed, 1.0, end_time=3600.0,
                                   scenario_params={"events": []}), 60.0)
    rec = build_report(tmp_path)["recovery"]
    assert len(rec) == 1 and "vs_no_event" not in rec[0]
    for seed in (1, 2):
        make_run(tmp_path, RunSpec("road_closure", "fixed_time", seed, 1.0, end_time=1500.0,
                                   scenario_params={"events": []}), 60.0)
    rec = build_report(tmp_path)["recovery"]
    assert "vs_no_event" in rec[0]


def _series(d, rates):
    with open(d / "timeseries.csv", "w") as fh:
        fh.write("t,delay_rate\n")
        for t, r in rates:
            fh.write(f"{t},{r}\n")


def test_vs_no_event_counts_seeds_not_windows(tmp_path):
    times = [float(t) for t in range(1, 4500, 5)]
    for seed in (1, 2):
        run = make_run(tmp_path, RunSpec("earthquake", "fixed_time", seed, 1.0, end_time=4500.0), 200.0, disruptions=2)
        # an older evaluation.json: two overlapping windows kept apart
        (run / "evaluation.json").write_text(json.dumps({"recovery": [
            {"kind": "closure", "what": "J1_N1+N1_J1", "start": 1200.0, "end": 3600.0},
            {"kind": "closure", "what": "J3_J4+J4_J3", "start": 1200.0, "end": 3000.0},
        ]}))
        _series(run, [(t, 30.0 if 1200 <= t < 3600 else 10.0) for t in times])
        twin = make_run(tmp_path, RunSpec("earthquake", "fixed_time", seed, 1.0, end_time=4500.0,
                                          scenario_params={"events": []}), 80.0)
        _series(twin, [(t, 10.0) for t in times])
    rec = build_report(tmp_path)["recovery"][0]["vs_no_event"]
    assert rec["n"] == 2 and rec["censored"] == 0
    assert rec["excess_veh_h"]["mean"] == pytest.approx(20 * 2400 / 3600, rel=0.01)  # once, not twice
    assert len(rec["per_seed"]) == 2


def test_report_shows_depart_delay(tmp_path):
    for seed in (1, 2):
        make_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0, end_time=900.0), 60.0,
                 mean_depart_delay_s=30.0, mean_delay_incl_depart_s=95.0)
    report = build_report(tmp_path)
    assert report["perf01"][0]["mean_depart_delay_s"]["mean"] == 30.0
    assert report["rows"][0]["metrics"]["mean_delay_incl_depart_s"]["mean"] == 95.0
    md = render_markdown(report)
    assert "depart delay s" in md and "(lower bound)" in md
    assert "mean_delay_incl_depart_s" in report["definitions"]


def _legacy_name(spec: RunSpec) -> str:
    """The run name before evaluation-2/ext-89: no end time, coverage rounded to whole percent."""
    pre = "" if spec.ev_preemption else "__nopre"
    return f"{spec.scenario_variant}__{spec.variant}__s{spec.seed}__c{round(spec.coverage * 100)}__{spec.sampling}{pre}"


def test_a_legacy_folder_and_its_rerun_count_once(tmp_path):
    # an experiment made with --end 2700 before the run end was in the name, re-run with the same command
    new = {"fixed_time": (61.0, 66.0, 74.0), "max_pressure": (30.0, 33.0, 38.0)}
    for controller, delays in new.items():
        for seed, delay in zip((1, 2, 3), delays):
            spec = RunSpec("rush_hour", controller, seed, 1.0, end_time=2700.0)
            make_run(tmp_path, spec, delay + 20.0, folder=_legacy_name(spec), est_samples=10, est_queue_mae=1.0)
            make_run(tmp_path, spec, delay, est_samples=10, est_queue_mae=1.0)
    report = build_report(tmp_path)
    ft = rows_by(report, controller="fixed_time")[0]
    mp = rows_by(report, controller="max_pressure")[0]
    assert ft["n_seeds"] == 3 and ft["seeds"] == [1, 2, 3] and mp["n_paired"] == 3
    expected = mean_ci(new["fixed_time"])
    assert ft["mean_delay_s"] == {"mean": round(expected["mean"], 3), "ci95": round(expected["ci95"], 3)}
    assert mp["mean_delay_diff_s"]["mean"] == pytest.approx(-100.0 / 3, abs=1e-3)  # the re-run values, not the old ones
    assert report["estimation"][0]["n_runs"] == 6
    dups = report["duplicate_runs"]
    assert len(dups) == 6 and all(d["kept"].endswith("__e2700") and not d["name"].endswith("__e2700") for d in dups)
    assert any("6 run folders" in w for w in report["warnings"])
    md = render_markdown(report)
    assert "## Duplicate run folders" in md and _legacy_name(RunSpec("rush_hour", "fixed_time", 1, 1.0)) in md


def test_a_default_run_and_an_explicit_end_of_the_same_length_count_once(tmp_path):
    for seed in (1, 2):
        make_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0), 60.0 + seed, manifest_end=4500.0)
        make_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0, end_time=4500.0), 60.0 + seed, manifest_end=4500.0)
        make_run(tmp_path, RunSpec("rush_hour", "max_pressure", seed, 1.0), 30.0 + seed, manifest_end=4500.0)
    report = build_report(tmp_path)
    ft = rows_by(report, controller="fixed_time")[0]
    assert ft["n_seeds"] == 2 and rows_by(report, controller="max_pressure")[0]["n_paired"] == 2
    assert [d["kept"] for d in report["duplicate_runs"]] == [RunSpec("rush_hour", "fixed_time", s, 1.0).name for s in (1, 2)]
    assert report["compute"]["runs_ok"] == 6 and report["compute"]["runs_duplicate"] == 2


def test_scenarios_with_their_own_durations_raise_no_end_warning(tmp_path):
    # default runs end at each scenario's duration (road_closure 5400 s, rush_hour 4500 s): within
    # every scenario all runs end together, so there is nothing to warn about and no end column
    for scenario, end in (("rush_hour", 4500.0), ("road_closure", 5400.0)):
        for controller, delay in (("fixed_time", 60.0), ("max_pressure", 45.0)):
            for seed in (1, 2, 3):
                make_run(tmp_path, RunSpec(scenario, controller, seed, 1.0), delay + seed, manifest_end=end)
    report = build_report(tmp_path)
    assert report["matrix"]["end_time"] == [4500.0, 5400.0]
    assert report["warnings"] == []
    md = render_markdown(report)
    assert "end s" not in md and "**Warning:**" not in md and "run end 4500, 5400 s" in md
    # one scenario at two ends still warns, names that scenario, and gets the column
    for seed in (1, 2, 3):
        make_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0, end_time=2700.0), 50.0 + seed)
    report = build_report(tmp_path)
    (warning,) = report["warnings"]
    assert "rush_hour: 2700 s, 4500 s" in warning and "road_closure" not in warning
    md = render_markdown(report)
    closure, rush = md.split("## Scenario `road_closure`")[1].split("## Scenario `rush_hour`")
    assert "| controller | end s |" in rush.split("##")[0] and "end s" not in closure


def test_side_tables_say_which_run_end_each_row_is(tmp_path):
    extra = {"ev_count": 2, "ev_mean_travel_time_s": 100.0, "disruptions": 1, "recovery_time_s": 60.0,
             "attacks": 1, "attack_detected": True}
    for end in (1500.0, 3600.0):
        for seed in (1, 2):
            make_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0, end_time=end), 60.0 + seed, **extra)
            for cov in (1.0, 0.5):
                make_run(tmp_path, RunSpec("rush_hour", "max_pressure", seed, cov, end_time=end), 40.0 + seed, **extra)
    report = build_report(tmp_path)
    for table in ("coverage_sweep", "emergency", "security", "recovery", "perf01"):
        assert report[table] and {r["end_time"] for r in report[table]} == {1500.0, 3600.0}, table
    md = render_markdown(report)
    assert md.count("| scenario | controller | end s |") == 5  # sweep, emergency, attack, recovery, PERF-01
    assert "| rush_hour | max_pressure | 1500 | 0.5 |" in md and "| rush_hour | max_pressure | 3600 | 0.5 |" in md
