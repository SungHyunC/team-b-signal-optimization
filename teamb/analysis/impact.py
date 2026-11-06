"""Impact & cost-benefit analysis: what a better signal controller is worth.

Owner: Scenarios & analysis (Aditya, with Doyoung).

    python -m teamb.analysis.impact results/experiments/NAME
    python -m teamb.analysis.impact results/experiments/NAME --baseline coordinated --params my.json
    python -m teamb.analysis.impact results/runs            # any folder of run folders

Input: run summaries — results/experiments/<name>/runs/*/summary.json (the experiments runner),
any folder that contains run folders, a JSON file with a list of summaries, or a summary.csv.
Python: `analyze(list_of_summary_dicts)`.

Method (paired by seed, so every controller sees the identical demand)
  For every run:
    window_h        = (sim_time_s − warmup) / 3600                (measurement window, hours)
    delay_s         = (mean_delay_incl_unfinished_s + mean_depart_delay_s) × inserted_in_window
                      + (never_inserted + teleports) × unfinished_trip_delay_s
                      i.e. the timeLoss every inserted window trip accrued in the run (trips still
                      driving at the end are charged what they accrued, not a flat penalty, since
                      the run has no drain period), plus the time spent waiting to enter
                      (departDelay, not part of timeLoss), plus a flat penalty for trips that were
                      never inserted or teleported (stranded). In-flight trips' delay is slightly
                      understated (accrued, not final). Summaries without these PERF-01 fields
                      (older runs, hand-made CSVs) fall back to
                      mean_delay_s × completed + unfinished × unfinished_trip_delay_s.
    delay_veh_h/h   = delay_s / 3600 / window_h
    stops/h         = stops_per_veh × completed / window_h
  For every candidate run vs the baseline run with the same scenario, seed, coverage, sampling,
  preemption setting and run end (the effective end time; runs that end at different times are
  never paired, merged or annualized together):
    delay saved     = baseline delay_veh_h/h − candidate delay_veh_h/h      (veh·h per hour)
    time value      = delay saved × [(1 − truck_share) × occupancy × VOT + truck_share × truck VOT]
    fuel saved      = delay saved × idle_fuel_gal_per_h + stops saved/h × fuel_per_stop_gal
    fuel value      = fuel saved × (fuel price − fuel tax)                 (taxes are transfers)
    CO2 avoided     = fuel saved × co2_kg_per_gal;  CO2 value = t × co2_usd_per_tonne × cpi_2020_to_2023
                      (every dollar amount is in 2023 dollars)
    EV time saved   = baseline ev_mean_travel_time_s − candidate ev_mean_travel_time_s
  Seeds are averaged; ± is the 95 % confidence half-width of the paired differences (t-dist.).
  A candidate that leaves more trips unfinished than the baseline (by more than
  unfinished_tolerance_pp) is flagged PERF-01 and its benefit is not claimed.
  Annual benefit = Σ over scenarios of value per hour × ANNUAL_HOURS[scenario]; it is compared
  with the controller's deployment cost (capital annualized over the service life at the
  discount rate, plus O&M): B/C ratio, simple payback and NPV.
  Each scenario's annual hours are counted once per controller setting and run end: by the
  plain scenario row, or by its only variant ('<scenario>-<hash>', e.g. a --scenario-params run)
  when there is no plain row. Other variants and no-event counterfactual twins (events=[]) get 0 hours and a
  flag; set annual_hours["<scenario>-<hash>"] to annualize a variant explicitly.
  EV hours per year = the paired EV time saved in the claimed 'emergency' scenario rows
  (seed-weighted) × ev_trips_per_year; other EV scenarios (earthquake) are not routine trips.
Every number used is a named parameter in teamb/analysis/assumptions.py with its source.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from teamb import config
from teamb.analysis.assumptions import ASSUMPTIONS, ImpactParams
from teamb.evaluation.stats import mean_ci
from teamb.fsutil import atomic_write_json, atomic_write_text
NUMERIC_FIELDS = ("seed", "coverage", "sim_time_s", "completed", "unfinished", "unfinished_pct", "mean_delay_s",
                  "stops_per_veh", "throughput_veh_h", "ev_count", "ev_mean_travel_time_s", "teleports", "warmup",
                  "end_time", "inserted_in_window", "in_network_at_end", "never_inserted", "mean_delay_incl_unfinished_s",
                  "mean_depart_delay_s", "mean_delay_incl_depart_s", "others_mean_delay_s")


# --- loading -------------------------------------------------------------------------
def _to_number(value):
    if value in (None, "", "None", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _normalize(summary: dict, run_dir: Path | None = None) -> dict:
    """A summary plus the bookkeeping fields the analysis needs (keys starting with '_')."""
    run = dict(summary)
    for key in NUMERIC_FIELDS:
        if key in run and isinstance(run[key], str):
            run[key] = _to_number(run[key])
    if isinstance(run.get("ev_preemption"), str):
        run["ev_preemption"] = run["ev_preemption"].lower() in ("true", "1", "yes")
    spec, manifest = {}, {}
    if run_dir is not None:
        for name, target in (("run_spec.json", spec), ("manifest.json", manifest)):
            p = run_dir / name
            if p.exists():
                try:
                    target.update(json.loads(p.read_text()))
                except (OSError, json.JSONDecodeError):
                    pass
    warmup = run.get("warmup")
    if warmup is None:  # an explicit warmup of 0 is a value, not "missing"
        warmup = (manifest.get("config") or {}).get("warmup")
    run["_warmup"] = float(warmup) if warmup is not None else float(config.WARMUP_S)
    # did the run finish? (contract 2: summaries of interrupted runs must not be priced)
    end = run.get("end_time")
    if end is None:
        end = (manifest.get("config") or {}).get("end_time")
    if end is None:
        end = spec.get("end_time")
    run["_end_time"] = _to_number(end) if isinstance(end, str) else end
    if run_dir is not None:
        from teamb.experiments.runner import run_status

        status, _, reason = run_status(run_dir, expected_end=run["_end_time"])
        run["_incomplete"] = None if status == "ok" else reason
    else:
        run["_incomplete"] = None
        sim = run.get("sim_time_s")
        if run.get("complete") is False or str(run.get("complete")).lower() == "false":
            run["_incomplete"] = "summary is marked complete: false"
        elif isinstance(run["_end_time"], (int, float)) and isinstance(sim, (int, float)) and sim + 1e-6 < run["_end_time"]:
            run["_incomplete"] = f"stopped at sim_time_s {sim:g} before the end time {run['_end_time']:g}"
    run["_variant"] = spec.get("variant") or run.get("variant") or run.get("controller")
    run["_scenario"] = run.get("scenario_variant") or run.get("scenario")
    # the variant's parameters if known (run_spec.json or the summary itself), else None
    known = spec.get("scenario_params") if "scenario_params" in spec else run.get("scenario_params")
    run["_scenario_params"] = known if isinstance(known, dict) else None
    # name the variant from the same parameters (RunSpec.scenario_variant's naming): run_spec.json
    # always, the summary's own parameters unless it already names its scenario_variant
    if run["_scenario_params"] and ("scenario_params" in spec or not run.get("scenario_variant")):
        from teamb.experiments.runner import short_hash

        run["_scenario"] = f"{run.get('scenario')}-{short_hash(run['_scenario_params'])}"
    run["_dir"] = str(run_dir) if run_dir else None
    # does the folder carry today's name for its spec? (an older name: a leftover of the same run)
    if run_dir is not None and spec:
        from teamb.experiments.runner import canonical_run_name

        run["_canonical"] = canonical_run_name(spec) == run_dir.name
    else:
        run["_canonical"] = None
    return run


def load_runs(source) -> list[dict]:
    """Summaries from a folder, a JSON file, a summary.csv, or an in-memory list of dicts."""
    if isinstance(source, (list, tuple)):
        return [_normalize(s) for s in source]
    path = Path(source)
    if path.is_file():
        if path.suffix == ".csv":
            with open(path, newline="") as fh:
                return [_normalize(row) for row in csv.DictReader(fh)]
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            if "runs" in data:
                data = data["runs"]
            elif "summaries" in data:
                data = data["summaries"]
            else:
                data = [data]
        return [_normalize(s.get("summary", s) if isinstance(s, dict) else s) for s in data]
    if not path.is_dir():
        raise FileNotFoundError(f"no such file or folder: {path}")
    files = sorted(path.glob("runs/*/summary.json")) or sorted(path.glob("*/summary.json")) or sorted(path.rglob("summary.json"))
    if not files and (path / "summary.csv").exists():
        return load_runs(path / "summary.csv")
    runs = []
    for f in files:
        try:
            runs.append(_normalize(json.loads(f.read_text()), f.parent))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warning: skipping {f}: {exc}", file=sys.stderr)
    return runs


# --- per-run quantities -----------------------------------------------------------------
def run_quantities(run: dict, p: ImpactParams) -> dict | None:
    """Per-hour delay and stops of one run (None if the summary lacks the basics, or if the run
    stopped before its end time or before the warm-up ended: no measurement window to price)."""
    completed = run.get("completed")
    sim_time = run.get("sim_time_s")
    if completed is None or sim_time is None or run.get("_incomplete"):
        return None
    window_s = float(sim_time) - run["_warmup"]
    if window_s <= 0:
        return None
    window_h = window_s / 3600.0
    unfinished = float(run.get("unfinished") or 0)
    mean_delay = run.get("mean_delay_s")
    inserted, never = run.get("inserted_in_window"), run.get("never_inserted")
    accrued = run.get("mean_delay_incl_unfinished_s")
    if inserted is not None and never is not None and (accrued is not None or not inserted):
        # accrued timeLoss of every inserted window trip + entry waits + stranded trips (evaluation-5/6)
        per_trip = float(accrued or 0.0) + float(run.get("mean_depart_delay_s") or 0.0)
        stranded = float(never) + float(run.get("teleports") or 0)
        delay_s = per_trip * float(inserted) + stranded * p.unfinished_trip_delay_s
        method = "accrued"
    else:
        delay_s = (float(mean_delay) * completed if mean_delay is not None else 0.0) + unfinished * p.unfinished_trip_delay_s
        method = "completed+penalty"
    stops = float(run.get("stops_per_veh") or 0.0) * completed
    return {
        "delay_method": method,
        "window_h": window_h,
        "trips": completed + unfinished,
        "delay_veh_h_per_h": delay_s / 3600.0 / window_h,
        "stops_per_h": stops / window_h,
        "mean_delay_s": mean_delay,
        "unfinished_pct": run.get("unfinished_pct"),
        "throughput_veh_h": run.get("throughput_veh_h"),
        "ev": run.get("ev_mean_travel_time_s"),
    }


def vot_per_vehicle_hour(p: ImpactParams) -> float:
    return (1 - p.truck_share) * p.vehicle_occupancy * p.value_of_time_usd_per_person_h + p.truck_share * p.truck_value_of_time_usd_per_veh_h


def pair_effect(base: dict, cand: dict, p: ImpactParams) -> dict:
    """Benefit per hour of operation of `cand` over `base` (positive = better)."""
    saved = base["delay_veh_h_per_h"] - cand["delay_veh_h_per_h"]
    stops_saved = base["stops_per_h"] - cand["stops_per_h"]
    fuel = saved * p.idle_fuel_gal_per_h + stops_saved * p.fuel_per_stop_gal
    co2_kg = fuel * p.co2_kg_per_gal
    time_usd = saved * vot_per_vehicle_hour(p)
    fuel_usd = fuel * (p.fuel_price_usd_per_gal - p.fuel_tax_usd_per_gal)
    co2_usd = co2_kg / 1000.0 * p.co2_usd_per_tonne * p.cpi_2020_to_2023  # SC-CO2 is in 2020 dollars
    d_delay = None if base["mean_delay_s"] is None or cand["mean_delay_s"] is None else cand["mean_delay_s"] - base["mean_delay_s"]
    d_unf = None if base["unfinished_pct"] is None or cand["unfinished_pct"] is None else cand["unfinished_pct"] - base["unfinished_pct"]
    ev_saved = None if base["ev"] is None or cand["ev"] is None else base["ev"] - cand["ev"]
    return {
        "delta_mean_delay_s": d_delay,
        "delay_saved_veh_h_per_h": saved,
        "stops_saved_per_h": stops_saved,
        "time_value_usd_per_h": time_usd,
        "fuel_saved_gal_per_h": fuel,
        "fuel_value_usd_per_h": fuel_usd,
        "co2_avoided_kg_per_h": co2_kg,
        "co2_value_usd_per_h": co2_usd,
        "total_value_usd_per_h": time_usd + fuel_usd + co2_usd,
        "ev_time_saved_s": ev_saved,
        "delta_unfinished_pp": d_unf,
    }


def _summary_stat(values: list[float | None]) -> dict:
    """Mean and 95 % t half-width over seeds: the same implementation as the experiment report
    (teamb.evaluation.stats.mean_ci), so impact.md and report.md agree for the same data."""
    s = mean_ci(values)
    return {"mean": s["mean"], "ci95": s["ci95"], "n": s["n"]}


# --- the analysis ----------------------------------------------------------------------------
def _end(run: dict) -> float | None:
    """The run's effective end time in s (None if unknown), as a pairing key."""
    end = run.get("_end_time")
    return float(end) if isinstance(end, (int, float)) and not isinstance(end, bool) else None


