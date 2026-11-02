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
    delay_veh_h/h   = (mean_delay_s × completed + unfinished × unfinished_trip_delay_s) / 3600 / window_h
    stops/h         = stops_per_veh × completed / window_h
  For every candidate run vs the baseline run with the same scenario, seed, coverage, sampling
  and preemption setting:
    delay saved     = baseline delay_veh_h/h − candidate delay_veh_h/h      (veh·h per hour)
    time value      = delay saved × [(1 − truck_share) × occupancy × VOT + truck_share × truck VOT]
    fuel saved      = delay saved × idle_fuel_gal_per_h + stops saved/h × fuel_per_stop_gal
    fuel value      = fuel saved × (fuel price − fuel tax)                 (taxes are transfers)
    CO2 avoided     = fuel saved × co2_kg_per_gal;  CO2 value = t × co2_usd_per_tonne
    EV time saved   = baseline ev_mean_travel_time_s − candidate ev_mean_travel_time_s
  Seeds are averaged; ± is the 95 % confidence half-width of the paired differences (t-dist.).
  A candidate that leaves more trips unfinished than the baseline (by more than
  unfinished_tolerance_pp) is flagged PERF-01 and its benefit is not claimed.
  Annual benefit = Σ over scenarios of value per hour × ANNUAL_HOURS[scenario]; it is compared
  with the controller's deployment cost (capital annualized over the service life at the
  discount rate, plus O&M): B/C ratio, simple payback and NPV.
Every number used is a named parameter in teamb/analysis/assumptions.py with its source.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev

from teamb import config
from teamb.analysis.assumptions import ASSUMPTIONS, ImpactParams

T_975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
         11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
         20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048,
         29: 2.045, 30: 2.042}
