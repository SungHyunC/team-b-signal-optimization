# Experiment report: `lesson1_smoke`

Created 2026-11-04T22:58:12 · baseline **fixed_time** · code `3ad4329` · SUMO 1.28.0

Matrix: scenarios rush_hour · controllers fixed_time, max_pressure · seeds [1] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Reproduce:

```bash
python -m teamb.experiments run --name lesson1_smoke --scenarios rush_hour --controllers fixed_time,max_pressure --seeds 1 --workers 1 --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `rush_hour`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 1 | 76.0 | baseline | – | – | 273.0 | 1.72 | 3.5% | 113.0 | 30.9 | 17.0 | 0 | – |
| max_pressure | 1 | uniform | on | 1 | 31.8 | 58.2% | -44.2 | – | 173.0 | 1.13 | 2.4% | 31.7 | 31.9 | 4.0 | 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 2 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.03 ± 0.06 | 0.24 ± 0.99 | 0.23 ± 0.78 | 0 ± 0 | 0 ± 0 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rush_hour | fixed_time | 1 | uniform | on | 1 | 3235 | 118 | 3.5 | 0 | 0.0 | 75.2 |
| rush_hour | max_pressure | 1 | uniform | on | 1 | 3274 | 79 | 2.4 | 0 | 0.0 | 31.4 |

## Compute cost

2 runs ok, 0 failed · experiment wall time 17.4 s with [1] worker(s) · sum of run wall times 17.4 s · 517.5× faster than real time per run · data 7.5 MB (3.73 MB/run, 2.99 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 9.2 | 1.82 |
| max_pressure | 8.2 | 1.58 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
