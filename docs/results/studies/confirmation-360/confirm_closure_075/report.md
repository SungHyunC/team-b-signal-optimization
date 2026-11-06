# Experiment report: `confirm_closure_075`

Created 2026-11-05T05:10:33 · baseline **max_pressure** · code `cd556b8` · SUMO 1.28.0

Matrix: scenarios road_closure-193e6a · controllers max_pressure, max_pressure_spillback-44ec25 · seeds [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Scenario parameters: `road_closure-193e6a` = `{"demand_scale": 0.75}`

Controller parameters: `max_pressure_spillback-44ec25` = `{"congestion_threshold": 8, "downstream_penalty": 1.25}`

Reproduce:

```bash
python -m teamb.experiments run --name confirm_closure_075 --scenarios road_closure --controllers max_pressure,max_pressure_spillback --seeds 31-60 --workers 2 --scenario-params '{"demand_scale":0.75}' --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.25}}' --baseline max_pressure --strict-validation
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `road_closure-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **max_pressure** | 1 | uniform | on | 30 | 44.6 ± 1.4 | baseline | – | – | 324.3 ± 8.0 | 1.52 ± 0.05 | 2.1 ± 0.1% | 56.9 ± 2.2 | 30.7 ± 0.6 | 3.6 ± 0.2 | 1 ± 1 | – |
| max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 45.4 ± 1.7 | -1.9 ± 2.2% | 0.8 ± 1.0 | 0.097 | 328.5 ± 10.0 | 1.55 ± 0.06 | 2.1 ± 0.1% | 58.4 ± 2.6 | 30.9 ± 0.8 | 3.7 ± 0.2 | 2 ± 2 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 60 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.03 ± 0.00 | 0.16 ± 0.01 | 0.16 ± 0.00 | 0 ± 0 | 0 ± 0 |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | max_pressure | 1 | 30 | 281 ± 30 | 0 | 15.70 ± 1.15 | – | – | – | 1 ± 1 |
| road_closure | max_pressure_spillback-44ec25 | 1 | 30 | 313 ± 48 | 0 | 16.50 ± 1.37 | – | – | – | 2 ± 2 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | max_pressure | 1 | uniform | on | 30 | 2813 ± 19 | 61 ± 3 | 2.1 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 44.0 ± 1.4 |
| road_closure | max_pressure_spillback-44ec25 | 1 | uniform | on | 30 | 2813 ± 19 | 62 ± 3 | 2.1 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 44.8 ± 1.7 |

## Compute cost

60 runs ok, 0 failed · experiment wall time 329.6 s with [2] worker(s) · sum of run wall times 657.9 s · 492.4× faster than real time per run · data 211.8 MB (3.53 MB/run, 2.35 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure | 10.9 | 1.83 |
| max_pressure_spillback-44ec25 | 11.0 | 1.84 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
