# Controller confirmation, November 2026

**Question.** Can a controller beat the original `max_pressure` without the regressions that sank
the spillback-aware variant ([confirmation-360](../confirmation-360/README.md))? And did retraining
the RL controller fix its flood failure?

**Design (fixed before the runs).** Fresh seeds **201-230** (30 paired seeds; never used for
screening, training or validation) × 7 scenarios (rush_hour, special_event, emergency, road_closure,
sinkhole_cross, earthquake, off_peak) × demand **0.75 / 1.0 / 1.25** × 6 controllers = 3,780 runs,
SUMO 1.28.0 through libsumo, run on Modal (`teamb exp run --backend modal`) from one clean
commit, `aa0c16c` (branch improve/unified-project); every expected run passed teamb's strict audit
(`demand-<d>/validation.json`). Every candidate is
judged against `max_pressure` with `teamb exp screen`, the team's earlier decision rule as code:
in **every** condition the mean delay may not rise by more than 5 %, the unfinished share may not
rise by more than 0.5 pp (nor significantly by more than 0.1 pp), emergency-vehicle travel time may
not rise significantly by more than 1 s, and no run may have controller errors, fallbacks or
rejected actions. Paired 95 % t-intervals, not adjusted for the 21 conditions.

**Where the candidates came from.** A stage-1 screen on seeds 101-110 at demand 1.0 and 1.25
([stage1-screen](stage1-screen/README.md)) compared lost-time-aware hysteresis (`rho` 0.15 / 0.25,
with and without a cap) and the closure-aware downstream term (`closure_weight` 0 / 0.35 / 0.5).
`rho` 0.25 and its combination with `closure_aware` (weight 0.35) went forward. The RL model was
chosen on validation seeds 900-909 ([rl-retraining-2026-11](../rl-retraining-2026-11/README.md)).

## Verdicts

| Candidate vs max_pressure | 75 % | 100 % | 125 % | Promoted |
|---|---|---|---|---|
| max_pressure_plus (rho 0.25) | PASS | PASS | PASS | yes, as `max_pressure_plus` |
| max_pressure + rho 0.25 + closure_aware | FAIL (road_closure) | PASS | PASS | no |
| rl (new default) | FAIL (road_closure, special_event) | FAIL (earthquake, special_event) | FAIL (earthquake, road_closure) | no |

Mean, worst and best per-scenario change of mean delay against `max_pressure` (negative = better):

| Candidate | 0.75 demand: mean / worst / best vs max_pressure | 1 demand: mean / worst / best vs max_pressure | 1.25 demand: mean / worst / best vs max_pressure |
|---|---|---|---|
| max_pressure_plus (rho 0.25) | -2.4 % / +0.3 % (sinkhole_cross) / -13.4 % (earthquake) | -3.9 % / +0.3 % (emergency) / -9.4 % (sinkhole_cross) | -3.6 % / +0.2 % (off_peak) / -9.5 % (special_event) |
| max_pressure + rho 0.25 + closure_aware | -1.3 % / +11.7 % (road_closure) / -21.4 % (earthquake) | -8.1 % / +0.3 % (emergency) / -36.3 % (earthquake) | -8.2 % / +0.2 % (off_peak) / -28.8 % (earthquake) |
| rl (new default) | -3.9 % / +12.9 % (special_event) / -31.2 % (off_peak) | -2.0 % / +23.9 % (earthquake) / -18.4 % (off_peak) | +7.0 % / +66.6 % (earthquake) / -25.5 % (special_event) |
| rl (first model, original) | +19.9 % / +76.4 % (road_closure) / -28.8 % (off_peak) | +18.0 % / +91.2 % (road_closure) / -18.2 % (off_peak) | +21.7 % / +78.1 % (road_closure) / -20.1 % (special_event) |

- **`max_pressure + rho 0.25` passed all 21 conditions** and is now registered as
  `max_pressure_plus`. Its gains are largest in heavy traffic and disasters; it never raised mean
  delay by more than a fraction of a percent, and at 125 % demand it also finished more trips in
  the earthquake, the flood and the stadium surge.
- **Adding `closure_aware`** helps a lot where several roads are cut (earthquake at 100 % demand:
  228 → 145 s/veh) but failed the guard in the light-traffic flood
  (75 %): with spare capacity the detour is better served by the original rule. Not promoted; it
  stays available as `{"rho": 0.25, "closure_aware": true, "closure_weight": 0.35}`.
