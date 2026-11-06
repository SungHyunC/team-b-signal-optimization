# Experiment report: `lesson1_validation`

Created 2026-11-04T23:15:23 · baseline **fixed_time** · code `3ad4329` · SUMO 1.28.0

Matrix: scenarios emergency, road_closure, rush_hour · controllers fixed_time, max_pressure · seeds [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Reproduce:

```bash
python -m teamb.experiments run --name lesson1_validation --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1-30 --workers 2 --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `emergency`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 30 | 89.5 ± 4.4 | baseline | – | – | 353.8 ± 21.6 | 2.20 ± 0.12 | 4.9 ± 0.4% | 136.4 ± 8.1 | 33.4 ± 0.4 | 18.7 ± 1.0 | 3 ± 4 | 129.3 ± 2.7 |
| max_pressure | 1 | uniform | on | 30 | 30.1 ± 0.3 | 65.8 ± 1.9% | -59.4 ± 4.4 | <0.001 | 168.1 ± 0.9 | 1.04 ± 0.02 | 2.6 ± 0.1% | 30.1 ± 0.5 | 30.0 ± 0.3 | 3.3 ± 0.2 | 0 ± 0 | 100.9 ± 1.2 |

## Scenario `road_closure`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 30 | 119.8 ± 0.8 | baseline | – | – | 600.6 ± 9.7 | 3.19 ± 0.03 | 7.6 ± 0.3% | 197.5 ± 1.4 | 40.5 ± 0.9 | 22.3 ± 0.3 | 28 ± 11 | – |
| max_pressure | 1 | uniform | on | 30 | 93.0 ± 3.8 | 22.4 ± 3.1% | -26.8 ± 3.7 | <0.001 | 544.1 ± 12.0 | 3.52 ± 0.17 | 2.3 ± 0.1% | 132.9 ± 5.8 | 47.8 ± 1.5 | 10.5 ± 0.4 | 91 ± 37 | – |

## Scenario `rush_hour`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 30 | 84.0 ± 4.4 | baseline | – | – | 318.2 ± 20.1 | 1.94 ± 0.12 | 4.7 ± 0.4% | 127.8 ± 8.0 | 31.3 ± 0.3 | 18.7 ± 1.0 | 0 ± 0 | – |
| max_pressure | 1 | uniform | on | 30 | 29.4 ± 0.4 | 64.3 ± 1.8% | -54.5 ± 4.4 | <0.001 | 166.5 ± 1.0 | 1.01 ± 0.02 | 2.6 ± 0.1% | 29.2 ± 0.5 | 29.7 ± 0.4 | 3.1 ± 0.1 | 0 ± 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 180 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.04 ± 0.00 | 0.56 ± 0.06 | 0.26 ± 0.01 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | on | 30 | 10.0 ± 0.0 | 129.3 ± 2.7 | 51.5 ± 2.7 | 89.6 ± 4.4 | 36.2 ± 6.3 | – | – |
| emergency | max_pressure | 1 | on | 30 | 10.0 ± 0.0 | 100.9 ± 1.2 | 23.1 ± 1.2 | 30.1 ± 0.3 | 6.4 ± 0.5 | – | – |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | fixed_time | 1 | 30 | – | 30 | 52.68 ± 2.42 | – | – | – | 28 ± 11 |
| road_closure | max_pressure | 1 | 30 | 1299 ± 101 | 1 | 68.63 ± 3.97 | – | – | – | 91 ± 37 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | uniform | on | 30 | 3214 ± 25 | 167 ± 14 | 4.9 ± 0.4 | 4 ± 3 | 0.0 ± 0.0 | 90.0 ± 4.7 |
| emergency | max_pressure | 1 | uniform | on | 30 | 3293 ± 24 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 29.7 ± 0.3 |
| road_closure | fixed_time | 1 | uniform | on | 30 | 3561 ± 23 | 291 ± 14 | 7.5 ± 0.3 | 89 ± 14 | 0.0 ± 0.0 | 119.0 ± 0.7 |
| road_closure | max_pressure | 1 | uniform | on | 30 | 3764 ± 25 | 88 ± 4 | 2.3 ± 0.1 | 0 ± 0 | 0.0 ± 0.1 | 91.2 ± 3.7 |
| rush_hour | fixed_time | 1 | uniform | on | 30 | 3213 ± 22 | 158 ± 16 | 4.7 ± 0.4 | 4 ± 5 | 0.0 ± 0.0 | 84.1 ± 4.7 |
| rush_hour | max_pressure | 1 | uniform | on | 30 | 3283 ± 23 | 88 ± 5 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 29.1 ± 0.4 |

## Compute cost

180 runs ok, 0 failed · experiment wall time 1030.7 s with [2] worker(s) · sum of run wall times 2055.8 s · 420.3× faster than real time per run · data 707.5 MB (3.93 MB/run, 2.95 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 12.1 | 2.31 |
| max_pressure | 10.7 | 2.01 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
