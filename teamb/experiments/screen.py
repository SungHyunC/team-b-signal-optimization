"""Prespecified regression screen: may a candidate controller replace a baseline?

    teamb exp screen --name confirm --baseline max_pressure --candidate max_pressure-1a2b3c

This is the decision rule the team applied by hand in docs/independent-controller-confirmation-review.md,
as code. For every condition (scenario variant x coverage x sampling x preemption x run end) where both
controllers ran on the same seeds, it computes paired differences (candidate - baseline) with 95 %
t-intervals and checks four guards:

  delay       relative change of the mean completed-trip delay <= +max_delay_regression % (default 5)
  throughput  mean increase of the unfinished share <= max_unfinished_pp percentage points (default 0.5),
              and no significant increase above 0.1 pp (lower 95 % bound <= 0.1 pp)
  emergency   emergency-vehicle travel time not significantly higher by more than 1 s
              (lower 95 % bound of the increase <= 1 s; scenarios with EVs only)
  safety      no controller errors, fallback steps or rejected actions in any candidate run

The verdict is PASS only if every guard passes in every condition. Benefits are reported next to the
guards (significant improvements in delay, delay incl. entry waits, spillback, queue p95) but never
override a failed guard. Intervals are not adjusted for the number of conditions.

Writes screen.json and screen.md into the experiment folder.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from teamb.evaluation.stats import paired
from teamb.experiments.analysis import _group_key, _one_run_per_seed, load_runs
from teamb.fsutil import atomic_write_json, atomic_write_text

# metric -> (label, lower is better)
METRICS = {
    "mean_delay_s": "delay (s/veh)",
    "mean_delay_incl_depart_s": "delay incl. entry wait (s/veh)",
    "unfinished_pct": "unfinished (%)",
    "completed": "completed trips",
    "spillback_duration_s": "confirmed spillback (s)",
    "queue_p95_veh": "queue p95 (veh)",
    "ev_mean_travel_time_s": "EV travel time (s)",
}
BENEFITS = ("mean_delay_s", "mean_delay_incl_depart_s", "spillback_duration_s", "queue_p95_veh")
SAFETY = ("controller_errors", "fallback_steps", "rejected_actions")
PRACTICAL_UNFINISHED_PP = 0.1  # a significant but smaller increase is negligible
PRACTICAL_EV_S = 1.0


def _ci(stat: dict) -> tuple[float | None, float | None]:
    m, h = stat["diff"]["mean"], stat["diff"]["ci95"]
    if m is None:
        return None, None
    return (m - h, m + h) if h is not None else (m, m)


def screen(exp_dir: Path, baseline: str, candidate: str, *, max_delay_regression: float = 5.0,
           max_unfinished_pp: float = 0.5, min_seeds: int = 2) -> dict:
    runs, _ = _one_run_per_seed([r for r in load_runs(exp_dir) if r["status"] == "ok"])
    groups: dict[tuple, list[dict]] = {}
    for r in runs:
        groups.setdefault(_group_key(r), []).append(r)
    conditions = []
    for key, cand_runs in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        if key[1] != candidate:
            continue
        base_key = (key[0], baseline, *key[2:])
        base_runs = groups.get(base_key)
        if not base_runs:
            continue
        stats = {}
        for metric in METRICS:
            b = {r["seed"]: r.get(metric) for r in base_runs}
            c = {r["seed"]: r.get(metric) for r in cand_runs}
            stats[metric] = paired(b, c)
        n = stats["mean_delay_s"]["n"]
        if n < min_seeds:
            continue
        guards = {}
        d = stats["mean_delay_s"]
        rel = None
        if d["baseline_mean"]:
            rel = 100.0 * (d["candidate_mean"] - d["baseline_mean"]) / d["baseline_mean"]
        guards["delay"] = {"pass": rel is not None and rel <= max_delay_regression, "change_pct": rel}
        u = stats["unfinished_pct"]
        lo, _ = _ci(u)
        guards["throughput"] = {
            "pass": u["n"] > 0 and (lo is None or lo <= PRACTICAL_UNFINISHED_PP) and (u["diff"]["mean"] or 0.0) <= max_unfinished_pp,
            "increase_pp": u["diff"]["mean"], "ci95": _ci(u),
        }
        ev = stats["ev_mean_travel_time_s"]
        if ev["n"]:
            lo, _ = _ci(ev)
            guards["emergency"] = {"pass": lo is None or lo <= PRACTICAL_EV_S, "increase_s": ev["diff"]["mean"], "ci95": _ci(ev)}
        bad = [r["name"] for r in cand_runs if any((r.get(k) or 0) != 0 for k in SAFETY)]
        guards["safety"] = {"pass": not bad, "runs_with_issues": bad}
        benefits = []
        for metric in BENEFITS:
            _, hi = _ci(stats[metric])
            if stats[metric]["n"] and hi is not None and hi < 0:
                benefits.append(metric)
        conditions.append({
            "scenario": key[0], "coverage": key[2], "sampling": key[3], "ev_preemption": key[4], "end_time": key[5],
            "n_seeds": n, "seeds": d["seeds"], "pass": all(g["pass"] for g in guards.values()),
            "guards": guards, "significant_benefits": benefits,
            "metrics": {m: {"baseline": s["baseline_mean"], "candidate": s["candidate_mean"], "diff": s["diff"]["mean"],
                            "ci95": _ci(s), "p": s["p_value"], "n": s["n"]} for m, s in stats.items() if s["n"]},
        })
    verdict = "PASS" if conditions and all(c["pass"] for c in conditions) else ("NO DATA" if not conditions else "FAIL")
    return {
        "experiment": Path(exp_dir).name, "baseline": baseline, "candidate": candidate, "verdict": verdict,
        "rules": {"max_delay_regression_pct": max_delay_regression, "max_unfinished_pp": max_unfinished_pp,
                  "practical_unfinished_pp": PRACTICAL_UNFINISHED_PP, "practical_ev_s": PRACTICAL_EV_S,
                  "ci": "paired t, 95 %, unadjusted for multiple conditions", "min_seeds": min_seeds},
        "conditions": conditions,
    }


def _num(v, digits=2) -> str:
    return "–" if v is None else f"{v:.{digits}f}"


def render_markdown(result: dict) -> str:
    lines = [
        f"# Regression screen: `{result['candidate']}` vs `{result['baseline']}`",
        "",
        f"Experiment `{result['experiment']}` · verdict **{result['verdict']}** · rules: delay regression ≤ "
        f"+{result['rules']['max_delay_regression_pct']} %, unfinished share ≤ +{result['rules']['max_unfinished_pp']} pp "
        f"and not significantly above +{PRACTICAL_UNFINISHED_PP} pp, EV travel time not significantly above +{PRACTICAL_EV_S:g} s, "
        "no safety events. "
        "Paired 95 % t-intervals, not adjusted for the number of conditions.",
        "",
        "| Scenario | Demand / params | Seeds | Baseline delay | Candidate delay | Change | Unfinished Δ pp [95 % CI] | EV Δ s | Benefits | Result |",
        "|---|---|---:|---:|---:|---:|---|---:|---|---|",
    ]
    for c in result["conditions"]:
        d = c["metrics"]["mean_delay_s"]
        g = c["guards"]
        u = g["throughput"]
        ev = g.get("emergency")
        ci = u["ci95"]
        lines.append(
            f"| {c['scenario']} | cov {c['coverage']:g}, end {_num(c['end_time'], 0)} | {c['n_seeds']} | {_num(d['baseline'])} | "
            f"{_num(d['candidate'])} | {_num(g['delay']['change_pct'], 1)} % | {_num(u['increase_pp'])} "
            f"[{_num(ci[0])}, {_num(ci[1])}] | {_num(ev['increase_s']) if ev else '–'} | "
            f"{', '.join(c['significant_benefits']) or '–'} | {'PASS' if c['pass'] else 'FAIL: ' + ', '.join(k for k, v in g.items() if not v['pass'])} |"
        )
    lines += ["", "Scenario names with a `-<hash>` suffix carry scenario parameters (e.g. demand_scale); see experiment.json."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from teamb.experiments.runner import EXPERIMENTS_DIR

    p = argparse.ArgumentParser(prog="teamb exp screen", description=__doc__.split("\n\n")[0])
    p.add_argument("--name", required=True, help="experiment folder under results/experiments/")
    p.add_argument("--baseline", required=True, help="baseline controller variant, e.g. max_pressure")
    p.add_argument("--candidate", required=True, help="candidate variant, e.g. max_pressure-1a2b3c (see report.md)")
    p.add_argument("--max-delay-regression", type=float, default=5.0, help="allowed relative delay increase, %%")
    p.add_argument("--max-unfinished-pp", type=float, default=0.5, help="allowed mean increase of the unfinished share, pp")
    args = p.parse_args(argv)
    exp_dir = EXPERIMENTS_DIR / args.name
    result = screen(exp_dir, args.baseline, args.candidate, max_delay_regression=args.max_delay_regression,
                    max_unfinished_pp=args.max_unfinished_pp)
    atomic_write_json(exp_dir / "screen.json", result)
    md = render_markdown(result)
    atomic_write_text(exp_dir / "screen.md", md)
    print(md)
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