- **The retrained RL** (v2 features, 2,000 mixed-scenario episodes, low-confidence fallback) no
  longer collapses in the flood (100 % demand: 169 → 87 s/veh; max-pressure 88), beats max-pressure
  off-peak at every demand (by 11-31 %) and in the heavy stadium surge (125 %: 81 → 61 s/veh), but it
  is clearly worse than max-pressure in the earthquake and in the light stadium surge, so it fails
  the screen. It remains the "stretch" controller, now with a known weak spot instead of a broken one.

## Results

### Demand 0.75 (mean delay s/veh ± 95 % CI, 30 seeds each)

| Scenario | fixed_time | max_pressure | max_pressure_plus (rho 0.25) | max_pressure + rho 0.25 + closure_aware | rl (new default) | rl (first model, original) |
|---|---:|---:|---:|---:|---:|---:|
| rush_hour | 61.7 ± 0.6 | 25.0 ± 0.2 | 24.9 ± 0.2 | 24.9 ± 0.2 | 24.9 ± 0.2 | 25.1 ± 0.2 |
| special_event | 60.3 ± 0.9 | 27.2 ± 0.5 | 26.9 ± 0.4 | 26.9 ± 0.4 | 30.7 ± 1.0 | 36.6 ± 1.6 |
| emergency | 60.5 ± 0.6 | 25.4 ± 0.2 | 25.3 ± 0.2 | 25.3 ± 0.2 | 25.1 ± 0.2 | 25.5 ± 0.2 |
| road_closure | 106.2 ± 2.0 | 46.1 ± 2.4 | 45.2 ± 1.5 | 51.5 ± 2.2 | 51.3 ± 2.6 | 81.3 ± 7.4 |
| sinkhole_cross | 122.1 ± 3.4 | 28.7 ± 0.4 | 28.8 ± 0.4 | 29.3 ± 0.4 | 28.3 ± 0.3 | 29.0 ± 0.3 |
| earthquake | 159.2 ± 14.2 | 109.1 ± 13.9 | 94.5 ± 11.9 | 85.7 ± 4.4 | 90.1 ± 18.4 | 169.3 ± 30.1 |
| off_peak | 51.9 ± 0.5 | 23.2 ± 0.3 | 23.2 ± 0.3 | 23.2 ± 0.3 | 15.9 ± 0.2 | 16.5 ± 0.2 |

Unfinished trips (% of planned):

| Scenario | fixed_time | max_pressure | max_pressure_plus (rho 0.25) | max_pressure + rho 0.25 + closure_aware | rl (new default) | rl (first model, original) |
|---|---:|---:|---:|---:|---:|---:|
| rush_hour | 3.29 ± 0.15 | 2.49 ± 0.10 | 2.57 ± 0.10 | 2.57 ± 0.10 | 2.54 ± 0.11 | 2.52 ± 0.11 |
| special_event | 3.93 ± 0.16 | 2.98 ± 0.13 | 2.98 ± 0.13 | 2.98 ± 0.13 | 3.02 ± 0.14 | 2.95 ± 0.14 |
| emergency | 3.26 ± 0.14 | 2.51 ± 0.11 | 2.53 ± 0.10 | 2.53 ± 0.10 | 2.51 ± 0.11 | 2.55 ± 0.11 |
| road_closure | 2.88 ± 0.10 | 2.27 ± 0.10 | 2.26 ± 0.10 | 2.25 ± 0.10 | 2.23 ± 0.11 | 2.26 ± 0.10 |
| sinkhole_cross | 4.32 ± 0.39 | 2.53 ± 0.11 | 2.54 ± 0.10 | 2.54 ± 0.10 | 2.51 ± 0.13 | 2.51 ± 0.10 |
| earthquake | 3.25 ± 0.18 | 2.50 ± 0.13 | 2.49 ± 0.14 | 2.52 ± 0.13 | 2.49 ± 0.11 | 2.53 ± 0.18 |
| off_peak | 4.04 ± 0.24 | 3.22 ± 0.18 | 3.22 ± 0.18 | 3.22 ± 0.18 | 2.99 ± 0.21 | 3.02 ± 0.20 |

