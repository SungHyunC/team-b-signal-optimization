# Experiment report: `robustness_high`

Created 2026-11-05T02:19:01 · baseline **fixed_time** · code `e723a79` · SUMO 1.28.0

Matrix: scenarios emergency-5601c3, road_closure-5601c3, rush_hour-5601c3 · controllers fixed_time, max_pressure · seeds [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `emergency-5601c3` = `{"demand_scale": 1.25}` · `road_closure-5601c3` = `{"demand_scale": 1.25}` · `rush_hour-5601c3` = `{"demand_scale": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name robustness_high --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1-30 --workers 2 --scenario-params '{"demand_scale":1.25}' --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `emergency-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 30 | 107.4 ± 1.2 | baseline | – | – | 405.7 ± 6.5 | 2.67 ± 0.04 | 11.8 ± 0.5% | 175.6 ± 2.4 | 36.9 ± 0.5 | 26.3 ± 0.4 | 1 ± 1 | 133.9 ± 3.5 |
| max_pressure | 1 | uniform | on | 30 | 44.7 ± 2.4 | 58.4 ± 2.3% | -62.7 ± 2.6 | <0.001 | 205.8 ± 9.6 | 1.58 ± 0.10 | 2.7 ± 0.2% | 48.6 ± 3.2 | 39.8 ± 1.5 | 6.4 ± 0.5 | 0 ± 0 | 111.3 ± 2.8 |

## Scenario `road_closure-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 30 | 126.0 ± 2.7 | baseline | – | – | 618.9 ± 16.7 | 3.40 ± 0.08 | 14.5 ± 0.4% | 213.3 ± 4.4 | 50.0 ± 2.1 | 25.8 ± 0.4 | 136 ± 41 | – |
| max_pressure | 1 | uniform | on | 30 | 123.8 ± 4.7 | 1.5 ± 4.3% | -2.3 ± 5.4 | 0.400 | 620.8 ± 22.5 | 4.96 ± 0.20 | 8.2 ± 0.9% | 181.4 ± 7.7 | 65.2 ± 2.8 | 15.7 ± 0.4 | 309 ± 87 | – |

## Scenario `rush_hour-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 30 | 107.6 ± 1.0 | baseline | – | – | 402.8 ± 5.6 | 2.59 ± 0.03 | 12.3 ± 0.6% | 179.1 ± 2.2 | 34.5 ± 0.5 | 26.8 ± 0.3 | 0 ± 0 | – |
| max_pressure | 1 | uniform | on | 30 | 42.6 ± 1.9 | 60.4 ± 1.8% | -65.0 ± 2.2 | <0.001 | 199.0 ± 8.3 | 1.50 ± 0.08 | 2.7 ± 0.1% | 46.0 ± 2.6 | 38.4 ± 1.1 | 6.1 ± 0.4 | 0 ± 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 180 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.05 ± 0.00 | 0.99 ± 0.07 | 0.39 ± 0.01 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | on | 30 | 9.6 ± 0.2 | 133.9 ± 3.5 | 57.2 ± 3.4 | 107.5 ± 1.2 | 31.4 ± 5.9 | – | – |
| emergency | max_pressure | 1 | on | 30 | 10.0 ± 0.0 | 111.3 ± 2.8 | 33.5 ± 2.8 | 44.7 ± 2.4 | 16.5 ± 2.9 | – | – |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | fixed_time | 1 | 30 | 1019 ± 254 | 14 | 31.86 ± 5.63 | – | – | – | 136 ± 41 |
| road_closure | max_pressure | 1 | 30 | – | 30 | 113.38 ± 6.27 | – | – | – | 309 ± 87 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | uniform | on | 30 | 3725 ± 29 | 497 ± 22 | 11.8 ± 0.5 | 281 ± 24 | 0.0 ± 0.0 | 107.7 ± 1.4 |
| emergency | max_pressure | 1 | uniform | on | 30 | 4110 ± 29 | 113 ± 7 | 2.7 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 44.0 ± 2.4 |
| road_closure | fixed_time | 1 | uniform | on | 30 | 4118 ± 26 | 701 ± 20 | 14.5 ± 0.4 | 485 ± 20 | 0.0 ± 0.0 | 125.5 ± 2.8 |
| road_closure | max_pressure | 1 | uniform | on | 30 | 4424 ± 41 | 394 ± 45 | 8.2 ± 0.9 | 154 ± 36 | 0.0 ± 0.1 | 123.7 ± 5.2 |
| rush_hour | fixed_time | 1 | uniform | on | 30 | 3695 ± 24 | 517 ± 25 | 12.3 ± 0.6 | 302 ± 25 | 0.0 ± 0.0 | 107.8 ± 1.0 |
| rush_hour | max_pressure | 1 | uniform | on | 30 | 4100 ± 28 | 113 ± 4 | 2.7 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 41.9 ± 1.8 |

## Compute cost

180 runs ok, 0 failed · experiment wall time 2259.2 s with [2] worker(s) · sum of run wall times 4509.6 s · 191.6× faster than real time per run · data 811.7 MB (4.51 MB/run, 3.38 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 26.3 | 5.26 |
| max_pressure | 23.8 | 4.73 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
