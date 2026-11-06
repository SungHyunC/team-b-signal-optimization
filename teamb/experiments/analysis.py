"""Turn the runs of an experiment into summary.csv, report.json and report.md.

Pairing rule (matched demand seeds)
-----------------------------------
A candidate group (scenario, controller variant, coverage, sampling, preemption, run end) is
compared with the baseline controller's runs of the same scenario, preemption setting and run
end, preferably with the same coverage and sampling ("exact"); if the baseline was only run at
another coverage/sampling (fine for fixed-time, which ignores sensor data) that run is used
("scenario"). A baseline with another preemption setting or run end is never used: those
change every controller's result. Only seeds present in both are paired. The run end is the
effective one (the spec's end_time, else the scenario duration from the manifest).

report.json schema (read by the twin; extra keys may be added, never removed)
-----------------------------------------------------------------------------
{"name", "created", "baseline": "fixed_time",
 "rows": [{"scenario", "controller", "coverage", "n_seeds",
           "mean_delay_s": {"mean", "ci95"}, "p95_travel_time_s": {...}, "stops_per_veh": {...},
           "unfinished_pct": {...}, "ev_mean_travel_time_s": {...},
           "delta_vs_baseline_pct": {"mean", "ci95"}, ...extras}],
 ...extras}
"ci95" is the half-width of the 95 % confidence interval (mean ± ci95), None with one seed.
"delta_vs_baseline_pct" is the paired improvement in mean delay, positive = better than baseline.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from teamb.evaluation.stats import holm, mean_ci, paired
from teamb.experiments.runner import run_status
from teamb.fsutil import read_json

ROW_METRICS = ("mean_delay_s", "p95_travel_time_s", "stops_per_veh", "unfinished_pct", "ev_mean_travel_time_s")
EXTRA_METRICS = (
    "mean_travel_time_s", "throughput_veh_h", "arterial_mean_delay_s", "cross_mean_delay_s", "queue_p95_veh",
    "spillback_duration_s", "queue_warning_s", "others_mean_delay_s", "ev_mean_delay_s", "ev_extra_delay_others_s",
    "recovery_time_s", "excess_delay_veh_h", "est_queue_mae", "est_queue_bias", "est_flow_mae", "alert_s",
    "false_alarm_s", "detection_delay_s", "completed", "unfinished", "never_inserted", "teleports",
    "mean_delay_incl_unfinished_s", "wall_time_s",
)
IDENTITY = ("name", "scenario", "scenario_variant", "controller", "variant", "seed", "coverage", "sampling", "ev_preemption", "end_time", "status")
DEFINITIONS = {
    "mean_delay_s": "Mean SUMO timeLoss (s/veh) of trips that depart in [warmup, end) and finish (primary endpoint).",
    "ci95": "Half-width of the 95 % t confidence interval over seeds (mean ± ci95); null with one seed.",
    "delta_vs_baseline_pct": "Paired improvement in mean delay vs the baseline on matched seeds: mean over seeds of "
    "100 × (baseline − candidate) / baseline. Positive = better (less delay) than the baseline.",
    "mean_delay_diff_s": "Paired difference candidate − baseline in mean delay (s/veh); negative = better.",
    "p_value": "Two-sided paired t-test on the per-seed delay differences.",
    "p_holm": "p_value after Holm–Bonferroni correction over the candidates of the same scenario.",
    "unfinished_pct": "100 × (trips still in the network at the end + trips never inserted) / (completed + unfinished) (PERF-01).",
    "ev_mean_travel_time_s": "Mean travel time of emergency vehicles that finished.",
    "baseline_match": "'exact' = baseline run with the same coverage/sampling, 'scenario' = same scenario, other coverage. "
    "Always the same preemption setting and run end; null = no such baseline run.",
    "end_time": "Effective run end in s (the --end given, else the scenario's duration).",
}


def _scalar(v) -> bool:
    return v is None or isinstance(v, (int, float, str, bool))


def _round(v, digits=3):
    return None if v is None else round(v, digits)


def _stat(values, digits=3) -> dict:
    s = mean_ci(values)
    return {"mean": _round(s["mean"], digits), "ci95": _round(s["ci95"], digits)}


def load_runs(exp_dir: Path) -> list[dict]:
    """One flat dict per run directory: identity fields + scalar summary metrics.

    status "ok" only for a finished run (runner.run_status: summary.json parses, is not marked
    incomplete, no error.json, and the run reached its end time); "failed" when error.json is
    present; "incomplete" otherwise (still running, killed, or a truncated legacy summary).
    Only "ok" runs enter the statistics; "error" says why the others did not."""
    runs = []
    runs_dir = Path(exp_dir) / "runs"
    if not runs_dir.exists():
        return runs
    for d in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        spec = read_json(d / "run_spec.json", {})
        spec = spec if isinstance(spec, dict) else {}
        status, summary, error = run_status(d, expected_end=spec.get("end_time"))
        src = summary or {}
        end_time = spec.get("end_time")
        if end_time is None:  # the scenario's duration: from the manifest, else where the run stopped
            manifest = read_json(d / "manifest.json", {})
            end_time = ((manifest.get("config") or {}) if isinstance(manifest, dict) else {}).get("end_time")
        if end_time is None:
            end_time = src.get("sim_time_s")
        scenario = spec.get("scenario", src.get("scenario"))
        controller = spec.get("controller", src.get("controller"))
        row = {
            "name": spec.get("name", d.name),
            "scenario": scenario,
            "scenario_variant": d.name.split("__")[0] if spec.get("scenario_params") else scenario,
            "controller": controller,
            "variant": spec.get("variant", controller),
            "controller_params": spec.get("controller_params", {}),
            "seed": spec.get("seed", src.get("seed")),
            "coverage": spec.get("coverage", src.get("coverage")),
            "sampling": spec.get("sampling", src.get("sampling", "uniform")),
            "ev_preemption": spec.get("ev_preemption", src.get("ev_preemption", True)),
            "end_time": None if end_time is None else float(end_time),
            "status": status,
            "error": error,
            "wall_total_s": spec.get("wall_total_s"),
            "bytes": spec.get("bytes"),
            "scenario_params": spec.get("scenario_params", {}),
            "run_dir": str(d),
        }
        for k, v in src.items():
            if k not in row and _scalar(v):
                row[k] = v
        runs.append(row)
    return runs


def write_summary_csv(runs: list[dict], path: Path) -> None:
    cols = list(IDENTITY)
    for r in runs:
        for k, v in r.items():
            if k not in cols and _scalar(v) and k not in ("error", "run_dir"):
                cols.append(k)
    cols.append("error")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in runs:
            w.writerow({k: r.get(k) for k in cols})


def _group_key(r: dict) -> tuple:
    """(scenario_variant, variant, coverage, sampling, ev_preemption, end_time): runs that differ
    only in the seed. end_time is the effective run end (float, or None if unknown)."""
    end = r.get("end_time")
    return (r["scenario_variant"], r["variant"], float(r["coverage"]), r["sampling"], bool(r["ev_preemption"]),
            None if end is None else float(end))


def _find_baseline(key: tuple, groups: dict, baseline: str) -> tuple[tuple | None, str | None]:
    scen, _, cov, sampling, pre, end = key
    # never across preemption or run end: both change the baseline's own result (evaluation-8, ext-79)
    cands = [k for k, rs in groups.items() if k[0] == scen and k[4] == pre and k[5] == end and rs[0]["controller"] == baseline]
    if not cands:
        return None, None
    plain = [k for k in cands if k[1] == baseline] or cands  # prefer the baseline without custom params
    exact = [k for k in plain if k[2] == cov and k[3] == sampling]
    if exact:
        return exact[0], "exact"
    plain.sort(key=lambda k: (k[2] != 1.0, k[3] != "uniform", -k[2]))
    return plain[0], "scenario"


def _by_seed(rs: list[dict], metric: str) -> dict:
    return {r["seed"]: r.get(metric) for r in rs}


def build_report(exp_dir: Path, baseline: str = "fixed_time") -> dict:
    exp_dir = Path(exp_dir)
    runs = load_runs(exp_dir)
    ok = [r for r in runs if r["status"] == "ok"]
    groups: dict[tuple, list[dict]] = {}
    for r in ok:
        groups.setdefault(_group_key(r), []).append(r)
    scen_order = list(dict.fromkeys(r["scenario_variant"] for r in ok))
    ctrl_order = list(dict.fromkeys(r["variant"] for r in ok))

    def sort_key(k):
        rs = groups[k]
        return (scen_order.index(k[0]), k[5] is None, k[5] or 0.0, rs[0]["controller"] != baseline,
                ctrl_order.index(k[1]), -k[2], k[3], not k[4])

    rows = []
    for key in sorted(groups, key=sort_key):
        rs = sorted(groups[key], key=lambda r: r["seed"])
        first = rs[0]
        row = {
            "scenario": first["scenario"],
            "controller": first["controller"],
            "coverage": key[2],
            "n_seeds": len(rs),
        }
        for m in ROW_METRICS:
            row[m] = _stat([r.get(m) for r in rs])
        base_key, match = _find_baseline(key, groups, baseline)
        is_base = first["controller"] == baseline and base_key == key
        if base_key is not None and not is_base:
            pr = paired(_by_seed(groups[base_key], "mean_delay_s"), _by_seed(rs, "mean_delay_s"))
            row["delta_vs_baseline_pct"] = {"mean": _round(pr["improvement_pct"]["mean"]), "ci95": _round(pr["improvement_pct"]["ci95"])}
            row["mean_delay_diff_s"] = {"mean": _round(pr["diff"]["mean"]), "ci95": _round(pr["diff"]["ci95"])}
            row["p_value"] = _round(pr["p_value"], 4)
            row["n_paired"] = pr["n"]
            row["improvement_of_means_pct"] = _round(pr["improvement_of_means_pct"])
        elif is_base:
            row["delta_vs_baseline_pct"] = {"mean": 0.0, "ci95": 0.0}
            row["mean_delay_diff_s"] = {"mean": 0.0, "ci95": 0.0}
            row["p_value"] = None
            row["n_paired"] = len(rs)
        else:
            row["delta_vs_baseline_pct"] = {"mean": None, "ci95": None}
            row["p_value"] = None
            row["n_paired"] = 0
        row.update(
            {
                "variant": first["variant"],
                "controller_params": first.get("controller_params") or {},
                "scenario_variant": first["scenario_variant"],
                "sampling": first["sampling"],
                "ev_preemption": first["ev_preemption"],
                "end_time": key[5],
                "seeds": [r["seed"] for r in rs],
                "is_baseline": is_base,
                "baseline_match": "self" if is_base else match,
                "metrics": {m: _stat([r.get(m) for r in rs]) for m in EXTRA_METRICS},
            }
        )
        rows.append(row)
    # Holm correction within each scenario
    for scen in scen_order:
        idx = [i for i, r in enumerate(rows) if r["scenario_variant"] == scen and not r["is_baseline"]]
        adj = holm([rows[i].get("p_value") for i in idx])
        for i, p in zip(idx, adj):
            rows[i]["p_holm"] = _round(p, 4)

    meta_path = exp_dir / "experiment.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    report = {
        "name": exp_dir.name,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "baseline": baseline,
        "rows": rows,
        "definitions": DEFINITIONS,
        "matrix": _matrix(ok, meta),
        "coverage_sweep": _coverage_sweep(groups, rows),
        "estimation": _estimation_table(ok),
        "security": _security_table(groups),
        "recovery": _recovery_table(groups),
        "emergency": _ev_table(groups),
        "perf01": _perf_table(groups),
        "compute": _compute(runs, meta),
        "failed_runs": [{"name": r["name"], "error": r["error"]} for r in runs if r["status"] == "failed"],
        "incomplete_runs": [{"name": r["name"], "reason": r["error"]} for r in runs if r["status"] == "incomplete"],
        "code_revision": _first_manifest_value(exp_dir, "code_revision"),
        "sumo_version": _first_manifest_value(exp_dir, "sumo_version"),
    }
    config = _first_manifest_value(exp_dir, "config") or {}
    report["matrix"]["warmup_s"] = config.get("warmup")
    report["commands"] = [i["command"] for i in meta.get("invocations", []) if i.get("command")]
    warnings = []
    if len(report["matrix"]["end_time"]) > 1:
        warnings.append(
            f"runs end at different times ({', '.join(f'{x:g}' for x in report['matrix']['end_time'])} s); "
            "each run end is reported and paired separately"
        )
    report["warnings"] = warnings
    return report


def _first_manifest_value(exp_dir: Path, key: str):
    for m in sorted((Path(exp_dir) / "runs").glob("*/manifest.json")):
        try:
            return json.loads(m.read_text()).get(key)
        except (OSError, ValueError):
            continue
    return None


def _matrix(ok: list[dict], meta: dict | None = None) -> dict:
    scen_params, ctrl_params = {}, {}
    for inv in (meta or {}).get("invocations", []):
        scen_params.update(inv.get("matrix", {}).get("scenario_params", {}))
        ctrl_params.update(inv.get("matrix", {}).get("controller_params", {}))
    return {
        "scenarios": sorted({r["scenario_variant"] for r in ok}),
        "controllers": sorted({r["variant"] for r in ok}),
        "scenario_params": {k: v for k, v in scen_params.items() if k in {r["scenario_variant"] for r in ok}},
        "controller_params": {k: v for k, v in ctrl_params.items() if k in {r["variant"] for r in ok}},
        "seeds": sorted({r["seed"] for r in ok}),
        "coverages": sorted({float(r["coverage"]) for r in ok}),
        "samplings": sorted({r["sampling"] for r in ok}),
        "ev_preemption": sorted({bool(r["ev_preemption"]) for r in ok}),
        "end_time": sorted({r["end_time"] for r in ok if r["end_time"] is not None}),
    }


def _coverage_sweep(groups: dict, rows: list[dict]) -> list[dict]:
    """Delay and estimation error by coverage, for every (scenario, controller, sampling) run at >= 2 coverages."""
    by_line: dict[tuple, list[tuple]] = {}
    for key in groups:
        by_line.setdefault((key[0], key[1], key[3], key[4], key[5]), []).append(key)
    delta = {
        (r["scenario_variant"], r["variant"], r["coverage"], r["sampling"], bool(r["ev_preemption"]), r["end_time"]): r["delta_vs_baseline_pct"]
        for r in rows
    }
    out = []
    for line, keys in by_line.items():
        if len({k[2] for k in keys}) < 2:
            continue
        for key in sorted(keys, key=lambda k: k[2]):
            rs = groups[key]
            out.append(
                {
                    "scenario": rs[0]["scenario"],
                    "controller": rs[0]["variant"],
                    "sampling": key[3],
                    "coverage": key[2],
                    "n_seeds": len(rs),
                    "mean_delay_s": _stat([r.get("mean_delay_s") for r in rs]),
                    "delta_vs_baseline_pct": delta.get(key),
                    "est_queue_mae": _stat([r.get("est_queue_mae") for r in rs]),
                    "est_queue_bias": _stat([r.get("est_queue_bias") for r in rs]),
                    "est_queue_adj_bias": _stat([r.get("est_queue_adj_bias") for r in rs]),
                    "est_flow_mae": _stat([r.get("est_flow_mae") for r in rs]),
                    "false_alarm_s": _stat([r.get("false_alarm_s") for r in rs]),
                }
            )
    return out


def _estimation_table(ok: list[dict]) -> list[dict]:
    """Sensor estimation error by sampling mechanism and coverage (all scenarios/controllers pooled)."""
    cells: dict[tuple, list[dict]] = {}
    for r in ok:
        if r.get("est_samples"):
            cells.setdefault((r["sampling"], float(r["coverage"])), []).append(r)
    metrics = (
        "probe_share", "probe_share_arterial", "probe_share_cross", "est_queue_mae", "est_queue_bias",
        "est_queue_bias_arterial", "est_queue_bias_cross", "est_queue_adj_mae", "est_queue_adj_bias",
        "det_queue_mae", "fused_queue_mae", "est_flow_mae", "est_flow_bias", "false_alarm_s",
    )
    out = []
    for (sampling, cov), rs in sorted(cells.items()):
        out.append({"sampling": sampling, "coverage": cov, "n_runs": len(rs), **{m: _stat([r.get(m) for r in rs]) for m in metrics}})
    return out


def _security_table(groups: dict) -> list[dict]:
    out = []
    for key, rs in groups.items():
        if not any((r.get("attacks") or 0) > 0 for r in rs):
            continue
        detected = [r.get("attack_detected") for r in rs if r.get("attack_detected") is not None]
        out.append(
            {
                "scenario": rs[0]["scenario"], "controller": rs[0]["variant"], "coverage": key[2], "sampling": key[3],
                "n_seeds": len(rs),
                "detected_share": _round(sum(bool(d) for d in detected) / len(detected)) if detected else None,
                "detection_delay_s": _stat([r.get("detection_delay_s") for r in rs]),
                "alert_s": _stat([r.get("alert_s") for r in rs]),
                "false_alarm_s": _stat([r.get("false_alarm_s") for r in rs]),
                "mean_delay_s": _stat([r.get("mean_delay_s") for r in rs]),
            }
        )
    return out


def _twin_key(key: tuple, groups: dict) -> tuple | None:
    """The no-event counterfactual group of a disrupted group: same scenario (+ params) with
    events=[], same controller variant, coverage, sampling, preemption and run end."""
    base = groups[key][0]
    want = {**(base.get("scenario_params") or {}), "events": []}
    for k, rs in groups.items():
        r0 = rs[0]
        if k != key and k[1:] == key[1:] and r0["scenario"] == base["scenario"] and (r0.get("scenario_params") or {}) == want:
            return k
    return None


def _read_series(run_dir: str) -> tuple[list[float], list[float]]:
    path = Path(run_dir) / "timeseries.csv"
    if not path.exists():
        return [], []
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    return [float(r["t"]) for r in rows], [float(r["delay_rate"]) for r in rows]


def _vs_counterfactual(rs: list[dict], twins: list[dict]) -> tuple[list[dict], dict]:
    """Per seed: recovery of each disruption window against the no-event twin run, and the
    seed's total excess over the union of its windows (each second once). Windows are merged
    into their union first (older evaluation.json files kept overlapping windows apart)."""
    from teamb.evaluation.recovery import merge_windows, recovery_vs_reference, union_excess

    by_seed = {r["seed"]: r for r in twins}
    out, seed_excess = [], {}
    for r in rs:
        twin = by_seed.get(r["seed"])
        detail = read_json(Path(r["run_dir"]) / "evaluation.json")
        if twin is None or not isinstance(detail, dict):
            continue
        windows = merge_windows(detail.get("recovery") or [])
        t, v = _read_series(r["run_dir"])
        t0, v0 = _read_series(twin["run_dir"])
        per = []
        for w in windows:
            res = recovery_vs_reference(t, v, t0, v0, start=w["start"], end=w["end"])
            per.append({"seed": r["seed"], "what": w["what"], **res})
        out += per
        if len(per) == 1:
            seed_excess[r["seed"]] = per[0]["excess_veh_h"]
        elif per:
            ref = dict(zip(t0, v0))
            matched = [(a, b) for a, b in zip(t, v) if a in ref]
            last = matched[-1][0] if matched else None
            spans = [(p["start"], p["recovered_at"] if p["recovered_at"] is not None else last, ref) for p in per]
            seed_excess[r["seed"]] = union_excess([a for a, _ in matched], [b for _, b in matched], spans)
    return out, seed_excess


def _per_seed_recovery(per: list[dict], seed_excess: dict) -> dict:
    """One value per seed (the windows of one run are not independent replicates): recovery =
    the slowest window, censored if any window is; excess = the union over the run's windows."""
    by_seed: dict = {}
    for p in per:
        by_seed.setdefault(p["seed"], []).append(p)
    recovery, censored = [], 0
    for ps in by_seed.values():
        if any(p["censored"] for p in ps):
            censored += 1
        else:
            recovery.append(max(p["recovery_s"] for p in ps))
    return {"n": len(by_seed), "recovery_s": _stat(recovery), "censored": censored,
            "excess_veh_h": _stat([seed_excess.get(s) for s in by_seed])}