### Demand 1 (mean delay s/veh ± 95 % CI, 30 seeds each)

| Scenario | fixed_time | max_pressure | max_pressure_plus (rho 0.25) | max_pressure + rho 0.25 + closure_aware | rl (new default) | rl (first model, original) |
|---|---:|---:|---:|---:|---:|---:|
| rush_hour | 81.8 ± 4.3 | 29.3 ± 0.3 | 29.1 ± 0.4 | 29.1 ± 0.4 | 29.3 ± 0.4 | 30.6 ± 0.4 |
| special_event | 75.5 ± 0.8 | 52.8 ± 1.4 | 49.4 ± 1.5 | 49.4 ± 1.5 | 50.6 ± 1.0 | 53.1 ± 0.8 |
| emergency | 83.9 ± 4.2 | 29.6 ± 0.3 | 29.7 ± 0.4 | 29.7 ± 0.4 | 30.0 ± 0.4 | 31.2 ± 0.4 |
| road_closure | 119.3 ± 1.2 | 88.4 ± 2.7 | 85.8 ± 2.4 | 80.4 ± 2.1 | 87.2 ± 1.9 | 169.1 ± 10.0 |
| sinkhole_cross | 132.1 ± 1.8 | 48.0 ± 5.1 | 43.5 ± 3.1 | 45.9 ± 4.3 | 40.6 ± 1.2 | 44.6 ± 1.7 |
| earthquake | 229.1 ± 17.1 | 227.5 ± 13.2 | 209.8 ± 12.6 | 144.9 ± 7.0 | 281.8 ± 25.4 | 340.2 ± 21.1 |
| off_peak | 52.6 ± 0.3 | 22.4 ± 0.2 | 22.4 ± 0.2 | 22.4 ± 0.2 | 18.3 ± 0.2 | 18.3 ± 0.2 |

Unfinished trips (% of planned):

| Scenario | fixed_time | max_pressure | max_pressure_plus (rho 0.25) | max_pressure + rho 0.25 + closure_aware | rl (new default) | rl (first model, original) |
|---|---:|---:|---:|---:|---:|---:|
| rush_hour | 4.27 ± 0.36 | 2.61 ± 0.12 | 2.62 ± 0.13 | 2.62 ± 0.13 | 2.60 ± 0.12 | 2.61 ± 0.12 |
| special_event | 3.91 ± 0.13 | 2.98 ± 0.13 | 2.93 ± 0.11 | 2.93 ± 0.11 | 3.34 ± 0.22 | 3.46 ± 0.25 |
| emergency | 4.17 ± 0.25 | 2.57 ± 0.12 | 2.62 ± 0.12 | 2.62 ± 0.12 | 2.56 ± 0.12 | 2.61 ± 0.12 |
| road_closure | 6.92 ± 0.34 | 2.29 ± 0.08 | 2.30 ± 0.09 | 2.28 ± 0.09 | 2.28 ± 0.09 | 2.46 ± 0.23 |
| sinkhole_cross | 11.82 ± 0.43 | 2.64 ± 0.14 | 2.61 ± 0.12 | 2.63 ± 0.14 | 2.60 ± 0.12 | 2.59 ± 0.12 |
| earthquake | 8.59 ± 0.55 | 3.30 ± 0.46 | 2.71 ± 0.26 | 2.53 ± 0.10 | 3.32 ± 0.54 | 5.96 ± 1.25 |
| off_peak | 4.09 ± 0.23 | 3.32 ± 0.21 | 3.32 ± 0.21 | 3.32 ± 0.21 | 3.23 ± 0.18 | 3.21 ± 0.21 |

### Demand 1.25 (mean delay s/veh ± 95 % CI, 30 seeds each)