def _setting(run: dict) -> tuple:
    """(scenario, coverage, sampling, preemption, run end): what must match for two runs to be paired."""
    return (run["_scenario"], run.get("coverage"), run.get("sampling", "uniform"), bool(run.get("ev_preemption", True)),
            _end(run))


def _end_label(end: float | None) -> str:
    return "unknown" if end is None else f"{end:g} s"


def _prefer(old: dict, new: dict) -> tuple[dict, dict]:
    """(kept, left out) for two runs of one setting and seed: the folder with today's run name,
    then the first folder name (as the experiment report does); summaries without a folder keep
    the last one."""
    if old.get("_dir") and new.get("_dir"):
        kept, dropped = sorted((old, new), key=lambda r: (not r.get("_canonical"), Path(r["_dir"]).name))
        return kept, dropped
    return new, old


def analyze(source, *, baseline: str = "fixed_time", params: ImpactParams | dict | None = None) -> dict:
    """Paired impact of every controller vs `baseline`, plus annual cost-benefit (JSON-ready)."""
    p = params if isinstance(params, ImpactParams) else ImpactParams.with_overrides(params)
    runs = load_runs(source)
    notes: list[str] = []
    by_key: dict[tuple, dict] = {}
    for run in runs:
        if run.get("_incomplete"):
            notes.append(f"incomplete/interrupted run for {run['_variant']}/{run['_scenario']}/seed {run.get('seed')} "
                         f"left out ({run['_incomplete']})")
            continue
        key = (*_setting(run), run["_variant"], run.get("seed"))
        if key in by_key:
            kept, dropped = _prefer(by_key[key], run)
            if kept.get("_dir") and dropped.get("_dir"):
                notes.append(f"duplicate run for {key}: using {Path(kept['_dir']).name}, "
                             f"leaving out {Path(dropped['_dir']).name}")
            else:
                notes.append(f"duplicate run for {key}; using the last one")
            run = kept
        by_key[key] = run
    base_runs = {k: r for k, r in by_key.items() if k[5] == baseline}
    # (scenario, preemption, run end, seed) -> run, for coverage-independent baselines
    base_any = defaultdict(dict)
    for (scen, cov, samp, pre, end, _var, seed), r in base_runs.items():
        base_any[(scen, pre, end, seed)].setdefault("run", r)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for (scen, cov, samp, pre, end, variant, seed), run in sorted(by_key.items(), key=lambda kv: str(kv[0])):
        if variant == baseline:
            continue
        base = base_runs.get((scen, cov, samp, pre, end, baseline, seed))
        fallback = False
        if base is None and (scen, pre, end, seed) in base_any:
            base, fallback = base_any[(scen, pre, end, seed)]["run"], True
        if base is None:
            notes.append(f"no {baseline} run to pair with {variant} on {scen} seed {seed} "
                         f"(coverage {cov}, preemption {pre}, run end {_end_label(end)})")
            continue
        qb, qc = run_quantities(base, p), run_quantities(run, p)
        if qb is None or qc is None:
            notes.append(f"incomplete summary for {variant}/{scen}/seed {seed}")
            continue
        groups[(scen, variant, cov, samp, pre, end)].append(
            {**pair_effect(qb, qc, p), "seed": seed, "fallback": fallback, "mixed": qb["delay_method"] != qc["delay_method"]}
        )

    params_of = {}
    for run in by_key.values():
        if run.get("_scenario_params") is not None:
            params_of.setdefault(run["_scenario"], run["_scenario_params"])
    rows = []
    ends = sorted({k[4] for k in by_key}, key=lambda e: (e is None, e or 0.0))
    if len(ends) > 1:
        notes.append(f"runs end at different times ({', '.join(_end_label(e) for e in ends)}): each run end is "
                     "paired, annualized and listed separately")
    for (scen, variant, cov, samp, pre, end), effects in sorted(groups.items(), key=lambda kv: str(kv[0])):
        stats = {k: _summary_stat([e[k] for e in effects]) for k in effects[0] if k not in ("seed", "fallback", "mixed")}
        d_unf = stats["delta_unfinished_pp"]["mean"]
        flags = []
        if d_unf is not None and d_unf > p.unfinished_tolerance_pp:
            flags.append(f"PERF-01: +{d_unf:.1f} pp unfinished trips — benefit not claimed")
        if any(e["fallback"] for e in effects):
            flags.append(f"baseline paired across coverage (the {baseline} baseline does not use probe data)")
        if len(effects) == 1:
            flags.append("1 seed — no confidence interval")
        if any(e["mixed"] for e in effects):
            flags.append("baseline and candidate summaries differ in detail (one lacks the PERF-01 fields): "
                         "delay compared with different formulas")
        scenario_name = scen.split("-")[0] if scen else scen
        rows.append(
            {
                "scenario": scen,
                "scenario_name": scenario_name,
                "controller": variant,
                "coverage": cov,
                "sampling": samp,
                "ev_preemption": pre,
                "end_time": end,
                "seeds": sorted(e["seed"] for e in effects),
                "n": len(effects),
                "stats": stats,
                "claimed": not any(f.startswith("PERF-01") for f in flags),
                "scenario_params": params_of.get(scen, {} if scen == scenario_name else None),
                "annual_hours": 0.0,
                "flags": flags,
            }
        )
    _assign_annual_hours(rows, p)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(source) if not isinstance(source, (list, tuple)) else f"{len(runs)} summaries",
        "baseline": baseline,
        "runs": len(runs),
        "rows": rows,
        "annual": annualize(rows, p),
        "preemption": preemption_effect(list(by_key.values()), p),
        "assumptions": assumption_table(p),
        "annual_hours": dict(p.annual_hours),
        "vot_usd_per_vehicle_hour": vot_per_vehicle_hour(p),
        "notes": sorted(set(notes)),
    }


