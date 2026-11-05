"""Read-only diagnosis of paired controller runs from a SUMO experiment folder.

Usage:
    python -m teamb.experiments.diagnose results/experiments/robustness_high --output diagnosis.json
Requires only the Python standard library. Does not alter simulation outputs.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

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
    """Mean difference and approximate two-sided 95% Student-t interval."""
    n = len(values)
    if n < 2:
        return {"n": n, "mean": _mean(values), "ci95": None}
    mean = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(n)
    # Cornish-Fisher expansion of t(.975, df); accurate for n >= 10.
    df = n - 1
    z = 1.959963984540054
    t = z + (z**3 + z) / (4 * df) + (5*z**5 + 16*z**3 + 3*z) / (96*df**2)
    hw = t * se
    return {"n": n, "mean": round(mean, 4), "ci95": [round(mean-hw, 4), round(mean+hw, 4)]}


def load_runs(folder):
    runs = {}
    issues = []
    for d in sorted((Path(folder) / "runs").glob("*")):
        if not d.is_dir():
            continue
        try:
            spec = json.loads((d / "run_spec.json").read_text())
            summary = json.loads((d / "summary.json").read_text())
            manifest = json.loads((d / "manifest.json").read_text())
            key = (spec["scenario"], spec["controller"], int(spec["seed"]))
            if key in runs:
                issues.append(f"duplicate scenario/controller/seed {key}")
            else:
                runs[key] = {"spec": spec, "summary": summary, "manifest": manifest}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            issues.append(f"{d.name}: {exc}")
    return runs, issues


def diagnose(folder, *, baseline="fixed_time", candidate="max_pressure"):
    runs, issues = load_runs(folder)
    results = {"experiment": Path(folder).name, "run_count": len(runs),
               "issues": issues, "scenarios": {}}
    scenarios = sorted({key[0] for key in runs})
    for scenario in scenarios:
        baseline_seeds = {k[2] for k in runs if k[0] == scenario and k[1] == baseline}
        candidate_seeds = {k[2] for k in runs if k[0] == scenario and k[1] == candidate}
        paired = sorted(baseline_seeds & candidate_seeds)
        warnings = []
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
                a = _number(runs[(scenario, baseline, seed)]["summary"].get(metric))
                b = _number(runs[(scenario, candidate, seed)]["summary"].get(metric))
                if a is not None and b is not None:
                    bp.append(a)
                    cp.append(b)
                    differences.append(b - a)
            metric_summary[metric] = {"baseline_mean": _mean(bp), "candidate_mean": _mean(cp),
                                      "candidate_minus_baseline": _ci(differences)}
        provenance = Counter()
        spillback = defaultdict(float)
        for seed in paired:
            a = runs[(scenario, baseline, seed)]
            b = runs[(scenario, candidate, seed)]
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
        results["scenarios"][scenario] = {"paired_seeds": len(paired), "warnings": warnings,
                                          "metrics": metric_summary, "spillback_hotspots": hotspots}
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description="Read-only SUMO controller failure diagnosis")
    p.add_argument("experiment", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    report = diagnose(args.experiment)
    body = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body + "\n")
    print(body)
    return 0 if report["run_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
