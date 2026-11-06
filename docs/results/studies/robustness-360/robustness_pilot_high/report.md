# Experiment report: `robustness_pilot_high`

Created 2026-11-05T01:14:22 · baseline **fixed_time** · code `e723a79` · SUMO 1.28.0

Matrix: scenarios emergency-5601c3, road_closure-5601c3, rush_hour-5601c3 · controllers fixed_time, max_pressure · seeds [1] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `emergency-5601c3` = `{"demand_scale": 1.25}` · `road_closure-5601c3` = `{"demand_scale": 1.25}` · `rush_hour-5601c3` = `{"demand_scale": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name robustness_pilot_high --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1 --workers 2 --scenario-params '{"demand_scale":1.25}' --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `emergency-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 1 | 108.6 | baseline | – | – | 417.0 | 2.75 | 14.3% | 182.2 | 36.3 | 27.0 | 0 | 132.8 |
| max_pressure | 1 | uniform | on | 1 | 51.5 | 52.6% | -57.1 | – | 226.0 | 1.88 | 3.2% | 57.1 | 44.5 | 8.0 | 0 | 112.9 |

## Scenario `road_closure-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 1 | 125.2 | baseline | – | – | 648.3 | 3.33 | 15.3% | 209.2 | 52.0 | 26.0 | 100 | – |
| max_pressure | 1 | uniform | on | 1 | 124.1 | 0.9% | -1.2 | – | 592.8 | 4.95 | 9.0% | 181.0 | 65.1 | 16.0 | 180 | – |

## Scenario `rush_hour-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 1 | 109.7 | baseline | – | – | 408.0 | 2.60 | 14.3% | 186.7 | 33.8 | 28.0 | 0 | – |
| max_pressure | 1 | uniform | on | 1 | 40.2 | 63.3% | -69.5 | – | 188.0 | 1.39 | 2.7% | 42.6 | 37.3 | 6.0 | 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 6 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.04 ± 0.01 | 1.06 ± 0.59 | 0.40 ± 0.12 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | on | 1 | 9.0 | 132.8 | 56.4 | 108.7 | 42.7 | – | – |
| emergency | max_pressure | 1 | on | 1 | 10.0 | 112.9 | 35.2 | 51.5 | 20.1 | – | – |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | fixed_time | 1 | 1 | 1346 | 0 | 21.47 | – | – | – | 100 |
| road_closure | max_pressure | 1 | 1 | – | 1 | 116.08 | – | – | – | 180 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | uniform | on | 1 | 3635 | 605 | 14.3 | 379 | 0.0 | 109.3 |
| emergency | max_pressure | 1 | uniform | on | 1 | 4106 | 135 | 3.2 | 0 | 0.0 | 50.7 |
| road_closure | fixed_time | 1 | uniform | on | 1 | 4098 | 740 | 15.3 | 497 | 0.0 | 125.0 |
| road_closure | max_pressure | 1 | uniform | on | 1 | 4402 | 436 | 9.0 | 120 | 0.0 | 123.2 |
| rush_hour | fixed_time | 1 | uniform | on | 1 | 3625 | 605 | 14.3 | 363 | 0.0 | 108.9 |
| rush_hour | max_pressure | 1 | uniform | on | 1 | 4115 | 116 | 2.7 | 0 | 0.0 | 39.6 |

## Compute cost

6 runs ok, 0 failed · experiment wall time 76.3 s with [2] worker(s) · sum of run wall times 151.3 s · 190.3× faster than real time per run · data 27.0 MB (4.5 MB/run, 3.37 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 26.5 | 5.28 |
| max_pressure | 23.9 | 4.74 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
