# results/

Everything in this folder is generated and **not committed** (see `.gitignore`), except this
file. Re-create any result with the command that made it; each run records its seed, code
revision, SUMO version and network/demand hashes in `manifest.json`. A small committed copy
of an experiment report lives in [`docs/results/`](../docs/results/).

```
results/
├── runs/<run_id>/                     single runs: python -m teamb run ...
├── experiments/<name>/                batch experiments: python -m teamb.experiments run --name <name> ...
│   ├── experiment.json                every invocation: matrix, workers, wall time, failed runs
│   ├── runs/<run name>/               one folder per run (same files as results/runs/<run_id>/)
│   ├── summary.csv                    one row per run: identity columns + every scalar metric
│   ├── report.json                    paired analysis (schema read by the digital twin)
│   └── report.md                      the same as readable tables
└── cache/                             other modules' caches (e.g. the AI recommender's plan search)
```

Run names in an experiment: `<scenario>__<controller>__s<seed>__c<coverage %>__<sampling>[__nopre]`
(a `-<hash>` suffix marks custom scenario or controller parameters; `run_spec.json` has them).

## Files of one run

| File | Written by | What it is |
|---|---|---|
| `summary.json` | env + metrics | all metrics of the run (see `docs/roles/data-evaluation.md`) |
| `manifest.json` | env | code revision, SUMO version, network and demand hashes, seed, full config |
| `trips.csv` | env (from metrics) | one row per trip: depart, arrival, duration, time loss, stops, origin, movement |
| `signal_events.csv` | env | every signal change, request, rejection and preemption (safety supervisor) |
| `preemptions.json` | env | emergency-vehicle preemption requests |
| `tripinfo.xml`, `routes.rou.xml` | SUMO / scenario | raw SUMO output and the demand of this seed |
| `timeseries.csv` | metrics | every 5 s: vehicles, halting, delay rate, queues, spillback, alerts, closures |
| `estimation.csv` | sensors (via metrics) | every 5 s per approach: probe / detector / fused estimates next to ground truth |
| `detector_intervals.csv` | sensors (via metrics) | 60-s detector aggregates: count, flow, occupancy, speed, halting |
| `evaluation.json` | metrics | breakdowns: per approach, per link, per event, EV trips, alert episodes |
| `run_spec.json`, `events.json` | experiment runner | the matrix cell of this run; the env's event log |
| `error.json` | experiment runner | only if the run failed: the exception and traceback |

Column definitions, units and the meaning of empty values: `docs/roles/data-evaluation.md`
(data dictionary).

Size (measured in the sample experiment): about 2.4 MB per 2700-s run, 3.2 MB per simulated
hour, most of it `tripinfo.xml`, `routes.rou.xml` and `estimation.csv`. Delete
`results/experiments/<name>/runs/*/tripinfo.xml` if space matters; the summaries and `trips.csv`
keep everything the reports need.
