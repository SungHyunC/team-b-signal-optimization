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


# --- preemption: others' delay excludes the EVs (evaluation-10) -----------------------------------
def test_others_extra_delay_excludes_the_emergency_vehicles():
    runs = []
    for seed in (1, 2):
        # preemption raises everyone else's delay by 5 s but cuts the EVs' own delay, so the
        # all-vehicle mean falls
        runs.append(S(scenario="emergency", seed=seed, ev_preemption=True, ev_mean_travel_time_s=120.0,
                      mean_delay_s=59.0, others_mean_delay_s=65.0))
        runs.append(S(scenario="emergency", seed=seed, ev_preemption=False, ev_mean_travel_time_s=160.0,
                      mean_delay_s=60.0, others_mean_delay_s=60.0))
    eff = impact.analyze(runs)["preemption"][0]
    assert eff["others_extra_delay_s"]["mean"] == pytest.approx(5.0)
    for r in runs:
        r.pop("others_mean_delay_s")
    assert impact.analyze(runs)["preemption"][0]["others_extra_delay_s"]["mean"] == pytest.approx(-1.0)  # fallback


# --- annual hours: once per scenario (evaluation-4) and EV hours (ext-23) -------------------------
def _variant(params, **kw):
    from teamb.experiments.runner import short_hash

    scen = kw.get("scenario", "rush_hour")
    return S(scenario_variant=f"{scen}-{short_hash(params)}", scenario_params=params, **kw)


def _pairs(make, seeds=(1, 2), base_delay=76.0, cand_delay=32.0, **kw):
    out = []
    for seed in seeds:
        out.append(make(seed=seed, mean_delay_s=base_delay + seed, **kw))
        out.append(make(seed=seed, controller="max_pressure", mean_delay_s=cand_delay + seed, **kw))
    return out


def _annual(result, controller="max_pressure"):
    return next(a for a in result["annual"] if a["controller"] == controller)


def test_counterfactual_twins_are_not_annualized():
    p = impact.ImpactParams()
    plain = _pairs(lambda **k: S(scenario_params={}, **k), scenario="road_closure")
    twins = _pairs(lambda **k: _variant({"events": []}, **k), scenario="road_closure", base_delay=40.0, cand_delay=30.0)
    result = impact.analyze(plain + twins, params=p)
    row = next(r for r in result["rows"] if r["scenario"] == "road_closure")
    twin = next(r for r in result["rows"] if r["scenario"] != "road_closure")
    assert twin["annual_hours"] == 0 and any("counterfactual" in f for f in twin["flags"])
    hours = p.annual_hours["road_closure"]
    assert _annual(result)["annual_benefit_usd"] == pytest.approx(row["stats"]["total_value_usd_per_h"]["mean"] * hours)
    assert _annual(result)["scenarios_used"] == ["road_closure"]
    # from a summary.csv the parameters are unknown: the plain scenario's twin is recognised by name
    from teamb.experiments.runner import short_hash

    unknown = {"scenario_name": "road_closure", "scenario": f"road_closure-{short_hash({'events': []})}", "scenario_params": None}
    assert impact._is_counterfactual(unknown)
    assert not impact._is_counterfactual({**unknown, "scenario": "road_closure-abc123"})
    assert not impact._is_counterfactual({"scenario_name": "rush_hour", "scenario": "rush_hour-x", "scenario_params": {"events": []}})


def test_scenario_variants_count_the_annual_hours_once():
    p = impact.ImpactParams()
    plain = _pairs(lambda **k: S(**k))
    scaled = _pairs(lambda **k: _variant({"demand_scale": 1.2}, **k), base_delay=90.0, cand_delay=40.0)
    result = impact.analyze(plain + scaled, params=p)
    row = next(r for r in result["rows"] if r["scenario"] == "rush_hour")
    var = next(r for r in result["rows"] if r["scenario"] != "rush_hour")
    assert row["annual_hours"] == 500.0 and var["annual_hours"] == 0 and any("variant of rush_hour" in f for f in var["flags"])
    assert _annual(result)["annual_benefit_usd"] == pytest.approx(row["stats"]["total_value_usd_per_h"]["mean"] * 500.0)
    # the only variant (e.g. one --scenario-params experiment) carries the hours
    alone = impact.analyze(scaled, params=p)
    assert alone["rows"][0]["annual_hours"] == 500.0 and _annual(alone)["annual_benefit_usd"] > 0
    # two variants and no plain run: none is counted unless chosen explicitly
    other = _pairs(lambda **k: _variant({"demand_scale": 0.8}, **k), base_delay=50.0, cand_delay=40.0)
    two = impact.analyze(scaled + other, params=p)
    assert all(r["annual_hours"] == 0 for r in two["rows"]) and _annual(two)["annual_benefit_usd"] == 0
    chosen = scaled[0]["scenario_variant"]
    picked = impact.analyze(scaled + other, params={"annual_hours": {chosen: 250}})
    assert {r["scenario"]: r["annual_hours"] for r in picked["rows"]}[chosen] == 250.0


