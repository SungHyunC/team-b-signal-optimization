# Experiment report: `coverage_sweep`

Created 2026-11-02T00:58:59 · baseline **fixed_time** · code `49b7d1b-dirty` · SUMO 1.28.0

Matrix: scenarios rush_hour · controllers fixed_time, max_pressure_probe · seeds [1] · coverage 0.1, 0.25, 0.5, 1 · sampling approach_biased, speed_biased, uniform · EV preemption on · warm-up 900 s · run end 1800 s

Reproduce:

```bash
python -m teamb.experiments run --name coverage_sweep --scenarios rush_hour --controllers fixed_time --seeds 1 --coverages 1.0 --end 1800 --workers 1 --no-report
python -m teamb.experiments run --name coverage_sweep --scenarios rush_hour --controllers max_pressure_probe --seeds 1 --coverages 10,25,50,100 --sampling uniform,approach_biased,speed_biased --end 1800 --workers 2
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `rush_hour`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 1 | 59.5 | baseline | – | – | 240.0 | 1.37 | 20.9% | 93.8 | 25.1 | 14.0 | 0 | – |
| max_pressure_probe | 1 | approach_biased | on | 1 | 38.0 | 36.3% | -21.6 | – | 181.2 | 1.13 | 18.5% | 24.6 | 53.8 | 5.0 | 0 | – |
| max_pressure_probe | 1 | speed_biased | on | 1 | 51.5 | 13.5% | -8.0 | – | 259.3 | 1.05 | 20.8% | 20.8 | 92.6 | 9.0 | 0 | – |
| max_pressure_probe | 1 | uniform | on | 1 | 38.0 | 36.3% | -21.6 | – | 181.2 | 1.13 | 18.5% | 24.6 | 53.8 | 5.0 | 0 | – |
| max_pressure_probe | 0.5 | approach_biased | on | 1 | 62.6 | -5.1% | 3.0 | – | 286.9 | 1.56 | 27.8% | 25.5 | 119.0 | 13.0 | 15 | – |
| max_pressure_probe | 0.5 | speed_biased | on | 1 | 48.9 | 17.9% | -10.7 | – | 213.1 | 1.01 | 21.9% | 22.9 | 83.3 | 8.0 | 0 | – |
| max_pressure_probe | 0.5 | uniform | on | 1 | 39.6 | 33.5% | -19.9 | – | 189.8 | 1.07 | 19.9% | 24.0 | 58.7 | 6.0 | 0 | – |
| max_pressure_probe | 0.25 | approach_biased | on | 1 | 62.2 | -4.4% | 2.6 | – | 331.2 | 1.38 | 26.1% | 21.0 | 118.3 | 10.0 | 25 | – |
| max_pressure_probe | 0.25 | speed_biased | on | 1 | 47.1 | 20.8% | -12.4 | – | 218.3 | 1.09 | 21.7% | 26.5 | 74.9 | 8.0 | 0 | – |
| max_pressure_probe | 0.25 | uniform | on | 1 | 37.8 | 36.6% | -21.8 | – | 177.5 | 0.99 | 19.3% | 23.1 | 55.4 | 6.0 | 0 | – |
| max_pressure_probe | 0.1 | approach_biased | on | 1 | 41.0 | 31.1% | -18.5 | – | 191.6 | 1.01 | 22.1% | 24.9 | 60.5 | 7.0 | 0 | – |
| max_pressure_probe | 0.1 | speed_biased | on | 1 | 44.5 | 25.3% | -15.0 | – | 188.8 | 1.11 | 19.9% | 34.8 | 56.1 | 8.0 | 0 | – |
| max_pressure_probe | 0.1 | uniform | on | 1 | 43.8 | 26.4% | -15.7 | – | 188.7 | 1.07 | 19.7% | 31.7 | 58.1 | 7.0 | 0 | – |

_Some rows are paired with a baseline run at another coverage/sampling (fixed-time ignores sensor data)._

## Coverage sweep (sampling bias)

Queue error = probe queue estimate (halted reports ÷ coverage) − true halted vehicles per approach, every 5 s. Bias > 0 overestimates. Adjusted = ÷ measured penetration instead of ÷ coverage.

| scenario | controller | sampling | coverage | n | delay s | Δ vs base | queue MAE | queue bias | adj. bias | flow MAE veh/h | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rush_hour | max_pressure_probe | approach_biased | 0.1 | 1 | 41.0 | 31.1% | 1.71 | -0.96 | -0.78 | 260 | 0 |
| rush_hour | max_pressure_probe | approach_biased | 0.25 | 1 | 62.2 | -4.4% | 2.01 | -1.37 | -0.82 | 225 | 0 |
| rush_hour | max_pressure_probe | approach_biased | 0.5 | 1 | 62.6 | -5.1% | 1.84 | -1.54 | -0.79 | 158 | 0 |
| rush_hour | max_pressure_probe | approach_biased | 1 | 1 | 38.0 | 36.3% | 0.00 | 0.00 | 0.04 | 0 | 0 |
| rush_hour | max_pressure_probe | speed_biased | 0.1 | 1 | 44.5 | 25.3% | 1.71 | -1.50 | -1.46 | 147 | 0 |
| rush_hour | max_pressure_probe | speed_biased | 0.25 | 1 | 47.1 | 20.8% | 1.64 | -1.52 | -1.44 | 99 | 0 |
| rush_hour | max_pressure_probe | speed_biased | 0.5 | 1 | 48.9 | 17.9% | 1.53 | -1.48 | -1.46 | 54 | 0 |
| rush_hour | max_pressure_probe | speed_biased | 1 | 1 | 51.5 | 13.5% | 1.48 | -1.48 | -1.46 | 0 | 0 |
| rush_hour | max_pressure_probe | uniform | 0.1 | 1 | 43.8 | 26.4% | 1.63 | -0.86 | -0.80 | 133 | 0 |
| rush_hour | max_pressure_probe | uniform | 0.25 | 1 | 37.8 | 36.6% | 1.09 | -0.42 | -0.25 | 102 | 0 |
| rush_hour | max_pressure_probe | uniform | 0.5 | 1 | 39.6 | 33.5% | 0.63 | -0.18 | -0.11 | 55 | 0 |
| rush_hour | max_pressure_probe | uniform | 1 | 1 | 38.0 | 36.3% | 0.00 | 0.00 | 0.04 | 0 | 0 |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| approach_biased | 0.1 | 1 | 0.102 | 1.71 | -0.96 | -0.23 | -1.69 | -0.78 | 0.16 | 0.27 | 260 | 0 |
| approach_biased | 0.25 | 1 | 0.264 | 2.01 | -1.37 | 0.16 | -2.90 | -0.82 | 0.44 | 0.66 | 225 | 0 |
| approach_biased | 0.5 | 1 | 0.486 | 1.84 | -1.54 | 0.03 | -3.11 | -0.79 | 0.43 | 0.53 | 158 | 0 |
| approach_biased | 1 | 1 | 1.000 | 0.00 | 0.00 | 0.00 | 0.00 | 0.04 | 0.14 | 0.14 | 0 | 0 |
| speed_biased | 0.1 | 1 | 0.099 | 1.71 | -1.50 | -0.90 | -2.09 | -1.46 | 0.18 | 0.18 | 147 | 0 |
| speed_biased | 0.25 | 1 | 0.244 | 1.64 | -1.52 | -0.53 | -2.50 | -1.44 | 0.20 | 0.20 | 99 | 0 |
| speed_biased | 0.5 | 1 | 0.501 | 1.53 | -1.48 | -0.44 | -2.53 | -1.46 | 0.19 | 0.19 | 54 | 0 |
| speed_biased | 1 | 1 | 1.000 | 1.48 | -1.48 | -0.36 | -2.60 | -1.46 | 0.19 | 0.19 | 0 | 0 |
| uniform | 0.1 | 1 | 0.099 | 1.63 | -0.86 | -0.42 | -1.29 | -0.80 | 0.18 | 0.20 | 133 | 0 |
| uniform | 0.25 | 1 | 0.244 | 1.09 | -0.42 | -0.11 | -0.73 | -0.25 | 0.15 | 0.15 | 102 | 0 |
| uniform | 0.5 | 1 | 0.501 | 0.63 | -0.18 | -0.00 | -0.35 | -0.11 | 0.19 | 0.20 | 55 | 0 |
| uniform | 1 | 2 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.04 ± 0.03 | 0.18 ± 0.47 | 0.18 ± 0.48 | 0 ± 0 | 0 ± 0 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rush_hour | fixed_time | 1 | uniform | on | 1 | 638 | 169 | 20.9 | 0 | 0.0 | 56.0 |
| rush_hour | max_pressure_probe | 1 | approach_biased | on | 1 | 658 | 149 | 18.5 | 0 | 0.0 | 35.5 |
| rush_hour | max_pressure_probe | 1 | speed_biased | on | 1 | 639 | 168 | 20.8 | 0 | 0.0 | 49.0 |
| rush_hour | max_pressure_probe | 1 | uniform | on | 1 | 658 | 149 | 18.5 | 0 | 0.0 | 35.5 |
| rush_hour | max_pressure_probe | 0.1 | approach_biased | on | 1 | 629 | 178 | 22.1 | 0 | 0.0 | 41.0 |
| rush_hour | max_pressure_probe | 0.1 | speed_biased | on | 1 | 646 | 161 | 19.9 | 0 | 0.0 | 43.5 |
| rush_hour | max_pressure_probe | 0.1 | uniform | on | 1 | 648 | 159 | 19.7 | 0 | 0.0 | 41.1 |
| rush_hour | max_pressure_probe | 0.25 | approach_biased | on | 1 | 596 | 211 | 26.1 | 0 | 0.0 | 63.2 |
| rush_hour | max_pressure_probe | 0.25 | speed_biased | on | 1 | 632 | 175 | 21.7 | 0 | 0.0 | 47.8 |
| rush_hour | max_pressure_probe | 0.25 | uniform | on | 1 | 651 | 156 | 19.3 | 0 | 0.0 | 36.2 |
| rush_hour | max_pressure_probe | 0.5 | approach_biased | on | 1 | 583 | 224 | 27.8 | 0 | 0.0 | 68.2 |
| rush_hour | max_pressure_probe | 0.5 | speed_biased | on | 1 | 630 | 177 | 21.9 | 0 | 0.0 | 48.5 |
| rush_hour | max_pressure_probe | 0.5 | uniform | on | 1 | 646 | 161 | 19.9 | 0 | 0.0 | 38.8 |

## Compute cost

13 runs ok, 0 failed · experiment wall time 171.9 s with [1, 2] worker(s) · sum of run wall times 317.4 s · 73.7× faster than real time per run · data 22.5 MB (1.73 MB/run, 3.46 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 23.9 | 12.56 |
| max_pressure_probe | 24.5 | 12.83 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