def _recovery_table(groups: dict) -> list[dict]:
    out = []
    for key, rs in groups.items():
        if not any((r.get("disruptions") or 0) > 0 for r in rs):
            continue
        row = {
            "scenario": rs[0]["scenario"], "controller": rs[0]["variant"], "coverage": key[2], "sampling": key[3],
            "n_seeds": len(rs),
            "recovery_time_s": _stat([r.get("recovery_time_s") for r in rs]),
            "censored": sum(bool(r.get("recovery_censored")) for r in rs),
            "excess_delay_veh_h": _stat([r.get("excess_delay_veh_h") for r in rs]),
            "spillback_duration_s": _stat([r.get("spillback_duration_s") for r in rs]),
        }
        twin = _twin_key(key, groups)
        if twin is not None:
            per, seed_excess = _vs_counterfactual(rs, groups[twin])
            row["vs_no_event"] = {**_per_seed_recovery(per, seed_excess), "per_seed": per}  # n, censored: seeds
        out.append(row)
    return out


def _ev_table(groups: dict) -> list[dict]:
    out = []
    for key, rs in groups.items():
        if not any((r.get("ev_count") or 0) > 0 for r in rs):
            continue
        row = {
            "scenario": rs[0]["scenario"], "controller": rs[0]["variant"], "coverage": key[2], "sampling": key[3],
            "ev_preemption": key[4], "n_seeds": len(rs),
            "ev_count": _stat([r.get("ev_count") for r in rs]),
            "ev_mean_travel_time_s": _stat([r.get("ev_mean_travel_time_s") for r in rs]),
            "ev_mean_delay_s": _stat([r.get("ev_mean_delay_s") for r in rs]),
            "others_mean_delay_s": _stat([r.get("others_mean_delay_s") for r in rs]),
            "ev_extra_delay_others_s": _stat([r.get("ev_extra_delay_others_s") for r in rs]),
        }
        if key[4]:  # preemption on: paired comparison with the same group without preemption, if run
            off = groups.get((key[0], key[1], key[2], key[3], False, key[5]))
            if off:
                ev = paired(_by_seed(off, "ev_mean_travel_time_s"), _by_seed(rs, "ev_mean_travel_time_s"))
                oth = paired(_by_seed(off, "others_mean_delay_s"), _by_seed(rs, "others_mean_delay_s"))
                row["preemption_effect"] = {
                    "n_paired": oth["n"],
                    "ev_travel_time_diff_s": {"mean": _round(ev["diff"]["mean"]), "ci95": _round(ev["diff"]["ci95"])},
                    "others_delay_diff_s": {"mean": _round(oth["diff"]["mean"]), "ci95": _round(oth["diff"]["ci95"])},
                }
        out.append(row)
    return out


