# Experiment report: `congestion_pilot_nominal`

Created 2026-11-05T03:09:48 · baseline **fixed_time** · code `912e680` · SUMO 1.28.0

Matrix: scenarios rush_hour · controllers max_pressure, max_pressure_spillback · seeds [1, 2, 3] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Reproduce:

```bash
python -m teamb.experiments run --name congestion_pilot_nominal --scenarios rush_hour --controllers max_pressure,max_pressure_spillback --seeds 1-3 --workers 2 --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `rush_hour`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure | 1 | uniform | on | 3 | 29.4 ± 5.4 | – | – | – | 166.7 ± 15.0 | 1.01 ± 0.25 | 2.3 ± 0.5% | 28.7 ± 7.1 | 30.2 ± 3.7 | 3.3 ± 1.4 | 0 ± 0 | – |
| max_pressure_spillback | 1 | uniform | on | 3 | 31.2 ± 4.7 | – | – | – | 173.0 ± 13.8 | 1.10 ± 0.25 | 2.4 ± 0.5% | 33.5 ± 8.7 | 28.6 ± 0.8 | 3.7 ± 1.4 | 0 ± 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 6 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.02 ± 0.00 | 0.15 ± 0.02 | 0.15 ± 0.02 | 0 ± 0 | 0 ± 0 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rush_hour | max_pressure | 1 | uniform | on | 3 | 3261 ± 72 | 78 ± 20 | 2.3 ± 0.5 | 0 ± 1 | 0.0 ± 0.0 | 29.0 ± 5.2 |
| rush_hour | max_pressure_spillback | 1 | uniform | on | 3 | 3260 ± 76 | 80 ± 17 | 2.4 ± 0.5 | 0 ± 1 | 0.0 ± 0.0 | 30.8 ± 4.5 |

## Compute cost

6 runs ok, 0 failed · experiment wall time 52.4 s with [2] worker(s) · sum of run wall times 104.4 s · 258.6× faster than real time per run · data 22.4 MB (3.74 MB/run, 2.99 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure | 17.7 | 3.66 |
| max_pressure_spillback | 17.1 | 3.56 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
