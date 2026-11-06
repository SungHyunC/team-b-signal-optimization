"""Read-only diagnosis of paired controller runs from a SUMO experiment folder.

Usage:
    python -m teamb.experiments.diagnose results/experiments/robustness_high --output diagnosis.json
    python -m teamb.experiments.diagnose results/experiments/sample --baseline fixed_time --candidate coordinated

Runs are compared per condition (scenario variant, coverage, sampling, preemption, end time),
never across them: counterfactual twins, coverage sweeps and preemption on/off are reported as
separate entries of "scenarios" (keyed by the scenario name plus any non-default dimension).
Requires only the Python standard library (teamb.evaluation.stats is stdlib-only). Does not
alter simulation outputs.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from teamb.evaluation.stats import mean_ci
from teamb.fsutil import atomic_write_text

METRICS = (
    "mean_delay_s", "mean_delay_incl_unfinished_s", "unfinished_pct",
    "completed", "never_inserted", "throughput_veh_h",
    "p95_travel_time_s", "queue_p95_veh", "queue_warning_s",
    "spillback_duration_s", "spillback_events", "ev_mean_travel_time_s",
    "recovery_time_s",
)


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value)


def _mean(values):
    vals = [v for v in values if v is not None]
    return round(statistics.mean(vals), 4) if vals else None


def _ci(values):
    """Mean difference and its two-sided 95 % Student-t interval [low, high].

    Same t quantiles as the experiment report and the impact analysis (stats.mean_ci)."""
    s = mean_ci(values)
    if s["ci95"] is None:
        return {"n": s["n"], "mean": _mean(values), "ci95": None}
    mean, hw = s["mean"], s["ci95"]
    return {"n": s["n"], "mean": round(mean, 4), "ci95": [round(mean - hw, 4), round(mean + hw, 4)]}


def _token(x: float) -> str:
    return str(int(round(x))) if abs(x - round(x)) < 1e-9 else f"{x:.10g}"


def _condition(spec: dict, folder: Path) -> tuple:
    """(scenario variant, coverage, sampling, preemption, end time): what must match for two runs
    to be a paired comparison. Counterfactual twins and --scenario-params runs are their own
    scenario variant ('<scenario>-<hash>', the run folder's first segment, as in analysis.py)."""
    scen = folder.name.split("__")[0] if spec.get("scenario_params") else spec["scenario"]
    cov = spec.get("coverage")
    end = spec.get("end_time")
    return (scen, 1.0 if cov is None else float(cov), spec.get("sampling") or "uniform",
            bool(spec.get("ev_preemption", True)), None if end is None else float(end))


def condition_label(cond: tuple) -> str:
    """The scenario variant, plus every dimension that differs from the default:
    'emergency', 'emergency/c10/approach_biased-2/nopre/e2700'."""
    scen, cov, sampling, pre, end = cond
    parts = [scen]
    if cov != 1.0:
        parts.append(f"c{_token(cov * 100)}")
    if sampling != "uniform":
        parts.append(sampling.replace(":", "-"))
    if not pre:
        parts.append("nopre")
    if end is not None:
        parts.append(f"e{_token(end)}")
    return "/".join(parts)


def load_runs(folder):
    """{(condition, controller variant, seed): run} for every finished run, plus issues.

    Failed or incomplete runs (runner.run_status) are skipped with an issue; only two folders of
    the same condition, controller variant and seed are a duplicate."""
    from teamb.experiments.runner import run_status

    runs = {}
    issues = []
    for d in sorted((Path(folder) / "runs").glob("*")):
        if not d.is_dir():
            continue
        try:
            spec = json.loads((d / "run_spec.json").read_text())
            status, _, reason = run_status(d, expected_end=spec.get("end_time"))
            if status != "ok":
                issues.append(f"{d.name}: {status} run skipped ({reason})")
                continue
            summary = json.loads((d / "summary.json").read_text())
            manifest = json.loads((d / "manifest.json").read_text())
            key = (_condition(spec, d), spec.get("variant") or spec["controller"], int(spec["seed"]))
            if key in runs:
                issues.append(f"duplicate run {d.name} for {condition_label(key[0])}/{key[1]}/seed {key[2]} "
                              f"(kept {runs[key]['dir']})")
            else:
                runs[key] = {"spec": spec, "summary": summary, "manifest": manifest, "dir": d.name}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            issues.append(f"{d.name}: {exc}")
    return runs, issues


def _baseline_condition(cond: tuple, baseline_conds: set) -> tuple[tuple | None, str | None]:
    """The baseline's condition for a candidate condition, as analysis._find_baseline: the same
    one, else the same scenario variant, preemption and end time at another coverage/sampling
    (fixed-time ignores sensor data), preferring coverage 1.0 and uniform sampling."""
    if cond in baseline_conds:
        return cond, None
    same = [c for c in baseline_conds if c[0] == cond[0] and c[3] == cond[3] and c[4] == cond[4]]
    if not same:
        return None, None
    same.sort(key=lambda c: (c[1] != 1.0, c[2] != "uniform", -c[1]))
    return same[0], f"baseline from another coverage/sampling: {condition_label(same[0])}"


def diagnose(folder, *, baseline="fixed_time", candidate="max_pressure"):
    """Paired baseline-vs-candidate diagnosis per condition (results["scenarios"][label]).

    A condition is (scenario variant, coverage, sampling, preemption, end time); its label is the
    scenario name when everything else is the default, so a plain experiment reports one entry
    per scenario."""
    runs, issues = load_runs(folder)
    results = {"experiment": Path(folder).name, "run_count": len(runs), "baseline": baseline, "candidate": candidate,
               "issues": issues, "scenarios": {}}
    base_conds = {k[0] for k in runs if k[1] == baseline}
    cand_conds = {k[0] for k in runs if k[1] == candidate}
    plan = []
    used = set()
    for cond in sorted(cand_conds, key=condition_label):
        b, note = _baseline_condition(cond, base_conds)
        plan.append((cond, b, note))
        used.add(b)
    plan += [(b, b, None) for b in sorted(base_conds - used, key=condition_label) if b not in cand_conds]
    for cond, bcond, note in sorted(plan, key=lambda x: condition_label(x[0])):
        baseline_seeds = {k[2] for k in runs if k[0] == bcond and k[1] == baseline} if bcond is not None else set()
        candidate_seeds = {k[2] for k in runs if k[0] == cond and k[1] == candidate}
        paired = sorted(baseline_seeds & candidate_seeds)
        warnings = [note] if note else []
        if baseline_seeds != candidate_seeds:
            warnings.append("unpaired seeds: " + str(sorted(baseline_seeds ^ candidate_seeds)))
        if not paired:
            warnings.append("no paired observations")
        metric_summary = {}
        for metric in METRICS:
            bp = []
            cp = []
            differences = []
            for seed in paired:
                a = _number(runs[(bcond, baseline, seed)]["summary"].get(metric))
                b = _number(runs[(cond, candidate, seed)]["summary"].get(metric))
                if a is not None and b is not None:
                    bp.append(a)
                    cp.append(b)
                    differences.append(b - a)
            metric_summary[metric] = {"baseline_mean": _mean(bp), "candidate_mean": _mean(cp),
                                      "candidate_minus_baseline": _ci(differences)}
        provenance = Counter()
        spillback = defaultdict(float)
        for seed in paired:
            a = runs[(bcond, baseline, seed)]
            b = runs[(cond, candidate, seed)]
            for field in ("code_revision", "sumo_version", "network_hash", "seed"):
                if a["manifest"].get(field) != b["manifest"].get(field):
                    provenance[field] += 1
            # The route demand hash should be identical for matched seeds if demand
            # is controller-independent. A mismatch is a warning, not silent acceptance.
            if a["manifest"].get("demand_hash") != b["manifest"].get("demand_hash"):
                provenance["demand_hash"] += 1
            for ctrl, item in ((baseline, a), (candidate, b)):
                for edge, seconds in (item["summary"].get("spillback_by_link") or {}).items():
                    if _number(seconds) is not None:
                        spillback[(ctrl, edge)] += float(seconds)
        for field, count in sorted(provenance.items()):
            warnings.append(f"{field} differs in {count} paired seeds")
        hotspots = {ctrl: sorted(
            ({"edge": edge, "mean_spillback_s": round(total/max(1,len(paired)), 2)}
             for (who, edge), total in spillback.items() if who == ctrl),
            key=lambda item: -item["mean_spillback_s"])[:8]
            for ctrl in (baseline, candidate)}
        scen, cov, sampling, pre, end = cond
        results["scenarios"][condition_label(cond)] = {
            "paired_seeds": len(paired), "warnings": warnings, "metrics": metric_summary,
            "spillback_hotspots": hotspots,
            "condition": {"scenario": scen, "coverage": cov, "sampling": sampling, "ev_preemption": pre, "end_time": end},
            "baseline_condition": None if bcond is None else condition_label(bcond),
        }
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description="Read-only SUMO controller failure diagnosis")
    p.add_argument("experiment", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--baseline", default="fixed_time", help="baseline controller variant (default: fixed_time)")
    p.add_argument("--candidate", default="max_pressure", help="candidate controller variant (default: max_pressure)")
    args = p.parse_args(argv)
    report = diagnose(args.experiment, baseline=args.baseline, candidate=args.candidate)
    body = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        atomic_write_text(args.output, body + "\n")
    print(body)
    return 0 if report["run_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