| Scenario | fixed_time | max_pressure | max_pressure_plus (rho 0.25) | max_pressure + rho 0.25 + closure_aware | rl (new default) | rl (first model, original) |
|---|---:|---:|---:|---:|---:|---:|
| rush_hour | 106.9 ± 1.4 | 41.6 ± 2.4 | 41.2 ± 3.1 | 41.2 ± 3.1 | 42.6 ± 2.4 | 51.4 ± 3.8 |
| special_event | 93.2 ± 2.0 | 81.3 ± 3.9 | 73.6 ± 3.1 | 73.5 ± 3.1 | 60.6 ± 1.3 | 65.0 ± 1.4 |
| emergency | 107.6 ± 1.7 | 45.5 ± 3.2 | 41.2 ± 1.3 | 41.3 ± 1.4 | 43.9 ± 2.3 | 54.4 ± 3.8 |
| road_closure | 126.7 ± 2.5 | 115.7 ± 4.3 | 115.1 ± 3.9 | 104.7 ± 3.1 | 136.1 ± 4.5 | 206.0 ± 5.9 |
| sinkhole_cross | 152.0 ± 4.1 | 119.7 ± 5.3 | 118.1 ± 4.2 | 119.8 ± 4.6 | 122.5 ± 6.1 | 126.6 ± 8.1 |
| earthquake | 257.4 ± 10.1 | 247.2 ± 8.5 | 237.4 ± 11.2 | 176.0 ± 6.0 | 411.8 ± 21.3 | 386.6 ± 21.0 |
| off_peak | 53.4 ± 0.2 | 22.3 ± 0.2 | 22.4 ± 0.2 | 22.4 ± 0.2 | 19.9 ± 0.2 | 19.8 ± 0.2 |

Unfinished trips (% of planned):

| Scenario | fixed_time | max_pressure | max_pressure_plus (rho 0.25) | max_pressure + rho 0.25 + closure_aware | rl (new default) | rl (first model, original) |
|---|---:|---:|---:|---:|---:|---:|
| rush_hour | 12.30 ± 0.52 | 2.83 ± 0.14 | 2.82 ± 0.14 | 2.82 ± 0.14 | 2.84 ± 0.14 | 3.14 ± 0.27 |
| special_event | 5.32 ± 0.29 | 7.34 ± 0.45 | 6.42 ± 0.41 | 6.40 ± 0.41 | 7.24 ± 0.32 | 7.15 ± 0.24 |
| emergency | 11.92 ± 0.65 | 2.88 ± 0.15 | 2.82 ± 0.23 | 2.83 ± 0.25 | 2.90 ± 0.14 | 3.13 ± 0.28 |
| road_closure | 13.80 ± 0.39 | 6.55 ± 0.78 | 5.37 ± 0.81 | 5.60 ± 0.68 | 4.15 ± 0.26 | 10.89 ± 0.75 |
| sinkhole_cross | 18.38 ± 0.64 | 9.21 ± 0.93 | 8.53 ± 0.60 | 8.76 ± 0.92 | 6.92 ± 0.86 | 5.71 ± 0.66 |
| earthquake | 15.16 ± 0.57 | 11.57 ± 0.72 | 9.80 ± 0.81 | 6.11 ± 0.79 | 20.90 ± 1.71 | 19.02 ± 1.80 |
| off_peak | 3.94 ± 0.21 | 3.11 ± 0.19 | 3.12 ± 0.19 | 3.12 ± 0.19 | 2.97 ± 0.19 | 3.00 ± 0.19 |

## Files

`demand-<d>/report.md` (paired report against max_pressure, all metrics), `summary.csv` (one row
per run), `experiment.json` (commands and matrix), and `screen_<candidate>.md/json` (the screen
per candidate). Per-run folders (tripinfo, time series) are not committed; the commands below
regenerate them.

## Reproduce

```bash
pip install -e ".[dev,fast,cloud]" && modal setup
for d in 0.75 1.0 1.25; do
  n=confirm_d${d/./}
  S=rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak
  teamb exp run --name $n --backend modal --workers 100 --scenarios $S --seeds 201-230 \
      --scenario-params "{\"demand_scale\": $d}" --controllers fixed_time,max_pressure,max_pressure_plus,rl
  teamb exp screen --name $n --baseline max_pressure --candidate max_pressure_plus
done
```

`max_pressure_plus` is the same controller as `max_pressure` with `{"rho": 0.25}` (a test pins
this), and `rl` now loads the selected model by default, so these four controllers reproduce the
study's columns under their registered names. The first RL model is
`--controllers rl --controller-params '{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}'`.
Local runs (`--backend local`) give the same numbers; Modal is only faster.

**Limits.** A synthetic, uncalibrated four-junction corridor; demand, routes and closures are
design assumptions. Passing the screen means "no regression found in these 21 simulated
conditions", not field performance.
