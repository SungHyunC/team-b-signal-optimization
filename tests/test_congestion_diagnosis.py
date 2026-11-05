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
