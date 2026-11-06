"""Experiment report pairing on synthetic run folders (no SUMO): run end, preemption, header,
counterfactual twins (ext-79, ext-83, evaluation-2, evaluation-8, evaluation-12)."""
from __future__ import annotations

import json
from dataclasses import asdict

from teamb.experiments.analysis import build_report, load_runs, render_markdown
from teamb.experiments.runner import RunSpec


def make_run(root, spec: RunSpec, delay: float, *, sim_time=None, manifest_end=None, **summary):
    d = root / "runs" / spec.name
    d.mkdir(parents=True)
    (d / "run_spec.json").write_text(json.dumps({**asdict(spec), "name": spec.name, "variant": spec.variant}))
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
