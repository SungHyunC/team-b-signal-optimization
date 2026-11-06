# Experiment report: `confirm_rush_100`

Created 2026-11-05T04:48:47 · baseline **max_pressure** · code `cd556b8` · SUMO 1.28.0

Matrix: scenarios rush_hour · controllers max_pressure, max_pressure_spillback-44ec25 · seeds [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Controller parameters: `max_pressure_spillback-44ec25` = `{"congestion_threshold": 8, "downstream_penalty": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name confirm_rush_100 --scenarios rush_hour --controllers max_pressure,max_pressure_spillback --seeds 31-60 --workers 2 --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.25}}' --baseline max_pressure --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `rush_hour`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **max_pressure** | 1 | uniform | on | 30 | 29.2 ± 0.4 | baseline | – | – | 166.3 ± 0.8 | 1.00 ± 0.01 | 2.6 ± 0.1% | 29.0 ± 0.5 | 29.4 ± 0.4 | 3.1 ± 0.1 | 0 ± 0 | – |
| max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 29.6 ± 0.4 | -1.6 ± 1.2% | 0.4 ± 0.3 | 0.012 | 168.0 ± 1.1 | 1.02 ± 0.02 | 2.6 ± 0.1% | 29.8 ± 0.6 | 29.4 ± 0.4 | 3.2 ± 0.2 | 0 ± 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 60 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.02 ± 0.00 | 0.14 ± 0.00 | 0.14 ± 0.00 | 0 ± 0 | 0 ± 0 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rush_hour | max_pressure | 1 | uniform | on | 30 | 3269 ± 22 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 28.8 ± 0.4 |
| rush_hour | max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 3270 ± 21 | 87 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 29.3 ± 0.4 |

## Compute cost

60 runs ok, 0 failed · experiment wall time 275.2 s with [2] worker(s) · sum of run wall times 549.1 s · 491.7× faster than real time per run · data 224.3 MB (3.74 MB/run, 2.99 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure | 9.2 | 1.82 |
| max_pressure_spillback-44ec25 | 9.1 | 1.78 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
