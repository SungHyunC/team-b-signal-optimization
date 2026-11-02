"""How good are the sensor estimates? Probe / detector / fused numbers vs SUMO ground truth.

For a list of (estimate e_i, truth y_i) pairs (one per approach and 5-s sample):

    error   err_i = e_i - y_i
    MAE     mean |err_i|                 typical size of the mistake, in vehicles (or veh/h)
    RMSE    sqrt(mean err_i^2)           like MAE but punishes big mistakes more
    bias    mean err_i                   > 0: overestimates on average, < 0: underestimates
    nMAE    MAE / mean y_i               MAE relative to the typical true value

Quantities (columns of estimation.csv, see teamb/sensors/logs.py):
    queue  truth = halted vehicles on the whole approach
           probe      = halted probe reports / coverage        (the contract's queue_est)
           probe_adj  = halted probe reports / estimated penetration
           detector   = E2 halting count (last 100 m only, so it misses long queues)
           fused      = detector, extended by trusted probes when the detector zone is full
    flow   truth = vehicles crossing the stop line (last 5 min, veh/h)
           probe      = probe crossings / coverage
           detector   = E1 loop count

Approach-seconds under a fake-data attack are left out: there the "error" is the attack,
which the cross-check metrics measure instead.
"""
from __future__ import annotations

import math

from teamb.sensors.logs import ESTIMATION_COLUMNS

COL = {name: i for i, name in enumerate(ESTIMATION_COLUMNS)}
QUEUE_SOURCES = {"probe": "probe_queue_est", "probe_adj": "probe_queue_adj", "detector": "det_queue", "fused": "fused_queue"}
FLOW_SOURCES = {"probe": "probe_flow_est_vph", "detector": "det_flow_vph"}


def error_stats(estimates: list[float], truths: list[float]) -> dict:
    n = len(estimates)
    if n == 0:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "nmae": None}
    errs = [e - y for e, y in zip(estimates, truths)]
    mae = sum(abs(x) for x in errs) / n
    mean_truth = sum(truths) / n
    return {
        "n": n,
        "mae": round(mae, 3),
        "rmse": round(math.sqrt(sum(x * x for x in errs) / n), 3),
        "bias": round(sum(errs) / n, 3),
        "nmae": round(mae / mean_truth, 3) if mean_truth > 0 else None,
    }


def _group_stats(rows: list[tuple]) -> dict:
    tq, tf = COL["true_queue"], COL["true_flow_vph"]
    out = {"queue": {}, "flow": {}}
    for name, col in QUEUE_SOURCES.items():
        out["queue"][name] = error_stats([float(r[COL[col]]) for r in rows], [float(r[tq]) for r in rows])
    for name, col in FLOW_SOURCES.items():
        out["flow"][name] = error_stats([float(r[COL[col]]) for r in rows], [float(r[tf]) for r in rows])
    return out


def summarize_estimation(rows: list[tuple], t_min: float = 0.0, t_max: float | None = None) -> dict:
    """Error statistics overall, by approach kind (arterial/cross) and by approach (J1.W ...)."""
    t, att = COL["t"], COL["attacked"]
    use = [r for r in rows if r[t] >= t_min and (t_max is None or r[t] <= t_max) and not r[att]]
    result = {"samples": len(use), "excluded_attacked": sum(1 for r in rows if r[att]), **_group_stats(use)}
    kinds: dict[str, list] = {}
    approaches: dict[str, list] = {}
    for r in use:
        kinds.setdefault(r[COL["kind"]], []).append(r)
        approaches.setdefault(f"{r[COL['junction']]}.{r[COL['approach']]}", []).append(r)
    result["by_kind"] = {k: _group_stats(v) for k, v in sorted(kinds.items())}
    result["by_approach"] = {k: _group_stats(v) for k, v in sorted(approaches.items())}
    return result


def headline(summary: dict) -> dict:
    """Flat numbers for summary.json / summary.csv."""
    if not summary or not summary.get("samples"):
        return {}
    q, f = summary["queue"], summary["flow"]
    out = {
        "est_samples": summary["samples"],
        "est_queue_mae": q["probe"]["mae"],
        "est_queue_rmse": q["probe"]["rmse"],
        "est_queue_bias": q["probe"]["bias"],
        "est_queue_adj_mae": q["probe_adj"]["mae"],
        "est_queue_adj_bias": q["probe_adj"]["bias"],
        "det_queue_mae": q["detector"]["mae"],
        "det_queue_bias": q["detector"]["bias"],
        "fused_queue_mae": q["fused"]["mae"],
        "est_flow_mae": f["probe"]["mae"],
        "est_flow_rmse": f["probe"]["rmse"],
        "est_flow_bias": f["probe"]["bias"],
        "det_flow_mae": f["detector"]["mae"],
    }
    for kind, stats in summary.get("by_kind", {}).items():
        out[f"est_queue_bias_{kind}"] = stats["queue"]["probe"]["bias"]
        out[f"est_queue_mae_{kind}"] = stats["queue"]["probe"]["mae"]
    return out
