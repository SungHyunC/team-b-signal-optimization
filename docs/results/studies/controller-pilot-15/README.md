# Congestion controller pilot: 15 runs

First three-seed pilot (seeds 1–3) of the spillback-aware variant with its default parameters at
that commit (the stronger penalty: threshold 6, multiplier 1.50, per the
[calibration review](../../../spillback-penalty-calibration-review.md)): 9 heavy road-closure runs at 125 % demand (fixed-time, original,
variant) and 6 normal rush-hour runs (original, variant). It lowered spillback but lost
throughput, so it was held back. See the [pilot review](../../../congestion-controller-pilot-review.md).

| | |
|---|---|
| Workflow run | [Congestion Controller Improvement Pilot #41959366607](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41959366607) |
| Commit | [`912e680`](https://github.com/SungHyunC/team-b-signal-optimization/commit/912e680ffb5c7baa3411b8cf0cc35ef370a0350b) (branch `feature/validation-sandbox-explainability`) |
| Date | 2026-11-05 03:05 UTC |
| Simulator | SUMO 1.28.0 |
| Audit | 9/9 and 6/6 strict-valid runs |
| Original artifact | `congestion-controller-pilot-41959366607` (9 MB zip), expires 2026-11-19 |

## Included

- [congestion_pilot_heavy](congestion_pilot_heavy/report.md): road_closure, 125 % demand, 9 runs.
- [congestion_pilot_nominal](congestion_pilot_nominal/report.md): rush_hour, 100 % demand, 6 runs.

Each folder has `report.md`, `report.json`, `summary.csv`, `validation.json` and `experiment.json`.
Not included: the per-run folders (`runs/*/`).

## Reproduce

Needs the research commit (`git checkout 77ca85d`); the controller is not on `main`. The
commands are in each `experiment.json`.
