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


# --- what a run's delay is (evaluation-6, evaluation-5) ------------------------------------------
def _seed1_pair(**cand_kw):
    base = S(completed=3235, unfinished=118, unfinished_pct=3.52, in_network_at_end=118, never_inserted=0, teleports=0,
             mean_delay_s=76.0, mean_delay_incl_unfinished_s=75.18, inserted_in_window=3353, mean_depart_delay_s=0.0)
    cand = S(controller="max_pressure", completed=3274, unfinished=79, unfinished_pct=2.36, in_network_at_end=79,
             never_inserted=0, teleports=0, mean_delay_s=31.8, mean_delay_incl_unfinished_s=31.37,
             inserted_in_window=3353, mean_depart_delay_s=0.0, **cand_kw)
    return base, cand


def test_in_flight_trips_are_charged_their_accrued_delay_not_300_s():
    base, cand = _seed1_pair()
    p = impact.ImpactParams()
    saved = impact.pair_effect(impact.run_quantities(impact._normalize(base), p),
                               impact.run_quantities(impact._normalize(cand), p), p)["delay_saved_veh_h_per_h"]
    accrued = (75.18 - 31.37) * 3353 / 3600
    assert saved == pytest.approx(accrued, abs=0.01)  # about 40.8, not + (118 - 79) * 300 / 3600 = 3.25 more
    assert abs(saved - 40.8) < 1.0
    # stranded trips (never inserted or teleported) still pay the flat penalty
    stranded = dict(cand, never_inserted=40, teleports=10)
    q = impact.run_quantities(impact._normalize(stranded), p)
    q0 = impact.run_quantities(impact._normalize(cand), p)
    assert q["delay_veh_h_per_h"] - q0["delay_veh_h_per_h"] == pytest.approx(50 * 300 / 3600)


def test_entry_waits_count_as_delay():
    base, cand = _seed1_pair()
    base = dict(base, mean_delay_incl_unfinished_s=31.37, mean_depart_delay_s=30.0)  # same timeLoss, more waiting
    p = impact.ImpactParams()
    eff = impact.pair_effect(impact.run_quantities(impact._normalize(base), p),
                             impact.run_quantities(impact._normalize(cand), p), p)
    assert eff["delay_saved_veh_h_per_h"] == pytest.approx(30.0 * 3353 / 3600)


def test_summaries_without_the_perf01_detail_use_the_old_formula_and_are_flagged_when_mixed():
    p = impact.ImpactParams()
    q = impact.run_quantities(impact._normalize(S(unfinished=100)), p)
    assert q["delay_method"] == "completed+penalty"
    assert q["delay_veh_h_per_h"] == pytest.approx((60.0 * 3600 + 100 * 300) / 3600)
    base, cand = _seed1_pair()
    legacy = {k: v for k, v in base.items() if k not in ("inserted_in_window", "never_inserted", "mean_delay_incl_unfinished_s")}
    row = impact.analyze([legacy, cand])["rows"][0]
    assert any("different formulas" in f for f in row["flags"])