def test_ev_hours_come_from_claimed_emergency_rows_only():
    p = impact.ImpactParams()
    runs = []
    for seed in (1, 2, 3):
        runs.append(S(scenario="emergency", seed=seed, ev_mean_travel_time_s=200.0))
        runs.append(S(scenario="emergency", seed=seed, controller="cand", ev_mean_travel_time_s=180.0))
        runs.append(S(scenario="earthquake", seed=seed, ev_mean_travel_time_s=500.0))
        runs.append(S(scenario="earthquake", seed=seed, controller="cand", ev_mean_travel_time_s=300.0,
                      completed=3200, unfinished=400, unfinished_pct=10.0))
    expected = 20.0 * p.ev_trips_per_year / 3600.0
    assert _annual(impact.analyze(runs, params=p), "cand")["ev_hours_saved_per_year"] == pytest.approx(expected)
    claimed = [dict(r, completed=3600, unfinished=0, unfinished_pct=0.0) for r in runs]
    a = _annual(impact.analyze(claimed, params=p), "cand")
    assert a["ev_hours_saved_per_year"] == pytest.approx(expected) and a["ev_scenarios_used"] == ["emergency"]
    stranding = [dict(r, unfinished=400, unfinished_pct=10.0) if r["controller"] == "cand" and r["scenario"] == "emergency" else r
                 for r in runs]
    assert _annual(impact.analyze(stranding, params=p), "cand")["ev_hours_saved_per_year"] is None


# --- parameter overrides (ext-22, ext-24) ------------------------------------------------------------
@pytest.mark.parametrize("override, message", [
    ({"service_life_years": 0}, "service_life_years"),
    ({"service_life_years": -3}, "service_life_years"),
    ({"service_life_years": 10.9}, "whole number"),
    ({"discount_rate": -1}, "discount_rate"),
    ({"intersections": -1}, "intersections"),
    ({"intersections": float("nan")}, "intersections"),
    ({"intersections": float("inf")}, "intersections"),
    ({"discount_rate": float("inf")}, "discount_rate"),
    ({"service_life_years": float("inf")}, "service_life_years"),
    ({"vehicle_occupancy": float("nan")}, "vehicle_occupancy"),
    ({"annual_hours": {"rush_hour": float("nan")}}, "annual_hours"),
    ({"annual_hours": {"rush_hour": -5}}, "annual_hours"),
])
def test_impossible_overrides_are_rejected(override, message):
    with pytest.raises(ValueError, match=message):
        impact.ImpactParams.with_overrides(override)
    with pytest.raises(ValueError):
        impact.analyze([S(), S(controller="max_pressure", mean_delay_s=50.0)], params=override)


def test_valid_overrides_still_work():
    p = impact.ImpactParams.with_overrides({"service_life_years": 15.0, "discount_rate": 0.0, "intersections": 0})
    assert p.service_life_years == 15 and impact.capital_recovery_factor(0.0, 15) == pytest.approx(1 / 15)
    with pytest.raises(ValueError):
        impact.capital_recovery_factor(0.07, 0)


# --- one dollar year (evaluation-14) ---------------------------------------------------------------
def test_monetary_values_share_one_dollar_year():
    import re

    from teamb.analysis.assumptions import ASSUMPTIONS

    years = {a.name: re.search(r"USD \((\d{4})\)", a.unit).group(1) for a in ASSUMPTIONS if re.search(r"USD \((\d{4})\)", a.unit)}
    assert {n for n, y in years.items() if y != "2023"} == {"co2_usd_per_tonne"}  # converted with the CPI factor
    p = impact.ImpactParams()
    assert p.cpi_2020_to_2023 == pytest.approx(304.702 / 258.811, abs=1e-3)
    base = impact.run_quantities(impact._normalize(S()), p)
    cand = impact.run_quantities(impact._normalize(S(controller="max_pressure", mean_delay_s=50.0)), p)
    eff = impact.pair_effect(base, cand, p)
    assert eff["co2_value_usd_per_h"] == pytest.approx(eff["co2_avoided_kg_per_h"] / 1000 * 190.0 * p.cpi_2020_to_2023)


# --- run end: never pair or merge runs that end at different times (evaluation-2, ext-79) ----------
def _run_folder(root, spec, summary: dict, end: float, *, folder: str | None = None):
    """A run folder as the experiments runner writes it (folder = an older run name, if given)."""
    import json
    from dataclasses import asdict

    d = root / "runs" / (folder or spec.name)
    d.mkdir(parents=True)
    (d / "run_spec.json").write_text(json.dumps({**asdict(spec), "name": folder or spec.name, "variant": spec.variant}))
    (d / "summary.json").write_text(json.dumps(summary))
    (d / "manifest.json").write_text(json.dumps({"config": {"warmup": 900, "end_time": end}}))
    return d