def _is_counterfactual(row: dict) -> bool:
    """A no-event twin (--counterfactual): the scenario with its events removed."""
    from teamb.experiments.runner import short_hash
    from teamb.scenarios import REGISTRY, get_scenario

    name, params = row["scenario_name"], row.get("scenario_params")
    if name not in REGISTRY:
        return False
    if params is None:  # parameters unknown (e.g. a summary.csv): recognise the twin of the plain scenario by name
        return row["scenario"] == f"{name}-{short_hash({'events': []})}"
    if params.get("events") != []:
        return False
    try:
        return bool(get_scenario(name, **{k: v for k, v in params.items() if k != "events"}).events)
    except Exception:
        return False


def _assign_annual_hours(rows: list[dict], p: ImpactParams) -> None:
    """Give each scenario's ANNUAL_HOURS to exactly one row per controller setting (evaluation-4).

    An explicit annual_hours entry for a variant ("rush_hour-1a2b3c") always applies. Otherwise
    counterfactual twins get 0; of the remaining rows of one base scenario the plain one gets the
    hours, or the only variant if there is no plain row; the others get 0. Every 0 is flagged."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["controller"], r["coverage"], r["sampling"], r["ev_preemption"], r.get("end_time"),
                r["scenario_name"])].append(r)
    for (*_, name), rs in groups.items():
        hours = p.annual_hours.get(name, 0.0)
        rest = []
        for r in rs:
            if r["scenario"] != name and r["scenario"] in p.annual_hours:
                r["annual_hours"] = p.annual_hours[r["scenario"]]
            elif _is_counterfactual(r):
                if hours:
                    r["flags"].append("no-event counterfactual: not annualized")
            else:
                rest.append(r)
        if not rest or not hours:
            continue
        plain = [r for r in rest if r["scenario"] == name]
        chosen = plain[0] if plain else (rest[0] if len(rest) == 1 else None)
        for r in rest:
            if r is chosen:
                r["annual_hours"] = hours
            elif chosen is not None:
                r["flags"].append(f"variant of {name}: not annualized ({chosen['scenario']} carries its {hours:g} h/yr)")
            else:
                r["flags"].append(f"{len(rest)} variants of {name} and no plain run: none annualized "
                                  f"(set annual_hours[\"{r['scenario']}\"] to count one)")


def capital_recovery_factor(rate: float, years: float) -> float:
    if years <= 0:
        raise ValueError(f"service life must be > 0 years, not {years:g}")
    if rate == 0:
        return 1.0 / years
    g = (1 + rate) ** years
    return rate * g / (g - 1)


def annualize(rows: list[dict], p: ImpactParams) -> list[dict]:
    """Annual benefit per controller setting (and run end) vs its deployment cost."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["controller"], r["coverage"], r["sampling"], r["ev_preemption"], r.get("end_time"))].append(r)
    out = []
    crf = capital_recovery_factor(p.discount_rate, p.service_life_years)
    for (controller, cov, samp, pre, end), rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        parts = {"time": 0.0, "fuel": 0.0, "co2": 0.0}
        used, skipped = [], []
        for r in rs:
            hours = r["annual_hours"]
            if not hours:
                continue
            if not r["claimed"]:
                skipped.append(r["scenario"])
                continue
            s = r["stats"]
            parts["time"] += (s["time_value_usd_per_h"]["mean"] or 0.0) * hours
            parts["fuel"] += (s["fuel_value_usd_per_h"]["mean"] or 0.0) * hours
            parts["co2"] += (s["co2_value_usd_per_h"]["mean"] or 0.0) * hours
            used.append(r["scenario"])
        # routine EV trips: the claimed 'emergency' rows only, weighted by their seed counts (ext-23)
        ev_rows = [r for r in rs if r["claimed"] and r["scenario_name"] == "emergency"
                   and r["stats"]["ev_time_saved_s"]["mean"] is not None]
        n_ev = sum(r["stats"]["ev_time_saved_s"]["n"] for r in ev_rows)
        ev_hours = (sum(r["stats"]["ev_time_saved_s"]["mean"] * r["stats"]["ev_time_saved_s"]["n"] for r in ev_rows)
                    / n_ev * p.ev_trips_per_year / 3600.0) if n_ev else None
        benefit = sum(parts.values())
        capex, om, profile = p.cost_of(controller)
        annual_cost = capex * crf + om
        net = benefit - om
        npv = -capex + sum(net / (1 + p.discount_rate) ** y for y in range(1, int(p.service_life_years) + 1))
        out.append(
            {
                "controller": controller,
                "coverage": cov,
                "sampling": samp,
                "ev_preemption": pre,
                "end_time": end,
                "scenarios_used": used,
                "scenarios_not_claimed": skipped,
                "annual_benefit_usd": benefit,
                "annual_benefit_parts_usd": parts,
                "ev_hours_saved_per_year": ev_hours,
                "ev_scenarios_used": [r["scenario"] for r in ev_rows],
                "capex_usd": capex,
                "om_usd_per_year": om,
                "cost_profile": profile,
                "annualized_cost_usd": annual_cost,
                "benefit_cost_ratio": benefit / annual_cost if annual_cost > 0 else None,
                "payback_years": capex / net if net > 0 and capex > 0 else (0.0 if capex == 0 and net > 0 else None),
                "npv_usd": npv,
            }
        )
    return out


