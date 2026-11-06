import json
from teamb.experiments.diagnose import diagnose


def _run(root, controller, seed, delay, unfinished, demand_hash="same"):
    folder = root / "runs" / f"road_closure__{controller}__s{seed}"
    folder.mkdir(parents=True)
    (folder / "run_spec.json").write_text(json.dumps(
        {"scenario": "road_closure", "controller": controller, "seed": seed}
    ))
    (folder / "summary.json").write_text(json.dumps(
        {"mean_delay_s": delay, "unfinished_pct": unfinished, "completed": 100,
         "spillback_by_link": {"J2_J3": 25 if controller == "fixed_time" else 10}}
    ))
    (folder / "manifest.json").write_text(json.dumps(
        {"code_revision": "same", "sumo_version": "1.28", "network_hash": "same",
         "seed": seed, "demand_hash": demand_hash}
    ))


def test_paired_difference_and_spillback(tmp_path):
    for s in range(1, 31):
        _run(tmp_path, "fixed_time", s, 100 + s, 13)
        _run(tmp_path, "max_pressure", s, 96 + s, 8)
    result = diagnose(tmp_path)
    sc = result["scenarios"]["road_closure"]
    assert sc["paired_seeds"] == 30
    assert sc["metrics"]["mean_delay_s"]["candidate_minus_baseline"]["mean"] == -4
    assert sc["metrics"]["unfinished_pct"]["candidate_minus_baseline"]["mean"] == -5
    assert sc["spillback_hotspots"]["fixed_time"][0]["edge"] == "J2_J3"
    assert not sc["warnings"]


def test_unpaired_and_demand_mismatch_are_visible(tmp_path):
    _run(tmp_path, "fixed_time", 1, 100, 10)
    _run(tmp_path, "max_pressure", 1, 95, 8, demand_hash="different")
    _run(tmp_path, "fixed_time", 2, 100, 10)
    sc = diagnose(tmp_path)["scenarios"]["road_closure"]
    assert sc["paired_seeds"] == 1
    assert any("unpaired seeds" in w for w in sc["warnings"])
    assert any("demand_hash" in w for w in sc["warnings"])


def test_ci_uses_exact_student_t_quantiles():
    from teamb.evaluation.stats import t_critical
    from teamb.experiments.diagnose import _ci

    assert _ci([0.0, 1.0])["ci95"] == [-5.853, 6.853]  # t(0.975, 1) = 12.706, se = 0.5
    lo, hi = _ci([0.0, 1.0, 2.0])["ci95"]
    assert abs(lo - (1 - 4.303 / 3 ** 0.5)) < 1e-3 and abs(hi - (1 + 4.303 / 3 ** 0.5)) < 1e-3
    for n in (4, 10, 31, 45):
        vals = [float(i % 7) for i in range(n)]
        r = _ci(vals)
        sd = (sum((v - sum(vals) / n) ** 2 for v in vals) / (n - 1)) ** 0.5
        assert abs((r["ci95"][1] - r["mean"]) - t_critical(n - 1) * sd / n ** 0.5) < 1e-3
    assert _ci([3.0])["ci95"] is None


def _spec_run(root, spec, delay):
    from dataclasses import asdict

    folder = root / "runs" / spec.name
    folder.mkdir(parents=True)
    (folder / "run_spec.json").write_text(json.dumps({**asdict(spec), "name": spec.name, "variant": spec.variant}))
    (folder / "summary.json").write_text(json.dumps({"mean_delay_s": delay, "completed": 100}))
    (folder / "manifest.json").write_text(json.dumps(
        {"code_revision": "same", "sumo_version": "1.28", "network_hash": "same", "seed": spec.seed, "demand_hash": "d"}))


def test_counterfactual_twins_are_a_separate_condition(tmp_path):
    from teamb.experiments.runner import build_matrix

    specs = build_matrix(["emergency"], ["fixed_time", "max_pressure"], [1, 2, 3], [1.0], counterfactual=True)
    for spec in specs:
        twin = bool(spec.scenario_params)
        _spec_run(tmp_path, spec, (10.0 if spec.controller == "fixed_time" else 5.0) if twin
                  else (100.0 if spec.controller == "fixed_time" else 150.0))
    result = diagnose(tmp_path)
    real = result["scenarios"]["emergency"]
    assert real["metrics"]["mean_delay_s"]["baseline_mean"] == 100.0
    assert real["metrics"]["mean_delay_s"]["candidate_mean"] == 150.0 and real["paired_seeds"] == 3
    twin_label = next(k for k in result["scenarios"] if k != "emergency")
    assert twin_label.startswith("emergency-") and result["scenarios"][twin_label]["metrics"]["mean_delay_s"]["candidate_mean"] == 5.0
    assert not any("duplicate" in i for i in result["issues"]) and result["run_count"] == 12


def test_coverage_sweep_pairs_each_coverage_with_the_baseline(tmp_path):
    from teamb.experiments.runner import RunSpec

    for seed in (1, 2, 3):
        _spec_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0), 80.0)
        for cov, delay in ((0.1, 70.0), (0.5, 50.0), (1.0, 40.0)):
            _spec_run(tmp_path, RunSpec("rush_hour", "max_pressure", seed, cov), delay)
    result = diagnose(tmp_path)
    assert set(result["scenarios"]) == {"rush_hour", "rush_hour/c10", "rush_hour/c50"}
    for label, delay in (("rush_hour", 40.0), ("rush_hour/c10", 70.0), ("rush_hour/c50", 50.0)):
        sc = result["scenarios"][label]
        assert sc["paired_seeds"] == 3 and sc["metrics"]["mean_delay_s"]["candidate_mean"] == delay
        assert sc["metrics"]["mean_delay_s"]["baseline_mean"] == 80.0
    assert any("another coverage" in w for w in result["scenarios"]["rush_hour/c10"]["warnings"])
    assert not result["scenarios"]["rush_hour"]["warnings"] and not result["issues"]


def test_cli_baseline_and_candidate_options(tmp_path, capsys):
    from teamb.experiments.diagnose import main
    from teamb.experiments.runner import RunSpec

    for seed in (1, 2):
        _spec_run(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0), 80.0)
        _spec_run(tmp_path, RunSpec("rush_hour", "coordinated", seed, 1.0), 70.0)
    out = tmp_path / "d.json"
    assert main([str(tmp_path), "--candidate", "coordinated", "--output", str(out)]) == 0
    sc = json.loads(out.read_text())["scenarios"]["rush_hour"]
    assert sc["paired_seeds"] == 2 and sc["metrics"]["mean_delay_s"]["candidate_minus_baseline"]["mean"] == -10.0


def test_failed_runs_are_skipped_not_diagnosed(tmp_path):
    _run(tmp_path, "fixed_time", 1, 100, 10)
    _run(tmp_path, "max_pressure", 1, 95, 8)
    (tmp_path / "runs" / "road_closure__max_pressure__s1" / "error.json").write_text(json.dumps({"error": "boom"}))
    result = diagnose(tmp_path)
    assert result["run_count"] == 1 and any("failed run skipped" in i for i in result["issues"])