def _perf_table(groups: dict) -> list[dict]:
    out = []
    for key, rs in groups.items():
        out.append(
            {
                "scenario": rs[0]["scenario"], "controller": rs[0]["variant"], "coverage": key[2], "sampling": key[3],
                "ev_preemption": key[4], "n_seeds": len(rs),
                **{m: _stat([r.get(m) for r in rs], 2) for m in (
                    "completed", "unfinished", "unfinished_pct", "in_network_at_end", "never_inserted", "teleports",
                    "mean_delay_s", "mean_delay_incl_unfinished_s")},
            }
        )
    return out


def _compute(runs: list[dict], meta: dict) -> dict:
    ok = [r for r in runs if r["status"] == "ok"]
    by_ctrl: dict[str, list] = {}
    for r in ok:
        by_ctrl.setdefault(r["variant"], []).append(r)
    total_bytes = sum(r.get("bytes") or 0 for r in ok)
    sim_s = sum(r.get("sim_time_s") or 0 for r in ok)
    run_wall = sum(r.get("wall_total_s") or r.get("wall_time_s") or 0 for r in ok)
    return {
        "runs_ok": len(ok),
        "runs_failed": sum(r["status"] == "failed" for r in runs),
        "runs_incomplete": sum(r["status"] == "incomplete" for r in runs),
        "experiment_wall_time_s": round(sum(i.get("wall_time_s", 0) for i in meta.get("invocations", [])), 1),
        "sum_run_wall_time_s": round(run_wall, 1),
        "workers": sorted({i.get("workers") for i in meta.get("invocations", [])}),
        "simulated_s": sim_s,
        "sim_speedup": round(sim_s / run_wall, 1) if run_wall else None,
        "mean_run_wall_by_controller_s": {c: _round(sum(r.get("wall_total_s") or r.get("wall_time_s") or 0 for r in rs) / len(rs), 1) for c, rs in sorted(by_ctrl.items())},
        "mean_step_ms_by_controller": {
            c: _round(1000 * sum(r.get("wall_time_s") or 0 for r in rs) / max(1.0, sum(r.get("sim_time_s") or 0 for r in rs)), 2)
            for c, rs in sorted(by_ctrl.items())
        },
        "data_bytes": total_bytes,
        "data_mb_per_run": _round(total_bytes / len(ok) / 1e6, 2) if ok else None,
        "data_mb_per_sim_hour": _round(total_bytes / 1e6 / (sim_s / 3600.0), 2) if sim_s else None,
    }


