# Congestion diagnosis of the robustness study

Read-only paired diagnosis (`teamb diagnose`, i.e. `python -m teamb.experiments.diagnose`) of the
two 180-run matrices of the [robustness study](../robustness-360/README.md): where and when
`max_pressure` and `fixed_time` congest, per scenario, at 125 % and 75 % demand.

| | |
|---|---|
| Workflow run | [Congestion Failure Analysis #41958378469](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41958378469) |
| Commit | [`cfa3a07`](https://github.com/SungHyunC/team-b-signal-optimization/commit/cfa3a0726f39b5a16f405695e1bf105abcbebfae) (branch `feature/validation-sandbox-explainability`) |
| Date | 2026-11-05 02:56 UTC |
| Input | artifact `robustness-results-41946810451` of run [#41946810451](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41946810451) |
| Original artifact | `congestion-diagnosis-41958378469` (3 KB zip), expires 2026-11-19 |

## Included

The whole artifact:

- `high_demand.json`: diagnosis of `robustness_high` (125 % demand, 180 runs).
- `light_demand.json`: diagnosis of `robustness_low` (75 % demand, 180 runs).

Each file has, per scenario, the paired seeds, paired metric differences with intervals,
spillback hotspots and warnings.

## Reproduce

Dispatch [congestion-failure-analysis.yml](../../../../.github/workflows/congestion-failure-analysis.yml)
with the run id of a full robustness run whose artifact has not expired. The per-run folders it
needs are not archived here.
