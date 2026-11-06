# Experiment report: `mild_125_closure`

Created 2026-11-05T04:30:48 · baseline **fixed_time** · code `1568f72` · SUMO 1.28.0

Matrix: scenarios road_closure-5601c3 · controllers max_pressure, max_pressure_spillback-44ec25 · seeds [4, 5, 6] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `road_closure-5601c3` = `{"demand_scale": 1.25}`

Controller parameters: `max_pressure_spillback-44ec25` = `{"congestion_threshold": 8, "downstream_penalty": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name mild_125_closure --scenarios road_closure --controllers max_pressure,max_pressure_spillback --seeds 4-6 --workers 2 --scenario-params '{"demand_scale":1.25}' --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.25}}' --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `road_closure-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure | 1 | uniform | on | 3 | 132.1 ± 24.0 | – | – | – | 622.5 ± 113.4 | 5.39 ± 0.88 | 8.8 ± 5.0% | 193.6 ± 36.3 | 68.8 ± 19.7 | 16.3 ± 1.4 | 532 ± 278 | – |
| max_pressure_spillback-44ec25 | 1 | uniform | on | 3 | 105.5 ± 10.5 | – | – | – | 554.5 ± 83.5 | 3.99 ± 0.48 | 7.9 ± 3.7% | 159.9 ± 16.0 | 48.9 ± 10.8 | 15.3 ± 2.9 | 57 ± 47 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 6 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.06 ± 0.00 | 1.01 ± 0.12 | 0.58 ± 0.09 | 0 ± 0 | 0 ± 0 |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | max_pressure | 1 | 3 | – | 3 | 123.00 ± 20.97 | – | – | – | 532 ± 278 |
| road_closure | max_pressure_spillback-44ec25 | 1 | 3 | – | 3 | 80.90 ± 14.80 | – | – | – | 57 ± 47 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | max_pressure | 1 | uniform | on | 3 | 4426 ± 161 | 430 ± 271 | 8.8 ± 5.0 | 189 ± 216 | 0.0 ± 0.0 | 132.3 ± 24.3 |
| road_closure | max_pressure_spillback-44ec25 | 1 | uniform | on | 3 | 4472 ± 237 | 385 ± 194 | 7.9 ± 3.7 | 182 ± 220 | 0.0 ± 0.0 | 104.1 ± 10.6 |

## Compute cost

6 runs ok, 0 failed · experiment wall time 51.3 s with [2] worker(s) · sum of run wall times 102.2 s · 316.9× faster than real time per run · data 29.8 MB (4.97 MB/run, 3.32 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure | 17.7 | 3.07 |
| max_pressure_spillback-44ec25 | 16.4 | 2.83 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
