# Experiment report: `mild_110_rush`

Created 2026-11-05T04:31:17 · baseline **fixed_time** · code `1568f72` · SUMO 1.28.0

Matrix: scenarios rush_hour · controllers max_pressure, max_pressure_spillback-660065 · seeds [4, 5, 6] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Controller parameters: `max_pressure_spillback-660065` = `{"congestion_threshold": 8, "downstream_penalty": 1.1}`

Reproduce:

```bash
python -m teamb.experiments run --name mild_110_rush --scenarios rush_hour --controllers max_pressure,max_pressure_spillback --seeds 4-6 --workers 2 --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.10}}' --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `rush_hour`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure | 1 | uniform | on | 3 | 29.8 ± 3.7 | – | – | – | 166.0 ± 7.5 | 1.03 ± 0.16 | 2.7 ± 0.5% | 29.9 ± 4.9 | 29.8 ± 2.2 | 3.3 ± 1.4 | 0 ± 0 | – |
| max_pressure_spillback-660065 | 1 | uniform | on | 3 | 29.5 ± 4.0 | – | – | – | 167.0 ± 8.6 | 1.01 ± 0.17 | 2.7 ± 0.2% | 29.7 ± 4.9 | 29.1 ± 2.9 | 3.3 ± 1.4 | 0 ± 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 6 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.02 ± 0.00 | 0.15 ± 0.02 | 0.15 ± 0.02 | 0 ± 0 | 0 ± 0 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rush_hour | max_pressure | 1 | uniform | on | 3 | 3333 ± 249 | 91 ± 22 | 2.7 ± 0.5 | 2 ± 3 | 0.0 ± 0.0 | 29.5 ± 3.7 |
| rush_hour | max_pressure_spillback-660065 | 1 | uniform | on | 3 | 3331 ± 250 | 92 ± 12 | 2.7 ± 0.2 | 2 ± 3 | 0.0 ± 0.0 | 29.1 ± 4.0 |

## Compute cost

6 runs ok, 0 failed · experiment wall time 28.8 s with [2] worker(s) · sum of run wall times 57.3 s · 471.4× faster than real time per run · data 22.7 MB (3.79 MB/run, 3.03 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure | 9.5 | 1.87 |
| max_pressure_spillback-660065 | 9.6 | 1.89 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