NUMERIC_FIELDS = ("seed", "coverage", "sim_time_s", "completed", "unfinished", "unfinished_pct", "mean_delay_s",
                  "stops_per_veh", "throughput_veh_h", "ev_count", "ev_mean_travel_time_s", "teleports", "warmup")


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
    warmup = run.get("warmup") or (manifest.get("config") or {}).get("warmup")
    run["_warmup"] = float(warmup) if warmup is not None else float(config.WARMUP_S)
    run["_variant"] = spec.get("variant") or run.get("variant") or run.get("controller")
    scenario_params = spec.get("scenario_params") or {}
    run["_scenario"] = run.get("scenario_variant") or run.get("scenario")
    if scenario_params:  # same naming as the experiments runner (RunSpec.scenario_variant)
        digest = hashlib.sha1(json.dumps(scenario_params, sort_keys=True).encode()).hexdigest()[:6]
        run["_scenario"] = f"{run.get('scenario')}-{digest}"
    run["_dir"] = str(run_dir) if run_dir else None
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
            data = data.get("runs") or data.get("summaries") or [data]
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
    """Per-hour delay and stops of one run (None if the summary lacks the basics)."""
    completed = run.get("completed")
    sim_time = run.get("sim_time_s")
    if completed is None or sim_time is None:
        return None
    window_h = max(1e-9, (float(sim_time) - run["_warmup"]) / 3600.0)
    unfinished = float(run.get("unfinished") or 0)
    mean_delay = run.get("mean_delay_s")
    delay_s = (float(mean_delay) * completed if mean_delay is not None else 0.0) + unfinished * p.unfinished_trip_delay_s
    stops = float(run.get("stops_per_veh") or 0.0) * completed
    return {
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
    co2_usd = co2_kg / 1000.0 * p.co2_usd_per_tonne
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
    vals = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return {"mean": None, "ci95": None, "n": 0}
    m = mean(vals)
    if len(vals) < 2:
        return {"mean": m, "ci95": None, "n": 1}
    half = T_975.get(len(vals) - 1, 1.96) * stdev(vals) / math.sqrt(len(vals))
    return {"mean": m, "ci95": half, "n": len(vals)}


# --- the analysis ----------------------------------------------------------------------------
def _setting(run: dict) -> tuple:
    return (run["_scenario"], run.get("coverage"), run.get("sampling", "uniform"), bool(run.get("ev_preemption", True)))


def analyze(source, *, baseline: str = "fixed_time", params: ImpactParams | dict | None = None) -> dict:
    """Paired impact of every controller vs `baseline`, plus annual cost-benefit (JSON-ready)."""
    p = params if isinstance(params, ImpactParams) else ImpactParams.with_overrides(params)
    runs = load_runs(source)
    notes: list[str] = []
    by_key: dict[tuple, dict] = {}
    for run in runs:
        key = (*_setting(run), run["_variant"], run.get("seed"))
        if key in by_key:
            notes.append(f"duplicate run for {key}; using the last one")
        by_key[key] = run
    base_runs = {k: r for k, r in by_key.items() if k[4] == baseline}
    base_any = defaultdict(dict)  # (scenario, preemption, seed) -> run, for coverage-independent baselines
    for (scen, cov, samp, pre, _var, seed), r in base_runs.items():
        base_any[(scen, pre, seed)].setdefault("run", r)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for (scen, cov, samp, pre, variant, seed), run in sorted(by_key.items(), key=lambda kv: str(kv[0])):
        if variant == baseline:
            continue
        base = base_runs.get((scen, cov, samp, pre, baseline, seed))
        fallback = False
        if base is None and (scen, pre, seed) in base_any:
            base, fallback = base_any[(scen, pre, seed)]["run"], True
        if base is None:
            notes.append(f"no {baseline} run to pair with {variant} on {scen} seed {seed} (coverage {cov}, preemption {pre})")
            continue
        qb, qc = run_quantities(base, p), run_quantities(run, p)
        if qb is None or qc is None:
            notes.append(f"incomplete summary for {variant}/{scen}/seed {seed}")
            continue
        groups[(scen, variant, cov, samp, pre)].append({**pair_effect(qb, qc, p), "seed": seed, "fallback": fallback})

    rows = []
    for (scen, variant, cov, samp, pre), effects in sorted(groups.items(), key=lambda kv: str(kv[0])):
        stats = {k: _summary_stat([e[k] for e in effects]) for k in effects[0] if k not in ("seed", "fallback")}
        d_unf = stats["delta_unfinished_pp"]["mean"]
        flags = []
        if d_unf is not None and d_unf > p.unfinished_tolerance_pp:
            flags.append(f"PERF-01: +{d_unf:.1f} pp unfinished trips — benefit not claimed")
        if any(e["fallback"] for e in effects):
            flags.append(f"baseline paired across coverage (the {baseline} baseline does not use probe data)")
        if len(effects) == 1:
            flags.append("1 seed — no confidence interval")
        scenario_name = scen.split("-")[0] if scen else scen
        rows.append(
            {
                "scenario": scen,
                "scenario_name": scenario_name,
                "controller": variant,
                "coverage": cov,
                "sampling": samp,
                "ev_preemption": pre,
                "seeds": sorted(e["seed"] for e in effects),
                "n": len(effects),
                "stats": stats,
                "claimed": not any(f.startswith("PERF-01") for f in flags),
                "annual_hours": p.annual_hours.get(scenario_name, 0.0),
                "flags": flags,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(source) if not isinstance(source, (list, tuple)) else f"{len(runs)} summaries",
        "baseline": baseline,
        "runs": len(runs),
        "rows": rows,
        "annual": annualize(rows, p),
        "preemption": preemption_effect(runs, p),
        "assumptions": assumption_table(p),
        "annual_hours": dict(p.annual_hours),
        "vot_usd_per_vehicle_hour": vot_per_vehicle_hour(p),
        "notes": sorted(set(notes)),
    }


def capital_recovery_factor(rate: float, years: float) -> float:
    if rate == 0:
        return 1.0 / years
    g = (1 + rate) ** years
    return rate * g / (g - 1)


def annualize(rows: list[dict], p: ImpactParams) -> list[dict]:
    """Annual benefit per controller setting vs its deployment cost."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["controller"], r["coverage"], r["sampling"], r["ev_preemption"])].append(r)
    out = []
    crf = capital_recovery_factor(p.discount_rate, p.service_life_years)
    for (controller, cov, samp, pre), rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
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
        ev_saved = [r["stats"]["ev_time_saved_s"]["mean"] for r in rs if r["stats"]["ev_time_saved_s"]["mean"] is not None]
        ev_hours = mean(ev_saved) * p.ev_trips_per_year / 3600.0 if ev_saved else None
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
                "scenarios_used": used,
                "scenarios_not_claimed": skipped,
                "annual_benefit_usd": benefit,
                "annual_benefit_parts_usd": parts,
                "ev_hours_saved_per_year": ev_hours,
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
    """Same scenario, controller and seed with preemption on vs off: EV time saved and the
    change in everyone else's delay."""
    on, off = {}, {}
    for r in runs:
        key = (r["_scenario"], r["_variant"], r.get("coverage"), r.get("sampling", "uniform"), r.get("seed"))
        (on if r.get("ev_preemption", True) else off)[key] = r
    groups: dict[tuple, list[tuple]] = defaultdict(list)
    for key, r_off in off.items():
        if key in on:
            groups[key[:4]].append((on[key], r_off))
    out = []
    for (scen, variant, cov, samp), pairs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        ev_saved, delay_cost = [], []
        for r_on, r_off in pairs:
            if r_on.get("ev_mean_travel_time_s") is not None and r_off.get("ev_mean_travel_time_s") is not None:
                ev_saved.append(r_off["ev_mean_travel_time_s"] - r_on["ev_mean_travel_time_s"])
            if r_on.get("mean_delay_s") is not None and r_off.get("mean_delay_s") is not None:
                delay_cost.append(r_on["mean_delay_s"] - r_off["mean_delay_s"])
        out.append(
            {
                "scenario": scen,
                "controller": variant,
                "coverage": cov,
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


def _setting_label(r: dict) -> str:
    bits = []
    if r.get("coverage") not in (None, 1.0):
        bits.append(f"c{round(100 * r['coverage'])}")
    if r.get("sampling") not in (None, "uniform"):
        bits.append(str(r["sampling"]))
    if r.get("ev_preemption") is False:
        bits.append("no preemption")
    return f" ({', '.join(bits)})" if bits else ""


def render_markdown(result: dict) -> str:
    base = result["baseline"]
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
            f"| {r['scenario']} | {r['controller']}{_setting_label(r)} | {r['n']} | {_stat(s['delta_mean_delay_s'], 1, True)} "
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
            lines.append(f"- {r['scenario']} / {r['controller']}{_setting_label(r)}: " + "; ".join(r["flags"]))

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
            f"| {a['controller']}{_setting_label(a)} | {_f(a['annual_benefit_usd'], 0)} "
            f"| {_f(parts['time'], 0)} / {_f(parts['fuel'], 0)} / {_f(parts['co2'], 0)} | {_f(a['ev_hours_saved_per_year'], 1)} "
            f"| {_f(a['capex_usd'], 0)} | {_f(a['om_usd_per_year'], 0)} | {_f(a['annualized_cost_usd'], 0)} "
            f"| {_f(a['benefit_cost_ratio'], 2)} | {_f(a['payback_years'], 2)} | {_f(a['npv_usd'], 0)} |"
        )
    if not result["annual"]:
        lines.append("| – | | | | | | | | | |")
    hours = ", ".join(f"{k} {v:g} h" for k, v in result["annual_hours"].items())
    lines += ["", f"Hours per year each scenario stands for (assumptions): {hours}."]

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
                f"| {e['scenario']} | {e['controller']} | {e['n']} | {_stat(e['ev_travel_time_on_s'])} | {_stat(e['ev_travel_time_off_s'])} "
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
            out.write_text(text)
            print(f"wrote {out}", file=sys.stderr)
        json_out = Path(args.json_out) if args.json_out else (src / "impact.json" if src.is_dir() and not args.out else None)
        if json_out is not None:
            json_out.write_text(json.dumps(result, indent=2, default=str))
            print(f"wrote {json_out}", file=sys.stderr)
    if not result["rows"]:
        print(f"no runs could be paired with the baseline '{args.baseline}'", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
