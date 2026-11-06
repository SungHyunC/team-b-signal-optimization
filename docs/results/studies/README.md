# Study data archive

The 30-seed studies ran as GitHub Actions workflows, and their outputs were uploaded as Actions
artifacts that expire 14 days later (Nov 18–19, 2026). This folder keeps the small aggregate files
of every study the final reviews cite, so their numbers stay checkable. Each study folder has a
README with the workflow run, commit, date and exactly what is included.

| Study | Runs | What it decided | Workflow run | Commit |
|---|---:|---|---|---|
| [baseline-180](baseline-180/README.md) | 180 | max-pressure vs fixed-time at 100 % demand | [#41929708299](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41929708299) | `3ad4329` |
| [robustness-360](robustness-360/README.md) | 360 (+12 pilot) | the same at 75 % and 125 % demand | [#41946810451](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41946810451) | `e723a79` |
| [congestion-diagnosis](congestion-diagnosis/README.md) | (reads robustness-360) | where the heavy-closure case congests | [#41958378469](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41958378469) | `cfa3a07` |
| [controller-pilot-15](controller-pilot-15/README.md) | 15 | first spillback-aware variant: held back | [#41959366607](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41959366607) | `912e680` |
| [calibration-24](calibration-24/README.md) | 24 | picked penalty 1.25, threshold 8 for confirmation | [#41968041524](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968041524) | `1568f72` |
| [confirmation-360](confirmation-360/README.md) | 360 | spillback-aware variant rejected | [#41968750840](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968750840) | `cd556b8` |

All runs used SUMO 1.28.0 and passed the strict per-run audit (`validation.json`).

**Included per experiment:** `report.md` and `report.json` (paired comparison, intervals, all
metrics), `summary.csv` (one row per run), `validation.json` (strict audit: completeness, code
revision, SUMO version, network hash) and `experiment.json` (the exact command and matrix), plus
the diagnosis and evaluator JSON files where a study produced them.

**Not included:** the per-run folders (`runs/<run>/`: tripinfo.xml, trips.csv, time series,
detector logs, manifests). They are 0.1–1.4 GB per study and vanish with the artifacts; re-running
a study's workflow on its commit regenerates them. `teamb diagnose` needs those per-run folders.

Commands inside the archived `report.md` and `experiment.json` files reproduce the study at its
own commit. The spillback-aware controller exists only on the research commit
[`77ca85d`](https://github.com/SungHyunC/team-b-signal-optimization/tree/77ca85d), not on `main`.
