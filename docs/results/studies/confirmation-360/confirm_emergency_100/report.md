# Experiment report: `confirm_emergency_100`

Created 2026-11-05T04:59:22 · baseline **max_pressure** · code `cd556b8` · SUMO 1.28.0

Matrix: scenarios emergency · controllers max_pressure, max_pressure_spillback-44ec25 · seeds [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Controller parameters: `max_pressure_spillback-44ec25` = `{"congestion_threshold": 8, "downstream_penalty": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name confirm_emergency_100 --scenarios emergency --controllers max_pressure,max_pressure_spillback --seeds 31-60 --workers 2 --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.25}}' --baseline max_pressure --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `emergency`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **max_pressure** | 1 | uniform | on | 30 | 29.9 ± 0.4 | baseline | – | – | 168.2 ± 0.9 | 1.03 ± 0.01 | 2.6 ± 0.1% | 29.7 ± 0.5 | 30.1 ± 0.4 | 3.2 ± 0.1 | 0 ± 0 | 100.5 ± 1.3 |
| max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 30.6 ± 0.4 | -2.6 ± 1.1% | 0.8 ± 0.3 | <0.001 | 170.5 ± 1.1 | 1.06 ± 0.01 | 2.7 ± 0.1% | 31.1 ± 0.5 | 30.1 ± 0.4 | 3.4 ± 0.2 | 0 ± 0 | 101.5 ± 1.6 |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 60 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.02 ± 0.00 | 0.15 ± 0.00 | 0.15 ± 0.00 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | max_pressure | 1 | on | 30 | 10.0 ± 0.0 | 100.5 ± 1.3 | 22.7 ± 1.3 | 29.9 ± 0.4 | 6.3 ± 0.6 | – | – |
| emergency | max_pressure_spillback-44ec25 | 1 | on | 30 | 10.0 ± 0.0 | 101.5 ± 1.6 | 23.7 ± 1.6 | 30.6 ± 0.4 | 6.5 ± 0.7 | – | – |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | max_pressure | 1 | uniform | on | 30 | 3279 ± 21 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 29.5 ± 0.4 |
| emergency | max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 3278 ± 21 | 89 ± 5 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 30.2 ± 0.4 |

## Compute cost

60 runs ok, 0 failed · experiment wall time 310.9 s with [2] worker(s) · sum of run wall times 619.7 s · 435.7× faster than real time per run · data 226.2 MB (3.77 MB/run, 3.02 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure | 10.3 | 2.06 |
| max_pressure_spillback-44ec25 | 10.3 | 2.06 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
