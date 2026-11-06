# Experiment report: `confirm_emergency_125`

Created 2026-11-05T05:05:03 · baseline **max_pressure** · code `cd556b8` · SUMO 1.28.0

Matrix: scenarios emergency-5601c3 · controllers max_pressure, max_pressure_spillback-44ec25 · seeds [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `emergency-5601c3` = `{"demand_scale": 1.25}`

Controller parameters: `max_pressure_spillback-44ec25` = `{"congestion_threshold": 8, "downstream_penalty": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name confirm_emergency_125 --scenarios emergency --controllers max_pressure,max_pressure_spillback --seeds 31-60 --workers 2 --scenario-params '{"demand_scale":1.25}' --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.25}}' --baseline max_pressure --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `emergency-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **max_pressure** | 1 | uniform | on | 30 | 46.6 ± 4.0 | baseline | – | – | 214.5 ± 16.2 | 1.66 ± 0.18 | 3.0 ± 0.3% | 51.5 ± 5.7 | 40.5 ± 2.1 | 6.8 ± 0.8 | 8 ± 16 | 112.7 ± 3.1 |
| max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 52.0 ± 5.0 | -13.1 ± 9.1% | 5.4 ± 4.4 | 0.016 | 243.4 ± 24.2 | 1.84 ± 0.20 | 3.4 ± 0.6% | 63.0 ± 8.1 | 38.6 ± 1.4 | 8.2 ± 1.1 | 22 ± 30 | 116.4 ± 4.6 |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 60 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.04 ± 0.00 | 0.42 ± 0.04 | 0.37 ± 0.02 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | max_pressure | 1 | on | 30 | 10.0 ± 0.0 | 112.7 ± 3.1 | 34.9 ± 3.1 | 46.6 ± 4.0 | 18.4 ± 4.2 | – | – |
| emergency | max_pressure_spillback-44ec25 | 1 | on | 30 | 10.0 ± 0.0 | 116.4 ± 4.6 | 38.7 ± 4.6 | 52.0 ± 5.0 | 24.4 ± 5.3 | – | – |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | max_pressure | 1 | uniform | on | 30 | 4076 ± 18 | 126 ± 14 | 3.0 ± 0.3 | 0 ± 0 | 0.0 ± 0.0 | 46.0 ± 4.2 |
| emergency | max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 4058 ± 27 | 144 ± 25 | 3.4 ± 0.6 | 5 ± 6 | 0.0 ± 0.1 | 51.9 ± 5.5 |

## Compute cost

60 runs ok, 0 failed · experiment wall time 340.7 s with [2] worker(s) · sum of run wall times 675.7 s · 399.6× faster than real time per run · data 265.0 MB (4.42 MB/run, 3.53 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure | 11.2 | 2.25 |
| max_pressure_spillback-44ec25 | 11.3 | 2.29 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
