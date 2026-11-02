# Experiment report: `v1-security`

Created 2026-11-02T01:25:18 · baseline **fixed_time** · code `c0cbfb9` · SUMO 1.28.0

Matrix: scenarios fake_data_attack · controllers fixed_time, max_pressure, max_pressure_probe · seeds [1, 2, 3] · coverage 0.25 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Reproduce:

```bash
python -m teamb.experiments run --name v1-security --scenarios fake_data_attack --controllers fixed_time,max_pressure,max_pressure_probe --coverages 25 --seeds 1-3 --workers 6
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `fake_data_attack`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 0.25 | uniform | on | 3 | 79.5 ± 28.6 | baseline | – | – | 295.3 ± 134.3 | 1.81 ± 0.76 | 4.0 ± 2.3% | 120.0 ± 52.3 | 31.4 ± 1.1 | 17.3 ± 6.3 | 0 ± 0 | – |
| max_pressure | 0.25 | uniform | on | 3 | 29.4 ± 5.4 | 62.4 ± 16.6% | -50.1 ± 31.7 | 0.042 | 166.7 ± 15.0 | 1.01 ± 0.25 | 2.3 ± 0.5% | 28.7 ± 7.1 | 30.2 ± 3.7 | 3.3 ± 1.4 | 0 ± 0 | – |
| max_pressure_probe | 0.25 | uniform | on | 3 | 175.6 ± 57.8 | -126.6 ± 147.8% | 96.1 ± 85.9 | 0.042 | 791.3 ± 298.8 | 3.99 ± 1.01 | 8.6 ± 5.0% | 250.6 ± 83.9 | 85.2 ± 30.0 | 29.7 ± 6.3 | 1303 ± 483 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 0.25 | 9 | 0.262 ± 0.003 | 1.47 ± 0.46 | -0.01 ± 0.15 | 0.09 ± 0.24 | -0.12 ± 0.18 | 0.04 ± 0.14 | 0.90 ± 0.71 | 0.78 ± 0.47 | 108 ± 7 | 0 ± 0 |

## Fake-data attack and the cross-check

| scenario | controller | cov | sampling | n | detected | detection delay s | alert s | false alarm s | delay s |
|---|---|---|---|---|---|---|---|---|---|
| fake_data_attack | fixed_time | 0.25 | uniform | 3 | 100% | 2.0 ± 0.0 | 1807 ± 0 | 0 ± 0 | 79.5 ± 28.6 |
| fake_data_attack | max_pressure | 0.25 | uniform | 3 | 100% | 2.0 ± 0.0 | 1807 ± 0 | 0 ± 0 | 29.4 ± 5.4 |
| fake_data_attack | max_pressure_probe | 0.25 | uniform | 3 | 100% | 2.0 ± 0.0 | 1807 ± 0 | 0 ± 0 | 175.6 ± 57.8 |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| fake_data_attack | fixed_time | 0.25 | 3 | 351 | 2 | 23.02 ± 27.88 | – | – | – | 0 ± 0 |
| fake_data_attack | max_pressure | 0.25 | 3 | 484 ± 1189 | 0 | 4.53 ± 6.62 | – | – | – | 0 ± 0 |
| fake_data_attack | max_pressure_probe | 0.25 | 3 | – | 3 | 138.06 ± 31.32 | – | – | – | 1303 ± 483 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fake_data_attack | fixed_time | 0.25 | uniform | on | 3 | 3207 ± 165 | 133 ± 74 | 4.0 ± 2.3 | 0 ± 1 | 0.0 ± 0.0 | 80.0 ± 34.6 |
| fake_data_attack | max_pressure | 0.25 | uniform | on | 3 | 3261 ± 72 | 78 ± 20 | 2.3 ± 0.5 | 0 ± 1 | 0.0 ± 0.0 | 29.0 ± 5.2 |
| fake_data_attack | max_pressure_probe | 0.25 | uniform | on | 3 | 3051 ± 245 | 288 ± 160 | 8.6 ± 5.0 | 2 ± 7 | 1.3 ± 3.8 | 183.4 ± 35.0 |

## Compute cost

9 runs ok, 0 failed · experiment wall time 34.9 s with [6] worker(s) · sum of run wall times 159.7 s · 253.5× faster than real time per run · data 33.7 MB (3.75 MB/run, 3.0 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 19.0 | 3.94 |
| max_pressure | 16.5 | 3.38 |
| max_pressure_probe | 17.7 | 3.69 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