def preemption_effect(runs: list[dict], p: ImpactParams) -> list[dict]:
    """Same scenario, controller, seed and run end with preemption on vs off: EV time saved and
    the change in everyone else's delay (others_mean_delay_s, the non-EV trips; mean_delay_s only
    for summaries that lack it)."""
    on, off = {}, {}
    for r in runs:
        key = (r["_scenario"], r["_variant"], r.get("coverage"), r.get("sampling", "uniform"), _end(r), r.get("seed"))
        (on if r.get("ev_preemption", True) else off)[key] = r
    groups: dict[tuple, list[tuple]] = defaultdict(list)
    for key, r_off in off.items():
        if key in on:
            groups[key[:5]].append((on[key], r_off))
    out = []
    for (scen, variant, cov, samp, end), pairs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        ev_saved, delay_cost = [], []
        for r_on, r_off in pairs:
            if r_on.get("ev_mean_travel_time_s") is not None and r_off.get("ev_mean_travel_time_s") is not None:
                ev_saved.append(r_off["ev_mean_travel_time_s"] - r_on["ev_mean_travel_time_s"])
            # everyone else's delay: without the EVs, whose own delay preemption reduces (as in report.md)
            k = "others_mean_delay_s" if r_on.get("others_mean_delay_s") is not None and r_off.get("others_mean_delay_s") is not None else "mean_delay_s"
            if r_on.get(k) is not None and r_off.get(k) is not None:
                delay_cost.append(r_on[k] - r_off[k])
        out.append(
            {
                "scenario": scen,
                "controller": variant,
                "coverage": cov,
                "sampling": samp,
                "end_time": end,
                "n": len(pairs),
                "ev_time_saved_s": _summary_stat(ev_saved),
                "others_extra_delay_s": _summary_stat(delay_cost),
                "ev_travel_time_on_s": _summary_stat([a.get("ev_mean_travel_time_s") for a, _ in pairs]),
                "ev_travel_time_off_s": _summary_stat([b.get("ev_mean_travel_time_s") for _, b in pairs]),
                "ev_hours_saved_per_year": (mean(ev_saved) * p.ev_trips_per_year / 3600.0) if ev_saved else None,
            }
        )
    return out


