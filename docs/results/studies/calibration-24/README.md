# Spillback penalty calibration: 24 runs

Exploratory three-seed screen (seeds 4–6) of the experimental `max_pressure_spillback`
controller against the original `max_pressure`: penalty 1.10 and 1.25 at threshold 8, on 125 %
road closure and 100 % rush hour. Discussed in the
[calibration review](../../../spillback-penalty-calibration-review.md). The controller was later
**rejected** by the [independent confirmation](../confirmation-360/README.md) and is not on `main`.

| | |
|---|---|
| Workflow run | [Spillback Penalty Calibration Pilot #41968041524](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968041524) |
| Commit | [`1568f72`](https://github.com/SungHyunC/team-b-signal-optimization/commit/1568f72795b56453211482fc3db34591fbf6eec4) (branch `feature/validation-sandbox-explainability`) |
| Date | 2026-11-05 04:28 UTC |
| Simulator | SUMO 1.28.0 |
| Audit | 4 × 6 = 24/24 strict-valid runs (one `validation.json` per matrix) |
| Original artifact | `spillback-calibration-41968041524` (14 MB zip), expires 2026-11-19 |

## Included

| Folder | Matrix |
|---|---|
| [mild_110_closure](mild_110_closure/report.md) | road_closure, 125 % demand, penalty 1.10 |
| [mild_125_closure](mild_125_closure/report.md) | road_closure, 125 % demand, penalty 1.25 |
| [mild_110_rush](mild_110_rush/report.md) | rush_hour, 100 % demand, penalty 1.10 |
| [mild_125_rush](mild_125_rush/report.md) | rush_hour, 100 % demand, penalty 1.25 |

Each folder has `report.md`, `report.json`, `summary.csv` (one row per run), `validation.json` and
`experiment.json`. `prior_pilot_diagnosis.json` is the read-only diagnosis of the earlier
seeds 1–3 pilot (switching counts and queues during and after the closure).

Not included: the per-run folders (`runs/*/`).

## Reproduce

Needs the research commit: the controller is not on `main`. Check out `77ca85d` (or `1568f72`);
the commands are in each `experiment.json` and `report.md`.
