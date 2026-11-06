# Independent confirmation: 360 runs

Preregistered holdout test of the experimental `max_pressure_spillback` controller (downstream
queue threshold 8, penalty 1.25, frozen after calibration) against the original `max_pressure`,
on fresh paired seeds 31–60 in six conditions. Outcome: **rejected** as a general default
(heavy rush hour +14.0 % and heavy emergency +11.7 % delay fail the 5 % regression guard). See the
[decision](../../../independent-controller-confirmation-review.md). The experimental controller is
not on `main`.

| | |
|---|---|
| Workflow run | [Independent Controller Confirmation #41968750840](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968750840) |
| Commit | [`cd556b8`](https://github.com/SungHyunC/team-b-signal-optimization/commit/cd556b861d8f17cf3b00fc5dafddfdc6f7222e27) (branch `feature/validation-sandbox-explainability`) |
| Date | 2026-11-05 04:35 UTC |
| Simulator | SUMO 1.28.0 |
| Audit | 6 × 60 = 360/360 strict-valid runs (one `validation.json` per condition) |
| Original artifact | `independent-confirmation-41968750840` (artifact 13390656343, 194 MB zip), expires 2026-11-19 |

## Included

| Folder | Condition (30 paired seeds, original vs experimental) |
|---|---|
| [confirm_closure_125](confirm_closure_125/report.md) | road_closure, 125 % demand (primary) |
| [confirm_closure_075](confirm_closure_075/report.md) | road_closure, 75 % demand |
| [confirm_rush_100](confirm_rush_100/report.md) | rush_hour, 100 % demand |
| [confirm_rush_125](confirm_rush_125/report.md) | rush_hour, 125 % demand |
| [confirm_emergency_100](confirm_emergency_100/report.md) | emergency, 100 % demand |
| [confirm_emergency_125](confirm_emergency_125/report.md) | emergency, 125 % demand |

Each folder has `report.md`, `report.json`, `summary.csv` (one row per run), `validation.json` and
`experiment.json`. `confirmation_summary.json` is the confirmation evaluator's output: paired
differences with 95 % intervals for delay, unfinished share, completed trips, throughput,
spillback, queue and emergency-vehicle travel time per condition, the numbers quoted in the decision.

Not included: the per-run folders (`runs/*/`), about 1.4 GB unpacked.

## Reproduce

Needs the research commit (`git checkout 77ca85d` or `cd556b8`): the controller is not on `main`.
The commands are in each `experiment.json`; the full design is the
[confirmation workflow at 77ca85d](https://github.com/SungHyunC/team-b-signal-optimization/blob/77ca85d/.github/workflows/independent-controller-confirmation.yml).