def assumption_table(p: ImpactParams) -> list[dict]:
    return [
        {
            "name": a.name,
            "value": p.values[a.name],
            "unit": a.unit,
            "basis": a.basis,
            "source": a.source,
            "overridden": a.name in p.overridden,
        }
        for a in ASSUMPTIONS
    ]


# --- markdown ----------------------------------------------------------------------------
def _f(x, digits: int = 1, signed: bool = False) -> str:
    if x is None:
        return "–"
    return f"{x:+,.{digits}f}" if signed else f"{x:,.{digits}f}"


def _stat(s: dict, digits: int = 1, signed: bool = False) -> str:
    if s["mean"] is None:
        return "–"
    text = _f(s["mean"], digits, signed)
    return text + (f" ± {_f(s['ci95'], digits)}" if s.get("ci95") is not None else "")


def _setting_label(r: dict, show_end: bool = False) -> str:
    bits = []
    if show_end and r.get("end_time") is not None:
        bits.append(f"end {r['end_time']:g} s")
    if r.get("coverage") not in (None, 1.0):
        bits.append(f"c{round(100 * r['coverage'])}")
    if r.get("sampling") not in (None, "uniform"):
        bits.append(str(r["sampling"]))
    if r.get("ev_preemption") is False:
        bits.append("no preemption")
    return f" ({', '.join(bits)})" if bits else ""


