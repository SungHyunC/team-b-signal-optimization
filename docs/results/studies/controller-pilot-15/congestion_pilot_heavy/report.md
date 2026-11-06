# Experiment report: `congestion_pilot_heavy`

Created 2026-11-05T03:08:55 · baseline **fixed_time** · code `912e680` · SUMO 1.28.0

Matrix: scenarios road_closure-5601c3 · controllers fixed_time, max_pressure, max_pressure_spillback · seeds [1, 2, 3] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `road_closure-5601c3` = `{"demand_scale": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name congestion_pilot_heavy --scenarios road_closure --controllers fixed_time,max_pressure,max_pressure_spillback --seeds 1-3 --workers 2 --scenario-params '{"demand_scale":1.25}' --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `road_closure-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 3 | 126.4 ± 6.9 | baseline | – | – | 646.1 ± 23.0 | 3.36 ± 0.33 | 14.5 ± 1.8% | 212.3 ± 24.5 | 53.0 ± 2.3 | 25.7 ± 3.8 | 210 ± 237 | – |
| max_pressure | 1 | uniform | on | 3 | 115.2 ± 19.7 | 8.8 ± 18.9% | -11.2 ± 24.5 | 0.187 | 568.0 ± 92.7 | 4.54 ± 0.87 | 6.6 ± 5.7% | 166.7 ± 30.8 | 61.7 ± 9.1 | 15.0 ± 2.5 | 138 ± 100 | – |
| max_pressure_spillback | 1 | uniform | on | 3 | 112.6 ± 22.2 | 11.0 ± 15.3% | -13.8 ± 18.9 | 0.175 | 565.7 ± 126.2 | 4.06 ± 0.79 | 11.7 ± 5.1% | 186.8 ± 50.4 | 44.5 ± 6.5 | 18.0 ± 4.3 | 77 ± 80 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 9 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.07 ± 0.01 | 1.17 ± 0.20 | 0.48 ± 0.06 | 0 ± 0 | 0 ± 0 |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | fixed_time | 1 | 3 | 1194 ± 1938 | 1 | 32.80 ± 37.72 | – | – | – | 210 ± 237 |
| road_closure | max_pressure | 1 | 3 | – | 3 | 101.97 ± 31.09 | – | – | – | 138 ± 100 |
| road_closure | max_pressure_spillback | 1 | 3 | – | 3 | 76.31 ± 52.31 | – | – | – | 77 ± 80 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | fixed_time | 1 | uniform | on | 3 | 4131 ± 106 | 700 ± 90 | 14.5 ± 1.8 | 476 ± 45 | 0.0 ± 0.0 | 125.8 ± 5.1 |
| road_closure | max_pressure | 1 | uniform | on | 3 | 4512 ± 321 | 319 ± 274 | 6.6 ± 5.7 | 66 ± 152 | 0.0 ± 0.0 | 113.6 ± 21.4 |
| road_closure | max_pressure_spillback | 1 | uniform | on | 3 | 4264 ± 193 | 567 ± 256 | 11.7 ± 5.1 | 363 ± 187 | 0.0 ± 0.0 | 110.5 ± 22.8 |

## Compute cost

9 runs ok, 0 failed · experiment wall time 150.5 s with [2] worker(s) · sum of run wall times 276.6 s · 175.7× faster than real time per run · data 43.9 MB (4.88 MB/run, 3.25 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 31.8 | 5.67 |
| max_pressure | 31.1 | 5.55 |
| max_pressure_spillback | 29.3 | 5.22 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
