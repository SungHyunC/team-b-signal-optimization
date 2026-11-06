# Experiment report: `robustness_low`

Created 2026-11-05T01:41:21 · baseline **fixed_time** · code `e723a79` · SUMO 1.28.0

Matrix: scenarios emergency-193e6a, road_closure-193e6a, rush_hour-193e6a · controllers fixed_time, max_pressure · seeds [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `emergency-193e6a` = `{"demand_scale": 0.75}` · `road_closure-193e6a` = `{"demand_scale": 0.75}` · `rush_hour-193e6a` = `{"demand_scale": 0.75}`

Reproduce:

```bash
python -m teamb.experiments run --name robustness_low --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1-30 --workers 2 --scenario-params '{"demand_scale":0.75}' --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `emergency-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 30 | 60.7 ± 0.7 | baseline | – | – | 236.8 ± 2.0 | 1.49 ± 0.01 | 3.4 ± 0.2% | 86.2 ± 0.9 | 29.2 ± 0.4 | 10.5 ± 0.2 | 0 ± 0 | 109.6 ± 1.0 |
| max_pressure | 1 | uniform | on | 30 | 25.4 ± 0.3 | 58.2 ± 0.5% | -35.3 ± 0.7 | <0.001 | 160.7 ± 0.6 | 0.88 ± 0.01 | 2.6 ± 0.1% | 23.8 ± 0.3 | 27.4 ± 0.4 | 2.2 ± 0.2 | 0 ± 0 | 95.0 ± 0.7 |

## Scenario `road_closure-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 30 | 106.0 ± 2.0 | baseline | – | – | 575.5 ± 8.8 | 2.87 ± 0.06 | 3.0 ± 0.1% | 168.8 ± 3.1 | 35.4 ± 0.8 | 13.9 ± 0.4 | 8 ± 4 | – |
| max_pressure | 1 | uniform | on | 30 | 45.9 ± 1.9 | 56.8 ± 1.4% | -60.2 ± 1.7 | <0.001 | 331.8 ± 11.2 | 1.56 ± 0.07 | 2.4 ± 0.1% | 58.7 ± 3.0 | 31.3 ± 0.7 | 3.7 ± 0.2 | 0 ± 1 | – |

## Scenario `rush_hour-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 30 | 61.8 ± 0.7 | baseline | – | – | 235.7 ± 1.6 | 1.45 ± 0.01 | 3.4 ± 0.2% | 88.6 ± 0.8 | 28.8 ± 0.3 | 11.0 ± 0.2 | 0 ± 0 | – |
| max_pressure | 1 | uniform | on | 30 | 25.0 ± 0.2 | 59.5 ± 0.4% | -36.8 ± 0.6 | <0.001 | 159.7 ± 0.6 | 0.87 ± 0.01 | 2.6 ± 0.1% | 23.3 ± 0.3 | 27.2 ± 0.4 | 2.0 ± 0.1 | 0 ± 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 180 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.03 ± 0.00 | 0.22 ± 0.03 | 0.15 ± 0.01 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | on | 30 | 10.0 ± 0.0 | 109.6 ± 1.0 | 31.8 ± 1.0 | 60.8 ± 0.7 | 8.5 ± 0.9 | – | – |
| emergency | max_pressure | 1 | on | 30 | 10.0 ± 0.0 | 95.0 ± 0.7 | 17.2 ± 0.7 | 25.4 ± 0.3 | 4.9 ± 0.4 | – | – |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | fixed_time | 1 | 30 | 1151 ± 80 | 0 | 37.21 ± 1.71 | – | – | – | 8 ± 4 |
| road_closure | max_pressure | 1 | 30 | 360 ± 57 | 0 | 17.21 ± 1.56 | – | – | – | 0 ± 1 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | uniform | on | 30 | 2458 ± 19 | 86 ± 4 | 3.4 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 59.9 ± 0.7 |
| emergency | max_pressure | 1 | uniform | on | 30 | 2477 ± 18 | 66 ± 3 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 25.1 ± 0.2 |
| road_closure | fixed_time | 1 | uniform | on | 30 | 2809 ± 19 | 86 ± 4 | 3.0 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 104.0 ± 1.9 |
| road_closure | max_pressure | 1 | uniform | on | 30 | 2827 ± 20 | 68 ± 3 | 2.4 ± 0.1 | 0 ± 0 | 0.0 ± 0.1 | 45.1 ± 1.9 |
| rush_hour | fixed_time | 1 | uniform | on | 30 | 2448 ± 19 | 86 ± 4 | 3.4 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 61.0 ± 0.7 |
| rush_hour | max_pressure | 1 | uniform | on | 30 | 2468 ± 18 | 65 ± 3 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 24.7 ± 0.2 |

## Compute cost

180 runs ok, 0 failed · experiment wall time 1618.4 s with [2] worker(s) · sum of run wall times 3231.5 s · 267.4× faster than real time per run · data 586.3 MB (3.26 MB/run, 2.44 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 18.9 | 3.71 |
| max_pressure | 17.0 | 3.33 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
