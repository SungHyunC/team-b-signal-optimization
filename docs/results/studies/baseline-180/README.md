# Baseline study: 180 runs at 100 % demand

Paired-seed comparison of `fixed_time` (baseline) and `max_pressure` on `rush_hour`, `emergency`
and `road_closure`, seeds 1–30, 100 % demand. Source of the 100 % row in the
[robustness review](../../../robustness-and-sensitivity-review.md) and the
[final engineering review](../../../final-engineering-review.md).

| | |
|---|---|
| Workflow run | [Statistical Validation and Reproducibility #41929708299](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41929708299) |
| Commit | [`3ad4329`](https://github.com/SungHyunC/team-b-signal-optimization/commit/3ad4329f676a3edd33faf92103a4326220248b64) (branch `feature/validation-sandbox-explainability`) |
| Date | 2026-11-04 22:57 UTC |
| Simulator | SUMO 1.28.0 |
| Audit | 180/180 strict-valid runs ([validation.json](lesson1_validation/validation.json)) |
| Original artifact | `lesson1-sumo-results-41929708299` (94 MB zip), expires 2026-11-18 |

## Included

- `lesson1_validation/`: the 180-run matrix. [report.md](lesson1_validation/report.md) (paired comparison tables),
  `report.json` (the same, machine-readable), `summary.csv` (one row per run), `validation.json`
  (strict audit), `experiment.json` (the exact command and matrix).
- `lesson1_smoke/`: the 2-run smoke test of the same workflow ([report.md](lesson1_smoke/report.md)).

Not included: the per-run folders (`runs/*/`: tripinfo.xml, trips.csv, time series, manifests),
about 690 MB unpacked. They disappear with the Actions artifact.

## Reproduce

Dispatch [lesson1-sumo-validation.yml](../../../../.github/workflows/lesson1-sumo-validation.yml) with
`run_full_matrix`, or follow the [Lesson 1 runbook](../../../lesson1-validation-runbook.md).
Results are comparable only with the same SUMO version (pinned to 1.28.0) and code revision.
