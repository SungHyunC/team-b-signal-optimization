# Robustness study: 360 runs at 75 % and 125 % demand

Paired-seed comparison of `fixed_time` (baseline) and `max_pressure` on `rush_hour`, `emergency`
and `road_closure`, seeds 1–30, at 75 % and 125 % demand (180 runs each), plus a one-seed pilot at
each level. Source of the 75 % and 125 % rows in the
[robustness review](../../../robustness-and-sensitivity-review.md), including the inconclusive
1.8 % at 125 % road closure. The [congestion diagnosis](../congestion-diagnosis/README.md) reads
this study.

| | |
|---|---|
| Workflow run | [Robustness and Sensitivity Testing #41946810451](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41946810451) |
| Commit | [`e723a79`](https://github.com/SungHyunC/team-b-signal-optimization/commit/e723a79c19fd51bed11ec72ae74c7005319ad72d) (branch `feature/validation-sandbox-explainability`) |
| Date | 2026-11-05 01:11 UTC |
| Simulator | SUMO 1.28.0 |
| Audit | 180/180 + 180/180 strict-valid runs, pilots 6/6 + 6/6 (one `validation.json` per matrix) |
| Original artifact | `robustness-results-41946810451` (190 MB zip), expires 2026-11-19 |

## Included

| Folder | Matrix |
|---|---|
| [robustness_low](robustness_low/report.md) | 75 % demand, seeds 1–30, 180 runs |
| [robustness_high](robustness_high/report.md) | 125 % demand, seeds 1–30, 180 runs |
| [robustness_pilot_low](robustness_pilot_low/report.md) | 75 % demand, seed 1, 6 runs |
| [robustness_pilot_high](robustness_pilot_high/report.md) | 125 % demand, seed 1, 6 runs |

Each folder has `report.md`, `report.json`, `summary.csv` (one row per run), `validation.json` and
`experiment.json`.

Not included: the per-run folders (`runs/*/`), which `teamb diagnose` needs. They disappear with
the Actions artifact.

## Reproduce

Dispatch [robustness-sensitivity.yml](../../../../.github/workflows/robustness-sensitivity.yml) with
`run_full_matrix`, or run the commands in [the study design](../../../robustness-and-sensitivity.md).
