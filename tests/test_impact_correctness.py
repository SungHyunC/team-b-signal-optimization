"""Impact & cost-benefit correctness (no SUMO): statistics, pairing, annualization, PERF-01."""
from __future__ import annotations

import pytest

from teamb.analysis import impact
from teamb.evaluation import stats


def test_summary_stat_matches_the_shared_t_interval():
    vals = list(range(40))  # df = 39: the old local table stopped at 30 and used z = 1.96
    s = impact._summary_stat(vals)
    assert s["ci95"] == pytest.approx(stats.mean_ci(vals)["ci95"])
    assert s["ci95"] > 1.96 * stats.mean_ci(vals)["sd"] / 40 ** 0.5
    assert impact._summary_stat([1.0, None, float("nan")]) == {"mean": 1.0, "ci95": None, "n": 1}
    assert impact._summary_stat([]) == {"mean": None, "ci95": None, "n": 0}


def S(**kw):
    """A toy run summary (rush hour, 1-hour window after a 900-s warm-up)."""
    base = dict(scenario="rush_hour", controller="fixed_time", seed=1, coverage=1.0, sampling="uniform",
                ev_preemption=True, sim_time_s=4500.0, completed=3600, unfinished=0, unfinished_pct=0.0,
                mean_delay_s=60.0, stops_per_veh=1.5, ev_mean_travel_time_s=None)
    return {**base, **kw}


# --- incomplete runs and loading (ext-20, ext-16, ext-18) ----------------------------------------
def test_aborted_runs_are_never_priced():
    base = S(sim_time_s=600.0, warmup=900.0, completed=0, unfinished=506, unfinished_pct=100.0,
             mean_delay_s=None, stops_per_veh=None)
    cand = S(controller="max_pressure", sim_time_s=1500.0, completed=390, unfinished=116, unfinished_pct=22.9,
             mean_delay_s=27.2, stops_per_veh=1.0)
    result = impact.analyze([base, cand])
    assert result["rows"] == [] and any("incomplete summary" in n for n in result["notes"])
    # a run that stopped before its configured end is left out with a distinct note
    trunc = S(sim_time_s=1200.0, end_time=1500.0)
    result = impact.analyze([trunc, S(controller="max_pressure", sim_time_s=1500.0, end_time=1500.0, mean_delay_s=50.0)])
    assert result["rows"] == [] and any("incomplete/interrupted run for fixed_time" in n for n in result["notes"])
    result = impact.analyze([S(complete=False), S(controller="max_pressure", mean_delay_s=50.0)])
    assert result["rows"] == [] and any("complete: false" in n for n in result["notes"])


def test_run_folders_with_error_json_or_a_truncated_run_are_left_out(tmp_path):
    import json

    for controller, delay in (("fixed_time", 60.0), ("max_pressure", 50.0)):
        d = tmp_path / "runs" / f"rush_hour__{controller}__s1"
        d.mkdir(parents=True)
        (d / "summary.json").write_text(json.dumps(S(controller=controller, mean_delay_s=delay)))
        (d / "manifest.json").write_text(json.dumps({"config": {"warmup": 900, "end_time": 4500.0}}))
    assert len(impact.analyze(tmp_path)["rows"]) == 1
    (tmp_path / "runs" / "rush_hour__fixed_time__s1" / "error.json").write_text(json.dumps({"error": "RuntimeError: boom"}))
    result = impact.analyze(tmp_path)
    assert result["rows"] == [] and any("boom" in n for n in result["notes"])
    (tmp_path / "runs" / "rush_hour__fixed_time__s1" / "error.json").unlink()
    (tmp_path / "runs" / "rush_hour__fixed_time__s1" / "summary.json").write_text(json.dumps(S(sim_time_s=2411.0)))
    assert impact.analyze(tmp_path)["rows"] == []


def test_explicit_zero_warmup_is_kept():
    run = impact._normalize(S(warmup=0, sim_time_s=3600.0))
    assert run["_warmup"] == 0.0
    q = impact.run_quantities(run, impact.ImpactParams())
    assert q["window_h"] == pytest.approx(1.0)
    assert impact._normalize(S(warmup="0", sim_time_s=3600.0))["_warmup"] == 0.0  # from a CSV


def test_empty_runs_list_in_a_json_file(tmp_path):
    import json

    f = tmp_path / "runs.json"
    f.write_text(json.dumps({"runs": []}))
    result = impact.analyze(f)
    assert result["runs"] == 0 and result["notes"] == []
