# Experiment report: `confirm_rush_125`

Created 2026-11-05T04:54:11 · baseline **max_pressure** · code `cd556b8` · SUMO 1.28.0

Matrix: scenarios rush_hour-5601c3 · controllers max_pressure, max_pressure_spillback-44ec25 · seeds [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `rush_hour-5601c3` = `{"demand_scale": 1.25}`

Controller parameters: `max_pressure_spillback-44ec25` = `{"congestion_threshold": 8, "downstream_penalty": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name confirm_rush_125 --scenarios rush_hour --controllers max_pressure,max_pressure_spillback --seeds 31-60 --workers 2 --scenario-params '{"demand_scale":1.25}' --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.25}}' --baseline max_pressure --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `rush_hour-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **max_pressure** | 1 | uniform | on | 30 | 44.0 ± 4.6 | baseline | – | – | 206.4 ± 20.9 | 1.56 ± 0.21 | 3.0 ± 0.4% | 48.6 ± 7.0 | 38.6 ± 1.8 | 6.3 ± 0.8 | 20 ± 28 | – |
| max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 50.2 ± 5.1 | -17.6 ± 12.9% | 6.1 ± 6.2 | 0.051 | 241.7 ± 31.1 | 1.77 ± 0.20 | 3.5 ± 0.8% | 61.0 ± 8.8 | 37.3 ± 1.1 | 7.6 ± 1.1 | 28 ± 53 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 60 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.03 ± 0.00 | 0.39 ± 0.04 | 0.35 ± 0.02 | 0 ± 0 | 0 ± 0 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rush_hour | max_pressure | 1 | uniform | on | 30 | 4064 ± 21 | 128 ± 19 | 3.0 ± 0.4 | 3 ± 4 | 0.0 ± 0.0 | 43.6 ± 4.9 |
| rush_hour | max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 4044 ± 37 | 148 ± 34 | 3.5 ± 0.8 | 14 ± 19 | 0.0 ± 0.0 | 50.2 ± 6.1 |

## Compute cost

60 runs ok, 0 failed · experiment wall time 323.7 s with [2] worker(s) · sum of run wall times 642.6 s · 420.2× faster than real time per run · data 262.9 MB (4.38 MB/run, 3.51 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure | 10.5 | 2.11 |
| max_pressure_spillback-44ec25 | 10.9 | 2.18 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
