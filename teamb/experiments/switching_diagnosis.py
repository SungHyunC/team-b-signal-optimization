"""Explore phase switching and network queues in the existing controller pilot.

Read-only. Aggregates time-series and signal events by the road closure's event
window; not a link-level or causal explanation of spillback.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def diagnose(root: Path) -> dict:
    results = defaultdict(lambda: defaultdict(list))
    for run in sorted((root / "runs").glob("*")):
        if not run.is_dir():
            continue
        try:
            spec = json.loads((run / "run_spec.json").read_text())
            summary = json.loads((run / "summary.json").read_text())
            with (run / "timeseries.csv").open(newline="") as f:
                series = list(csv.DictReader(f))
            with (run / "signal_events.csv").open(newline="") as f:
                events = list(csv.DictReader(f))
        except (OSError, ValueError, KeyError) as exc:
            raise ValueError(f"{run.name}: missing or malformed pilot outputs: {exc}") from exc
        key = spec["controller"]
        for label, lo, hi in (("before_closure", 900, 1500),
                               ("during_closure", 1500, 3300),
                               ("after_reopening", 3300, float("inf"))):
            samples = [x for x in series if lo <= float(x["t"]) < hi and x["in_window"] == "1"]
            changes = [e for e in events if lo <= float(e["t"]) < hi and e["reason"] == "switch"]
            values = {
                "max_queue_veh": statistics.mean(float(x["max_queue"]) for x in samples) if samples else None,
                "halting_veh": statistics.mean(float(x["halting"]) for x in samples) if samples else None,
                "delay_rate": statistics.mean(float(x["delay_rate"]) for x in samples) if samples else None,
                "confirmed_spillback_samples": sum(int(x["spillback_links"]) > 0 for x in samples),
                "signal_switch_events": len(changes),
            }
            for metric, value in values.items():
                if value is not None:
                    results[key][f"{label}__{metric}"].append(value)
        for metric in ("completed", "unfinished_pct", "mean_delay_s", "spillback_duration_s",
                       "signal_switches", "controller_errors", "fallback_steps", "rejected_actions"):
            value = summary.get(metric)
            if isinstance(value, (float, int)):
                results[key][metric].append(value)
    return {c: {"n_runs": len(next(iter(ms.values()))) if ms else 0,
                "means": {m: round(statistics.mean(vals), 3) for m, vals in sorted(ms.items())}}
            for c, ms in sorted(results.items())}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("experiment", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = diagnose(args.experiment)
    if not result:
        raise SystemExit("No pilot runs found")
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
