import json
from dataclasses import asdict

from teamb.experiments.runner import RunSpec
from teamb.experiments.accuracy import audit_specs


def save(root, spec, *, delay=12.0, revision="abc"):
    d = root / "runs" / spec.name
    d.mkdir(parents=True)
    (d / "run_spec.json").write_text(json.dumps(asdict(spec)))
    (d / "summary.json").write_text(json.dumps({"mean_delay_s": delay}))
    (d / "manifest.json").write_text(json.dumps({
        "seed": spec.seed, "code_revision": revision, "sumo_version": "1.20",
        "network_hash": "network-123"}))
    return d


def test_complete_30_seed_paired_matrix(tmp_path):
    specs = [RunSpec("rush_hour", controller, seed, 1.0)
             for seed in range(1, 31) for controller in ("fixed_time", "max_pressure")]
    for spec in specs:
        save(tmp_path, spec)
    result = audit_specs(tmp_path, specs)
    assert result["complete"] and result["valid_runs"] == 60


def test_rejects_non_finite_results_and_missing_runs(tmp_path):
    specs = [RunSpec("rush_hour", "fixed_time", 1, 1.0),
             RunSpec("rush_hour", "max_pressure", 1, 1.0)]
    save(tmp_path, specs[0], delay=float("nan"))
    result = audit_specs(tmp_path, specs)
    assert not result["complete"] and result["valid_runs"] == 0


def test_rejects_different_coverage_even_if_seed_matches(tmp_path):
    expected = RunSpec("emergency", "fixed_time", 1, 1.0)
    actual = RunSpec("emergency", "fixed_time", 1, 0.5)
    save(tmp_path, actual)
    result = audit_specs(tmp_path, [expected])
    assert not result["complete"]


def test_rejects_mixed_code_revisions(tmp_path):
    a = RunSpec("rush_hour", "fixed_time", 1, 1.0)
    b = RunSpec("rush_hour", "max_pressure", 1, 1.0)
    save(tmp_path, a)
    save(tmp_path, b, revision="different")
    assert "mixed code revisions" in " ".join(audit_specs(tmp_path, [a,b])["problems"])
