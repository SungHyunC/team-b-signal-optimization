# Experiment report: `confirm_closure_125`

Created 2026-11-05T04:44:12 · baseline **max_pressure** · code `cd556b8` · SUMO 1.28.0

Matrix: scenarios road_closure-5601c3 · controllers max_pressure, max_pressure_spillback-44ec25 · seeds [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `road_closure-5601c3` = `{"demand_scale": 1.25}`

Controller parameters: `max_pressure_spillback-44ec25` = `{"congestion_threshold": 8, "downstream_penalty": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name confirm_closure_125 --scenarios road_closure --controllers max_pressure,max_pressure_spillback --seeds 31-60 --workers 2 --scenario-params '{"demand_scale":1.25}' --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.25}}' --baseline max_pressure --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `road_closure-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **max_pressure** | 1 | uniform | on | 30 | 120.8 ± 4.7 | baseline | – | – | 618.7 ± 23.2 | 4.86 ± 0.20 | 7.4 ± 0.9% | 177.8 ± 8.2 | 62.3 ± 2.5 | 15.4 ± 0.5 | 308 ± 101 | – |
| max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 107.0 ± 3.9 | 10.8 ± 3.7% | -13.8 ± 4.9 | <0.001 | 577.2 ± 21.2 | 4.11 ± 0.16 | 8.1 ± 1.0% | 164.5 ± 7.5 | 49.3 ± 1.4 | 15.1 ± 0.5 | 94 ± 37 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 60 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.06 ± 0.00 | 0.95 ± 0.02 | 0.55 ± 0.01 | 0 ± 0 | 0 ± 0 |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | max_pressure | 1 | 30 | 1866 | 29 | 110.40 ± 6.52 | – | – | – | 308 ± 101 |
| road_closure | max_pressure_spillback-44ec25 | 1 | 30 | – | 30 | 88.45 ± 5.04 | – | – | – | 94 ± 37 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | max_pressure | 1 | uniform | on | 30 | 4436 ± 37 | 354 ± 43 | 7.4 ± 0.9 | 122 ± 32 | 0.0 ± 0.1 | 120.7 ± 5.1 |
| road_closure | max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 4399 ± 38 | 390 ± 47 | 8.1 ± 1.0 | 190 ± 42 | 0.0 ± 0.0 | 105.7 ± 4.0 |

## Compute cost

60 runs ok, 0 failed · experiment wall time 491.0 s with [2] worker(s) · sum of run wall times 979.0 s · 330.9× faster than real time per run · data 295.8 MB (4.93 MB/run, 3.29 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure | 17.0 | 2.94 |
| max_pressure_spillback-44ec25 | 15.7 | 2.71 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
