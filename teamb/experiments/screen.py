"""Prespecified regression screen: may a candidate controller replace a baseline?

    teamb exp screen --name confirm --baseline max_pressure --candidate max_pressure-1a2b3c

This is the decision rule the team applied by hand in docs/independent-controller-confirmation-review.md,
as code. For every condition (scenario variant x coverage x sampling x preemption x run end) where both
controllers ran on the same seeds, it computes paired differences (candidate - baseline) with 95 %
t-intervals and checks these guards:

  delay       relative change of the mean completed-trip delay <= +max_delay_regression % (default 5)
  throughput  mean increase of the unfinished share <= max_unfinished_pp percentage points (default 0.5),
              and no significant increase above 0.1 pp (lower 95 % bound <= 0.1 pp)
  emergency   emergency-vehicle travel time not significantly higher by more than 1 s
              (lower 95 % bound of the increase <= 1 s), no seed with more EVs that never arrived
              (ev_unfinished) and no seed where no EV arrived while the baseline's did; travel
              time covers arrived EVs only, so a stranded EV would otherwise look like a faster one
              (scenarios with EVs only)
  safety      no controller errors, fallback steps or rejected actions in any candidate run, and
              every candidate run finished: no failed or incomplete run (error.json, truncated
              summary) and no seed the baseline finished but the candidate has no run for (a run
              lost on the cloud backend or by a dead worker leaves no folder)

A condition where both controllers ran is listed even when the candidate has fewer than min_seeds
(default 2) finished seeds paired with the baseline: it then fails the "seeds" guard instead of
silently dropping out of the verdict. The verdict is PASS only if every guard passes in every
condition. Benefits are reported next to the guards (significant improvements in delay, delay incl.
entry waits, spillback, queue p95) but never override a failed guard. Intervals are not adjusted for
the number of conditions.

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
    "ev_unfinished": "EVs not arrived",
}
BENEFITS = ("mean_delay_s", "mean_delay_incl_depart_s", "spillback_duration_s", "queue_p95_veh")
SAFETY = ("controller_errors", "fallback_steps", "rejected_actions")
BROKEN = ("failed", "incomplete")  # runner.run_status of a run that did not finish
PRACTICAL_UNFINISHED_PP = 0.1  # a significant but smaller increase is negligible
PRACTICAL_EV_S = 1.0


def _ci(stat: dict) -> tuple[float | None, float | None]:
    m, h = stat["diff"]["mean"], stat["diff"]["ci95"]
    if m is None:
        return None, None
    return (m - h, m + h) if h is not None else (m, m)


def _has_evs(runs: list[dict]) -> bool:
    return any((r.get("ev_count") or 0) > 0 or (r.get("ev_unfinished") or 0) > 0
               or r.get("ev_mean_travel_time_s") is not None for r in runs)


def _emergency_guard(stats: dict, base_runs: list[dict], cand_runs: list[dict]) -> dict:
    """EV travel time of the arrived EVs, plus the EVs that never arrived, seed by seed."""
    ev = stats["ev_mean_travel_time_s"]
    lo, _ = _ci(ev)
    base = {r["seed"]: r for r in base_runs}
    more_unfinished, none_arrived = [], []
    for r in cand_runs:
        b = base.get(r["seed"])
        if b is None:
            continue
        if (r.get("ev_unfinished") or 0) > (b.get("ev_unfinished") or 0):
            more_unfinished.append(r["seed"])
        if b.get("ev_mean_travel_time_s") is not None and r.get("ev_mean_travel_time_s") is None:
            none_arrived.append(r["seed"])
    return {
        "pass": not more_unfinished and not none_arrived and (lo is None or lo <= PRACTICAL_EV_S),
        "increase_s": ev["diff"]["mean"], "ci95": _ci(ev),
        "unfinished_increase": stats["ev_unfinished"]["diff"]["mean"],
        "more_unfinished_seeds": sorted(more_unfinished), "no_ev_arrived_seeds": sorted(none_arrived),
    }


def _broken_runs(all_runs: list[dict]) -> dict[tuple, list[dict]]:
    """Failed and incomplete runs by group key (runs whose identity cannot be read are left out)."""
    broken: dict[tuple, list[dict]] = {}
    for r in all_runs:
        if r["status"] not in BROKEN:
            continue
        try:
            key = _group_key(r)
        except (KeyError, TypeError, ValueError):
            continue
        broken.setdefault(key, []).append(r)
    return broken


def screen(exp_dir: Path, baseline: str, candidate: str, *, max_delay_regression: float = 5.0,
           max_unfinished_pp: float = 0.5, min_seeds: int = 2) -> dict:
    all_runs = load_runs(exp_dir)
    runs, _ = _one_run_per_seed([r for r in all_runs if r["status"] == "ok"])
    groups: dict[tuple, list[dict]] = {}
    for r in runs:
        groups.setdefault(_group_key(r), []).append(r)
    broken = _broken_runs(all_runs)
    conditions = []
    cand_keys = {k for k in (*groups, *broken) if k[1] == candidate}
    for key in sorted(cand_keys, key=lambda k: tuple(str(x) for x in k)):
        base_key = (key[0], baseline, *key[2:])
        if base_key not in groups and base_key not in broken:
            continue  # the baseline never ran this condition: nothing to compare with
        base_runs, cand_runs = groups.get(base_key, []), groups.get(key, [])
        stats = {}
        for metric in METRICS:
            b = {r["seed"]: r.get(metric) for r in base_runs}
            c = {r["seed"]: r.get(metric) for r in cand_runs}
            stats[metric] = paired(b, c)
        d = stats["mean_delay_s"]
        n = d["n"]
        guards = {}
        if n < min_seeds:
            guards["seeds"] = {"pass": False, "n": n, "min": min_seeds}
        else:
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
            if _has_evs(base_runs + cand_runs):
                guards["emergency"] = _emergency_guard(stats, base_runs, cand_runs)
        bad = [r["name"] for r in cand_runs if any((r.get(k) or 0) != 0 for k in SAFETY)]
        ok_seeds = {r["seed"] for r in cand_runs}
        # a failed folder next to a finished run of the same seed (e.g. under an older name) is history
        failed = sorted(({"name": r["name"], "seed": r["seed"], "status": r["status"], "error": r["error"]}
                         for r in broken.get(key, []) if r["seed"] not in ok_seeds),
                        key=lambda r: (str(r["seed"]), r["name"]))
        missing = sorted({r["seed"] for r in base_runs} - ok_seeds - {r["seed"] for r in failed}, key=str)
        guards["safety"] = {"pass": not bad and not failed and not missing, "runs_with_issues": bad,
                            "failed_runs": failed, "missing_seeds": missing}
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
        f"and not significantly above +{PRACTICAL_UNFINISHED_PP} pp, EV travel time not significantly above +{PRACTICAL_EV_S:g} s "
        "and no more EVs left unarrived on any seed, no safety events, every candidate run finished, "
        f"at least {result['rules']['min_seeds']} paired seeds per condition. "
        "Paired 95 % t-intervals, not adjusted for the number of conditions.",
        "",
        "| Scenario | Demand / params | Seeds | Baseline delay | Candidate delay | Change | Unfinished Δ pp [95 % CI] "
        "| EV Δ s | EVs not arrived Δ | Benefits | Result |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---|---|",
    ]
    for c in result["conditions"]:
        d = c["metrics"].get("mean_delay_s", {})
        g = c["guards"]
        u = g.get("throughput")
        ev = g.get("emergency")
        unfinished = f"{_num(u['increase_pp'])} [{_num(u['ci95'][0])}, {_num(u['ci95'][1])}]" if u else "–"
        change = f"{_num(g['delay']['change_pct'], 1)} %" if "delay" in g else "–"
        result_text = "PASS" if c["pass"] else "FAIL: " + ", ".join(k for k, v in g.items() if not v["pass"])
        lines.append(
            f"| {c['scenario']} | cov {c['coverage']:g}, end {_num(c['end_time'], 0)} | {c['n_seeds']} | "
            f"{_num(d.get('baseline'))} | {_num(d.get('candidate'))} | {change} | {unfinished} | "
            f"{_num(ev['increase_s']) if ev else '–'} | {_num(ev['unfinished_increase']) if ev else '–'} | "
            f"{', '.join(c['significant_benefits']) or '–'} | {result_text} |"
        )
    problems = []
    for c in result["conditions"]:
        safety = c["guards"]["safety"]
        where = f"{c['scenario']} (cov {c['coverage']:g}, end {_num(c['end_time'], 0)})"
        problems += [f"- {where}: `{r['name']}` {r['status']}: {r['error'] or 'no reason recorded'}" for r in safety["failed_runs"]]
        if safety["missing_seeds"]:
            problems.append(f"- {where}: no candidate run for seed(s) {', '.join(str(x) for x in safety['missing_seeds'])} "
                            "that the baseline finished")
    if problems:
        lines += ["", "## Failed / incomplete candidate runs", "",
                  "These fail the safety guard: re-run them (`teamb exp run` resumes only the missing runs).", "", *problems]
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