# --- markdown -----------------------------------------------------------------------
def _fmt(stat: dict | None, digits: int = 1, pct: bool = False) -> str:
    if not stat or stat.get("mean") is None:
        return "–"
    m = f"{stat['mean']:.{digits}f}"
    if stat.get("ci95") is None:
        return m + ("%" if pct else "")
    return f"{m} ± {stat['ci95']:.{digits}f}" + ("%" if pct else "")


def _p(v) -> str:
    if v is None:
        return "–"
    return "<0.001" if v < 0.001 else f"{v:.3f}"


def _table(header: list[str], lines: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in line) + " |" for line in lines]
    return "\n".join(out)


def render_markdown(report: dict) -> str:
    rows = report["rows"]
    m = report["matrix"]
    c = report["compute"]
    sumo = str(report.get("sumo_version") or "?").replace("SUMO ", "")
    lines = [
        f"# Experiment report: `{report['name']}`",
        "",
        f"Created {report['created']} · baseline **{report['baseline']}** · code `{report.get('code_revision')}` · SUMO {sumo}",
        "",
        f"Matrix: scenarios {', '.join(m['scenarios'])} · controllers {', '.join(m['controllers'])} · seeds {m['seeds']} · "
        f"coverage {', '.join(f'{x:g}' for x in m['coverages'])} · sampling {', '.join(m['samplings'])} · "
        f"EV preemption {', '.join('on' if x else 'off' for x in m['ev_preemption'])} · "
        f"warm-up {m.get('warmup_s')} s · run end {', '.join(f'{x:g}' for x in m['end_time']) or 'default'} s",
        "",
    ]
    for w in report.get("warnings") or []:
        lines += [f"**Warning:** {w}.", ""]
    for label, params in (("Scenario parameters", m.get("scenario_params")), ("Controller parameters", m.get("controller_params"))):
        if params:
            lines += [f"{label}: " + " · ".join(f"`{k}` = `{json.dumps(v)}`" for k, v in sorted(params.items())), ""]
    if report.get("commands"):
        lines += ["Reproduce:", "", "```bash", *report["commands"], "```", ""]
    lines += [
        "**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish "
        "(s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. "
        "**Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: "
        "positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. "
        "Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.",
        "",
    ]
    several_ends = len(m["end_time"]) > 1
    for scen in m["scenarios"]:
        srows = [r for r in rows if r["scenario_variant"] == scen]
        lines += [f"## Scenario `{scen}`", ""]
        body = []
        for r in srows:
            mm = r["metrics"]
            body.append([
                f"**{r['variant']}**" if r["is_baseline"] else r["variant"],
                *([f"{r['end_time']:g}" if r.get("end_time") is not None else "–"] if several_ends else []),
                f"{r['coverage']:g}", r["sampling"], "on" if r["ev_preemption"] else "off", r["n_seeds"],
                _fmt(r["mean_delay_s"]),
                "baseline" if r["is_baseline"] else _fmt(r["delta_vs_baseline_pct"], 1, pct=True),
                "–" if r["is_baseline"] else _fmt(r.get("mean_delay_diff_s")),
                _p(r.get("p_holm")), _fmt(r["p95_travel_time_s"]), _fmt(r["stops_per_veh"], 2),
                _fmt(r["unfinished_pct"], 1, pct=True), _fmt(mm["arterial_mean_delay_s"]), _fmt(mm["cross_mean_delay_s"]),
                _fmt(mm["queue_p95_veh"]), _fmt(mm["spillback_duration_s"], 0), _fmt(r["ev_mean_travel_time_s"]),
            ])
        lines.append(_table(
            ["controller", *(["end s"] if several_ends else []), "cov", "sampling", "EV pre", "n", "delay s", "Δ vs base",
             "diff s", "p (Holm)", "p95 TT s", "stops/veh", "unfinished", "arterial delay", "cross delay", "queue p95",
             "spillback s", "EV TT s"],
            body,
        ))
        if any(r.get("baseline_match") == "scenario" for r in srows):
            lines += ["", "_Some rows are paired with a baseline run at another coverage/sampling (fixed-time ignores sensor data)._"]
        if any(r.get("baseline_match") is None for r in srows):
            lines += ["", "_Rows with Δ '–' have no baseline run with the same preemption setting and run end._"]
        lines.append("")
    if report["coverage_sweep"]:
        lines += ["## Coverage sweep (sampling bias)", "",
                  "Queue error = probe queue estimate (halted reports ÷ coverage) − true halted vehicles per approach, "
                  "every 5 s. Bias > 0 overestimates. Adjusted = ÷ measured penetration instead of ÷ coverage.", ""]
        lines.append(_table(
            ["scenario", "controller", "sampling", "coverage", "n", "delay s", "Δ vs base", "queue MAE", "queue bias", "adj. bias", "flow MAE veh/h", "false alarm s"],
            [[s["scenario"], s["controller"], s["sampling"], f"{s['coverage']:g}", s["n_seeds"], _fmt(s["mean_delay_s"]),
              _fmt(s["delta_vs_baseline_pct"], 1, pct=True), _fmt(s["est_queue_mae"], 2), _fmt(s["est_queue_bias"], 2),
              _fmt(s["est_queue_adj_bias"], 2), _fmt(s["est_flow_mae"], 0), _fmt(s["false_alarm_s"], 0)] for s in report["coverage_sweep"]],
        ))
        lines.append("")
    if report["estimation"]:
        lines += ["## Sensor estimation accuracy (all runs pooled)", "",
                  "Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). "
                  "Detector = E2 zone (last 100 m), so it misses queues longer than that.", ""]
        lines.append(_table(
            ["sampling", "coverage", "runs", "probe share", "queue MAE", "queue bias", "bias arterial", "bias cross",
             "adj. bias", "detector MAE", "fused MAE", "flow MAE", "false alarm s"],
            [[e["sampling"], f"{e['coverage']:g}", e["n_runs"], _fmt(e["probe_share"], 3), _fmt(e["est_queue_mae"], 2),
              _fmt(e["est_queue_bias"], 2), _fmt(e["est_queue_bias_arterial"], 2), _fmt(e["est_queue_bias_cross"], 2),
              _fmt(e["est_queue_adj_bias"], 2), _fmt(e["det_queue_mae"], 2), _fmt(e["fused_queue_mae"], 2),
              _fmt(e["est_flow_mae"], 0), _fmt(e["false_alarm_s"], 0)] for e in report["estimation"]],
        ))
        lines.append("")
    if report["emergency"]:
        lines += ["## Emergency vehicles", "",
                  "EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. "
                  "Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest "
                  "(an indication; the clean number is the paired preemption on/off comparison when both were run).", ""]
        body = []
        for e in report["emergency"]:
            eff = e.get("preemption_effect")
            body.append([e["scenario"], e["controller"], f"{e['coverage']:g}", "on" if e["ev_preemption"] else "off", e["n_seeds"],
                         _fmt(e["ev_count"], 1), _fmt(e["ev_mean_travel_time_s"]), _fmt(e["ev_mean_delay_s"]),
                         _fmt(e["others_mean_delay_s"]), _fmt(e["ev_extra_delay_others_s"]),
                         _fmt(eff["ev_travel_time_diff_s"]) if eff else "–", _fmt(eff["others_delay_diff_s"]) if eff else "–"])
        lines.append(_table(["scenario", "controller", "cov", "EV pre", "n", "EVs", "EV TT s", "EV delay s", "others' delay s",
                             "extra delay near EVs s", "EV TT on−off s", "others on−off s"], body))
        lines.append("")
    if report["security"]:
        lines += ["## Fake-data attack and the cross-check", ""]
        lines.append(_table(
            ["scenario", "controller", "cov", "sampling", "n", "detected", "detection delay s", "alert s", "false alarm s", "delay s"],
            [[s["scenario"], s["controller"], f"{s['coverage']:g}", s["sampling"], s["n_seeds"],
              "–" if s["detected_share"] is None else f"{100 * s['detected_share']:.0f}%", _fmt(s["detection_delay_s"]),
              _fmt(s["alert_s"], 0), _fmt(s["false_alarm_s"], 0), _fmt(s["mean_delay_s"])] for s in report["security"]],
        ))
        lines.append("")
    if report["recovery"]:
        lines += ["## Recovery after disruptions", "",
                  "Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its "
                  "pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day "
                  "profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same "
                  "seed and controller run without the event (`--counterfactual`) at the same clock time.", ""]
        body = []
        for s in report["recovery"]:
            cf = s.get("vs_no_event")
            body.append([s["scenario"], s["controller"], f"{s['coverage']:g}", s["n_seeds"], _fmt(s["recovery_time_s"], 0),
                         s["censored"], _fmt(s["excess_delay_veh_h"], 2),
                         _fmt(cf["recovery_s"], 0) if cf else "–", cf["censored"] if cf else "–",
                         _fmt(cf["excess_veh_h"], 2) if cf else "–", _fmt(s["spillback_duration_s"], 0)])
        lines.append(_table(
            ["scenario", "controller", "cov", "n", "recovery s (pre-event)", "censored", "excess veh·h",
             "recovery s (vs no event)", "censored", "excess vs no event veh·h", "spillback s"],
            body,
        ))
        lines.append("")
    lines += ["## PERF-01: completed and unfinished trips", ""]
    lines.append(_table(
        ["scenario", "controller", "cov", "sampling", "EV pre", "n", "completed", "unfinished", "unfinished %", "never inserted",
         "teleports", "delay incl. unfinished s"],
        [[p["scenario"], p["controller"], f"{p['coverage']:g}", p["sampling"], "on" if p["ev_preemption"] else "off", p["n_seeds"],
          _fmt(p["completed"], 0), _fmt(p["unfinished"], 0), _fmt(p["unfinished_pct"], 1), _fmt(p["never_inserted"], 0),
          _fmt(p["teleports"], 1), _fmt(p["mean_delay_incl_unfinished_s"])] for p in report["perf01"]],
    ))
    lines += [
        "",
        "## Compute cost",
        "",
        f"{c['runs_ok']} runs ok, {c['runs_failed']} failed, {c.get('runs_incomplete', 0)} incomplete · experiment wall time {c['experiment_wall_time_s']} s with "
        f"{c['workers']} worker(s) · sum of run wall times {c['sum_run_wall_time_s']} s · "
        f"{c['sim_speedup']}× faster than real time per run · data {c['data_bytes'] / 1e6:.1f} MB "
        f"({c['data_mb_per_run']} MB/run, {c['data_mb_per_sim_hour']} MB per simulated hour).",
        "",
        _table(["controller", "mean wall per run s", "ms per simulated second"],
               [[k, v, c["mean_step_ms_by_controller"].get(k)] for k, v in c["mean_run_wall_by_controller_s"].items()]),
        "",
    ]
    if report["failed_runs"]:
        lines += ["## Failed runs", ""] + [f"- `{f['name']}`: {f['error']}" for f in report["failed_runs"]] + [""]
    if report.get("incomplete_runs"):
        lines += ["## Incomplete runs (not in the statistics)", ""]
        lines += [f"- `{f['name']}`: {f['reason']}" for f in report["incomplete_runs"]] + [""]
    lines += [
        "## Caveats",
        "",
        "- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show "
        "relative differences between controllers under the same demand, not real-world effects.",
        "- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.",
        "- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; "
        "compare unfinished % across controllers.",
        "",
    ]
    return "\n".join(lines)


def write_report(exp_dir: Path, baseline: str = "fixed_time") -> dict:
    exp_dir = Path(exp_dir)
    runs = load_runs(exp_dir)
    write_summary_csv(runs, exp_dir / "summary.csv")
    report = build_report(exp_dir, baseline)
    (exp_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    (exp_dir / "report.md").write_text(render_markdown(report))
    return report
