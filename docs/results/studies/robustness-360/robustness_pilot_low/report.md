# Experiment report: `robustness_pilot_low`

Created 2026-11-05T01:13:06 · baseline **fixed_time** · code `e723a79` · SUMO 1.28.0

Matrix: scenarios emergency-193e6a, road_closure-193e6a, rush_hour-193e6a · controllers fixed_time, max_pressure · seeds [1] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `emergency-193e6a` = `{"demand_scale": 0.75}` · `road_closure-193e6a` = `{"demand_scale": 0.75}` · `rush_hour-193e6a` = `{"demand_scale": 0.75}`

Reproduce:

```bash
python -m teamb.experiments run --name robustness_pilot_low --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1 --workers 2 --scenario-params '{"demand_scale":0.75}' --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `emergency-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 1 | 59.0 | baseline | – | – | 235.0 | 1.47 | 3.9% | 84.5 | 27.6 | 10.0 | 0 | 108.0 |
| max_pressure | 1 | uniform | on | 1 | 26.0 | 55.9% | -33.0 | – | 162.0 | 0.90 | 2.9% | 24.9 | 27.4 | 2.0 | 0 | 93.7 |

## Scenario `road_closure-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 1 | 105.7 | baseline | – | – | 578.1 | 2.89 | 2.9% | 168.7 | 33.7 | 14.0 | 0 | – |
| max_pressure | 1 | uniform | on | 1 | 41.4 | 60.8% | -64.3 | – | 311.0 | 1.37 | 2.6% | 51.6 | 29.6 | 3.0 | 0 | – |

## Scenario `rush_hour-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 1 | 61.0 | baseline | – | – | 237.8 | 1.42 | 3.9% | 88.5 | 26.9 | 11.0 | 0 | – |
| max_pressure | 1 | uniform | on | 1 | 24.7 | 59.4% | -36.2 | – | 159.0 | 0.84 | 3.0% | 22.7 | 27.4 | 2.0 | 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 6 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.03 ± 0.02 | 0.21 ± 0.23 | 0.14 ± 0.07 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | on | 1 | 10.0 | 108.0 | 30.2 | 59.1 | 9.0 | – | – |
| emergency | max_pressure | 1 | on | 1 | 10.0 | 93.7 | 15.9 | 26.1 | 4.0 | – | – |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | fixed_time | 1 | 1 | 1171 | 0 | 37.14 | – | – | – | 0 |
| road_closure | max_pressure | 1 | 1 | 621 | 0 | 15.07 | – | – | – | 0 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | fixed_time | 1 | uniform | on | 1 | 2433 | 99 | 3.9 | 0 | 0.0 | 58.4 |
| emergency | max_pressure | 1 | uniform | on | 1 | 2458 | 74 | 2.9 | 0 | 0.0 | 25.6 |
| road_closure | fixed_time | 1 | uniform | on | 1 | 2780 | 83 | 2.9 | 0 | 0.0 | 103.6 |
| road_closure | max_pressure | 1 | uniform | on | 1 | 2789 | 74 | 2.6 | 0 | 0.0 | 40.8 |
| rush_hour | fixed_time | 1 | uniform | on | 1 | 2425 | 97 | 3.9 | 0 | 0.0 | 60.2 |
| rush_hour | max_pressure | 1 | uniform | on | 1 | 2447 | 75 | 3.0 | 0 | 0.0 | 24.4 |

## Compute cost

6 runs ok, 0 failed · experiment wall time 55.1 s with [2] worker(s) · sum of run wall times 107.8 s · 267.3× faster than real time per run · data 19.5 MB (3.25 MB/run, 2.44 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 18.8 | 3.67 |
| max_pressure | 17.1 | 3.31 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
