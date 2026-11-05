"""Independent confirmation for a preselected spillback penalty.

Read only, checks paired run counts, controller failures and predeclared traffic
performance guardrails. The report never silently approves a candidate.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


METRICS = ("mean_delay_s", "unfinished_pct", "completed", "throughput_veh_h",
           "spillback_duration_s", "queue_p95_veh", "ev_mean_travel_time_s")


def mean_ci(deltas: list[float]) -> dict:
    """Two-sided approximate Student t CI for paired differences, n >= 20."""
    n = len(deltas)
    if n < 20:
        raise ValueError("At least 20 paired observations are required")
    avg = statistics.mean(deltas)
    standard_error = statistics.stdev(deltas) / math.sqrt(n)
    df = n - 1
    z = 1.95996398454
    t = z + (z**3 + z) / (4 * df) + (5*z**5 + 16*z**3 + 3*z) / (96*df**2)
    width = t * standard_error
    return {"mean": round(avg, 4), "ci95": [round(avg - width, 4), round(avg + width, 4)]}


def review(folder: Path, *, expected_seeds=range(31, 61)) -> dict:
    folder = Path(folder)
    audit = json.loads((folder / "validation.json").read_text())
    if not audit.get("complete") or audit.get("valid_runs") != 60 or audit.get("expected_runs") != 60:
        raise ValueError(f"strict audit failed for {folder.name}")
    grouped = {}
    problems = []
    for run in (folder / "runs").iterdir():
        if not run.is_dir():
            continue
        spec = json.loads((run / "run_spec.json").read_text())
        summary = json.loads((run / "summary.json").read_text())
        controller, seed = spec["controller"], int(spec["seed"])
        key = (controller, seed)
        if key in grouped:
            problems.append(f"duplicate {key}")
        grouped[key] = (spec, summary)
        if seed not in expected_seeds:
            problems.append(f"unexpected seed {seed}")
        for field in ("controller_errors", "fallback_steps", "rejected_actions"):
            if summary.get(field) != 0:
                problems.append(f"{key}: {field}={summary.get(field)}")
    variants = ("max_pressure", "max_pressure_spillback")
    required = {(controller, seed) for controller in variants for seed in expected_seeds}
    if set(grouped) != required:
        problems.append("paired matrix mismatch")
    pairs = []
    for seed in expected_seeds:
        if all((controller, seed) in grouped for controller in variants):
            bspec, base = grouped[(variants[0], seed)]
            cspec, cand = grouped[(variants[1], seed)]
            if bspec["scenario"] != cspec["scenario"] or bspec["scenario_params"] != cspec["scenario_params"]:
                problems.append(f"seed {seed}: scenario mismatch")
            if bspec.get("controller_params") or cspec.get("controller_params") != {"congestion_threshold": 8, "downstream_penalty": 1.25}:
                problems.append(f"seed {seed}: controller tuning mismatch")
            pairs.append((base, cand))
    if problems:
        raise ValueError("; ".join(problems))
    metrics = {}
    for metric in METRICS:
        values = [(b.get(metric), c.get(metric)) for b, c in pairs]
        vals = [(float(b), float(c)) for b, c in values if type(b) in (float, int) and type(c) in (float, int)
                and math.isfinite(b) and math.isfinite(c)]
        metrics[metric] = ({
            "n": len(vals),
            "baseline_mean": round(statistics.mean(b for b, _ in vals), 4),
            "candidate_mean": round(statistics.mean(c for _, c in vals), 4),
            "candidate_minus_baseline": mean_ci([c - b for b, c in vals]),
        } if len(vals) >= 20 else {"n": len(vals), "available": False})
    delay = metrics["mean_delay_s"]
    unfinished = metrics["unfinished_pct"]
    completed = metrics["completed"]
    has_evs = metrics["ev_mean_travel_time_s"].get("available") is not False
    # These are conservative *screening* conditions, not a formal
    # multiple-comparison-adjusted statistical approval or noninferiority test.
    c_delay = delay["candidate_mean"] <= 1.05 * delay["baseline_mean"]
    c_unfinished = unfinished["candidate_mean"] <= unfinished["baseline_mean"] + 1.0
    c_completed = completed["candidate_mean"] >= .99 * completed["baseline_mean"]
    c_emergency = (not has_evs or
                   metrics["ev_mean_travel_time_s"]["candidate_mean"] <=
                   1.05 * metrics["ev_mean_travel_time_s"]["baseline_mean"])
    return {"experiment": folder.name, "paired_seeds": len(pairs), "metrics": metrics,
            "screens": {"delay_no_gt_5pct_regression": c_delay,
                        "unfinished_no_gt_1pp_regression": c_unfinished,
                        "completed_no_gt_1pct_regression": c_completed,
                        "emergency_no_gt_5pct_regression": c_emergency},
            "passes_directional_screens": all((c_delay, c_unfinished, c_completed, c_emergency)),
            "notes": "Exploratory screening flags only; final decision needs the full statistical review."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("experiments", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [review(folder) for folder in args.experiments]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, indent=2) + "\n")
    for item in reports:
        print(item["experiment"], "paired seeds", item["paired_seeds"], "screens", item["screens"])
        for key in METRICS:
            print(" ", key, item["metrics"][key])
    print("Confirmation evidence generated. No algorithm approved automatically.")


if __name__ == "__main__":
    main()
