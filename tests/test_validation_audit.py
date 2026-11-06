import json
from pathlib import Path

from teamb.experiments.validation import audit_experiment


def make_run(root: Path, scenario: str, controller: str, seed: int, *, summary=True):
    folder = root / "runs" / f"{scenario}__{controller}__{seed}"
    folder.mkdir(parents=True)
    (folder / "run_spec.json").write_text(json.dumps({"scenario": scenario, "controller": controller, "seed": seed}))
    if summary:
        (folder / "summary.json").write_text(json.dumps({"mean_delay_s": 35.0}))
    (folder / "manifest.json").write_text(json.dumps({"code_revision": "abc123", "sumo_version": "1.20"}))
    return folder


def test_complete_paired_design(tmp_path):
    for seed in range(1, 31):
        for controller in ("fixed_time", "max_pressure"):
            make_run(tmp_path, "rush_hour", controller, seed)
    report = audit_experiment(tmp_path, scenarios=["rush_hour"],
                              controllers=["fixed_time", "max_pressure"], seeds=list(range(1, 31)))
    assert report["complete"]
    assert report["expected_runs"] == report["found_runs"] == 60


def test_missing_and_failed_runs_are_detected(tmp_path):
    make_run(tmp_path, "emergency", "fixed_time", 1)
    make_run(tmp_path, "emergency", "max_pressure", 1, summary=False)
    report = audit_experiment(tmp_path, scenarios=["emergency"],
                              controllers=["fixed_time", "max_pressure"], seeds=[1, 2])
    assert not report["complete"]
    assert len(report["missing_runs"]) == 2
    assert any("missing summary.json" in p for p in report["problems"])


def test_mixed_software_versions_are_detected(tmp_path):
    make_run(tmp_path, "rush_hour", "fixed_time", 1)
    second = make_run(tmp_path, "rush_hour", "max_pressure", 1)
    (second / "manifest.json").write_text(json.dumps({"code_revision": "different", "sumo_version": "1.20"}))
    report = audit_experiment(tmp_path, scenarios=["rush_hour"],
                              controllers=["fixed_time", "max_pressure"], seeds=[1])
    assert not report["complete"]
    assert "mixed code revisions across runs" in report["problems"]


def _spec_run(root: Path, spec, *, sim_time=None):
    from dataclasses import asdict

    folder = root / "runs" / spec.name
    folder.mkdir(parents=True)
    (folder / "run_spec.json").write_text(json.dumps({**asdict(spec), "name": spec.name, "variant": spec.variant}))
    summary = {"mean_delay_s": 35.0}
    if sim_time is not None:
        summary["sim_time_s"] = sim_time
    (folder / "summary.json").write_text(json.dumps(summary))
    (folder / "manifest.json").write_text(json.dumps({"code_revision": "abc123", "sumo_version": "1.20"}))
    return folder


def test_sweeps_and_counterfactual_twins_are_not_duplicates(tmp_path):
    from teamb.experiments.runner import build_matrix

    specs = build_matrix(["emergency"], ["fixed_time", "max_pressure"], [1, 2], [0.1, 1.0],
                         preemption=[True, False], counterfactual=True)
    for spec in specs:
        _spec_run(tmp_path, spec)
    report = audit_experiment(tmp_path, scenarios=["emergency"], controllers=["fixed_time", "max_pressure"], seeds=[1, 2])
    assert report["complete"], report["problems"]
    assert report["found_runs"] == report["expected_runs"] == 4 and not report["duplicates"]


def test_truncated_and_failed_runs_and_unpaired_conditions_are_detected(tmp_path):
    from teamb.experiments.runner import RunSpec

    _spec_run(tmp_path, RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=600.0), sim_time=300.0)
    failed = _spec_run(tmp_path, RunSpec("rush_hour", "max_pressure", 1, 1.0, end_time=600.0), sim_time=600.0)
    (failed / "error.json").write_text(json.dumps({"error": "RuntimeError: boom"}))
    _spec_run(tmp_path, RunSpec("rush_hour", "fixed_time", 2, 1.0, end_time=600.0), sim_time=600.0)
    _spec_run(tmp_path, RunSpec("rush_hour", "max_pressure", 2, 1.0, end_time=600.0), sim_time=600.0)
    _spec_run(tmp_path, RunSpec("rush_hour", "max_pressure", 3, 1.0, end_time=600.0), sim_time=600.0)
    report = audit_experiment(tmp_path, scenarios=["rush_hour"], controllers=["fixed_time", "max_pressure"], seeds=[1, 2, 3])
    text = " ".join(report["problems"])
    assert not report["complete"]
    assert "did not finish" in text and "failed run (RuntimeError: boom)" in text
    assert report["unpaired"] and len(report["missing_runs"]) == 1