def test_runs_with_another_end_are_neither_merged_nor_paired(tmp_path):
    from teamb.experiments.runner import RunSpec

    for seed in (1, 2):
        _run_folder(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0), S(seed=seed, mean_delay_s=76.0 + seed), 4500.0)
        _run_folder(tmp_path, RunSpec("rush_hour", "max_pressure", seed, 1.0),
                    S(controller="max_pressure", seed=seed, mean_delay_s=31.8 + seed), 4500.0)
        _run_folder(tmp_path, RunSpec("rush_hour", "max_pressure", seed, 1.0, end_time=2700.0),
                    S(controller="max_pressure", seed=seed, sim_time_s=2700.0, mean_delay_s=10.0 + seed), 2700.0)
    result = impact.analyze(tmp_path)
    (row,) = result["rows"]  # the --end 2700 runs have no baseline at 2700: not priced against 4500
    assert row["end_time"] == 4500.0 and row["n"] == 2
    assert row["stats"]["delta_mean_delay_s"]["mean"] == pytest.approx(31.8 - 76.0)
    assert not any("duplicate" in n for n in result["notes"])
    assert any("no fixed_time run to pair with max_pressure" in n and "2700" in n for n in result["notes"])
    for seed in (1, 2):
        _run_folder(tmp_path, RunSpec("rush_hour", "fixed_time", seed, 1.0, end_time=2700.0),
                    S(seed=seed, sim_time_s=2700.0, mean_delay_s=20.0 + seed), 2700.0)
    result = impact.analyze(tmp_path)
    rows = {r["end_time"]: r for r in result["rows"]}
    assert set(rows) == {2700.0, 4500.0} and all(r["n"] == 2 for r in rows.values())
    assert rows[2700.0]["stats"]["delta_mean_delay_s"]["mean"] == pytest.approx(10.0 - 20.0)
    assert rows[4500.0]["stats"]["delta_mean_delay_s"]["mean"] == pytest.approx(31.8 - 76.0)
    # each run end is annualized on its own, never summed into one controller total
    annual = {a["end_time"]: a for a in result["annual"] if a["controller"] == "max_pressure"}
    assert set(annual) == {2700.0, 4500.0}
    for end, a in annual.items():
        assert rows[end]["annual_hours"] == 500.0
        assert a["annual_benefit_usd"] == pytest.approx(rows[end]["stats"]["total_value_usd_per_h"]["mean"] * 500.0)
    assert any("different times" in n for n in result["notes"])
    md = impact.render_markdown(result)
    assert "end 2700 s" in md and "end 4500 s" in md


def test_preemption_pairs_stay_within_one_run_end(tmp_path):
    from teamb.experiments.runner import RunSpec

    for end, (on_tt, off_tt) in ((4500.0, (120.0, 160.0)), (2700.0, (100.0, 110.0))):
        for seed in (1, 2):
            for pre, tt in ((True, on_tt), (False, off_tt)):
                spec = RunSpec("emergency", "fixed_time", seed, 1.0, ev_preemption=pre, end_time=None if end == 4500.0 else end)
                _run_folder(tmp_path, spec, S(scenario="emergency", seed=seed, ev_preemption=pre, sim_time_s=end,
                                              ev_mean_travel_time_s=tt), end)
    eff = {e["end_time"]: e for e in impact.analyze(tmp_path)["preemption"]}
    assert set(eff) == {2700.0, 4500.0} and all(e["n"] == 2 for e in eff.values())
    assert eff[4500.0]["ev_time_saved_s"]["mean"] == pytest.approx(40.0)
    assert eff[2700.0]["ev_time_saved_s"]["mean"] == pytest.approx(10.0)


def test_a_duplicate_run_folder_prefers_the_current_run_name(tmp_path):
    from teamb.experiments.runner import RunSpec

    for controller, delay, old in (("fixed_time", 70.0, 75.0), ("max_pressure", 30.0, 25.0)):
        spec = RunSpec("rush_hour", controller, 1, 0.125)
        _run_folder(tmp_path, spec, S(controller=controller, coverage=0.125, mean_delay_s=delay), 4500.0)
        # the same run under the old name (coverage rounded to c12), from older code: sorts after c12.5
        _run_folder(tmp_path, spec, S(controller=controller, coverage=0.125, mean_delay_s=old), 4500.0,
                    folder=f"rush_hour__{controller}__s1__c12__uniform")
    result = impact.analyze(tmp_path)
    (row,) = result["rows"]
    assert row["stats"]["delta_mean_delay_s"]["mean"] == pytest.approx(30.0 - 70.0)
    assert any("duplicate" in n and "c12__uniform" in n for n in result["notes"])