def render_markdown(result: dict) -> str:
    base = result["baseline"]
    # several run ends: say which one every row is (rows of one end are only compared with each other)
    show_end = len({x.get("end_time") for part in ("rows", "annual", "preemption") for x in result.get(part) or []}) > 1
    lines = [
        "# Impact & cost-benefit",
        "",
        f"Source: `{result['source']}` · {result['runs']} runs · baseline **{base}** · generated {result['generated_at']}",
        "",
        "Paired by seed: every controller saw the identical demand. Δ columns are candidate − baseline",
        "(negative delay is better, positive unfinished is worse); 'saved', 'value' and 'avoided' columns are",
        "savings (positive is better). ± is the 95 % confidence half-width over seeds.",
        "Method and formulas: `teamb/analysis/impact.py`; every parameter: `teamb/analysis/assumptions.py`.",
        "",
        f"## Per hour of operation, vs {base}",
        "",
        "| Scenario | Controller | Seeds | Δ mean delay (s/veh) | Delay saved (veh·h/h) | Time value ($/h) "
        "| Fuel saved (gal/h) | CO₂ avoided (kg/h) | Total value ($/h) | EV time saved (s/trip) | Δ unfinished (pp) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in result["rows"]:
        s = r["stats"]
        lines.append(
            f"| {r['scenario']} | {r['controller']}{_setting_label(r, show_end)} | {r['n']} | {_stat(s['delta_mean_delay_s'], 1, True)} "
            f"| {_stat(s['delay_saved_veh_h_per_h'], 2)} | {_stat(s['time_value_usd_per_h'], 0)} | {_stat(s['fuel_saved_gal_per_h'], 2)} "
            f"| {_stat(s['co2_avoided_kg_per_h'], 1)} | {_stat(s['total_value_usd_per_h'], 0)} | {_stat(s['ev_time_saved_s'], 1)} "
            f"| {_stat(s['delta_unfinished_pp'], 2, True)} |"
        )
    if not result["rows"]:
        lines.append("| – | no candidate/baseline pairs found | | | | | | | | | |")
    flagged = [r for r in result["rows"] if r["flags"]]
    if flagged:
        lines += ["", "Flags:", ""]
        for r in flagged:
            lines.append(f"- {r['scenario']} / {r['controller']}{_setting_label(r, show_end)}: " + "; ".join(r["flags"]))

    n_junctions = next((int(a["value"]) for a in result["assumptions"] if a["name"] == "intersections"), 4)
    lines += [
        "",
        f"## Annualized benefit vs deployment cost ({n_junctions} intersections)",
        "",
        "| Controller | Annual benefit ($/yr) | time / fuel / CO₂ ($/yr) | EV time saved (h/yr) | Capital ($) "
        "| O&M ($/yr) | Annualized cost ($/yr) | B/C | Payback (yr) | NPV ($) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for a in result["annual"]:
        parts = a["annual_benefit_parts_usd"]
        lines.append(
            f"| {a['controller']}{_setting_label(a, show_end)} | {_f(a['annual_benefit_usd'], 0)} "
            f"| {_f(parts['time'], 0)} / {_f(parts['fuel'], 0)} / {_f(parts['co2'], 0)} | {_f(a['ev_hours_saved_per_year'], 1)} "
            f"| {_f(a['capex_usd'], 0)} | {_f(a['om_usd_per_year'], 0)} | {_f(a['annualized_cost_usd'], 0)} "
            f"| {_f(a['benefit_cost_ratio'], 2)} | {_f(a['payback_years'], 2)} | {_f(a['npv_usd'], 0)} |"
        )
    if not result["annual"]:
        lines.append("| – | | | | | | | | | |")
    hours = ", ".join(f"{k} {v:g} h" for k, v in result["annual_hours"].items())
    lines += ["", f"Hours per year each scenario stands for (assumptions): {hours}. Each scenario's hours count "
              "once per controller setting and run end (the plain scenario, or its only variant); other variants and no-event "
              "counterfactual twins are not annualized. EV hours per year use the claimed `emergency` rows only."]

    if result["preemption"]:
        lines += [
            "",
            "## Emergency preemption on vs off (same controller and seed)",
            "",
            "| Scenario | Controller | Seeds | EV travel time on (s) | off (s) | EV time saved (s/trip) | Others' extra delay (s/veh) | EV time saved (h/yr) |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for e in result["preemption"]:
            lines.append(
                f"| {e['scenario']} | {e['controller']}{_setting_label(e, show_end)} | {e['n']} | {_stat(e['ev_travel_time_on_s'])} | {_stat(e['ev_travel_time_off_s'])} "
                f"| {_stat(e['ev_time_saved_s'], 1)} | {_stat(e['others_extra_delay_s'], 2, True)} | {_f(e['ev_hours_saved_per_year'], 1)} |"
            )

    lines += [
        "",
        "## Assumptions",
        "",
        f"Value of an hour of vehicle delay with this mix: ${result['vot_usd_per_vehicle_hour']:.2f}.",
        "",
        "| Parameter | Value | Unit | Basis | Source |",
        "|---|---:|---|---|---|",
    ]
    for a in result["assumptions"]:
        value = f"{a['value']:g}" + (" (overridden)" if a["overridden"] else "")
        lines.append(f"| `{a['name']}` | {value} | {a['unit']} | {a['basis']} | {a['source']} |")
    if result["notes"]:
        lines += ["", "Notes:", ""] + [f"- {n}" for n in result["notes"]]
    lines += [
        "",
        "Limits: a synthetic, uncalibrated corridor; delay is SUMO timeLoss (includes slow driving, not only idling);",
        "fuel and CO₂ are estimates from idling and stop counts, not an emissions model; emergency time is not monetized.",
    ]
    return "\n".join(lines) + "\n"


# --- command line ------------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m teamb.analysis.impact", description=__doc__.split("\n")[0])
    parser.add_argument("source", help="results/experiments/<name>, a folder of run folders, a JSON list or a summary.csv")
    parser.add_argument("--baseline", default="fixed_time", help="baseline controller (variant) name")
    parser.add_argument("--params", help="JSON file overriding assumptions, e.g. {\"vehicle_occupancy\": 1.2}")
    parser.add_argument("--out", help="write the markdown here (default: <source>/impact.md for a folder)")
    parser.add_argument("--json", dest="json_out", help="also write the full result as JSON")
    parser.add_argument("--no-save", action="store_true", help="print only")
    args = parser.parse_args(argv)
    overrides = json.loads(Path(args.params).read_text()) if args.params else None
    result = analyze(args.source, baseline=args.baseline, params=overrides)
    text = render_markdown(result)
    print(text)
    if not args.no_save:
        src = Path(args.source)
        out = Path(args.out) if args.out else (src / "impact.md" if src.is_dir() else None)
        if out is not None:
            atomic_write_text(out, text)
            print(f"wrote {out}", file=sys.stderr)
        json_out = Path(args.json_out) if args.json_out else (src / "impact.json" if src.is_dir() and not args.out else None)
        if json_out is not None:
            atomic_write_json(json_out, result, default=str)
            print(f"wrote {json_out}", file=sys.stderr)
    if not result["rows"]:
        print(f"no runs could be paired with the baseline '{args.baseline}'", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
