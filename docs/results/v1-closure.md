# Experiment report: `v1-closure`

Created 2026-11-02T01:25:18 · baseline **fixed_time** · code `c0cbfb9` · SUMO 1.28.0

Matrix: scenarios road_closure · controllers actuated, fixed_time, max_pressure, rl · seeds [1, 2, 3] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Reproduce:

```bash
python -m teamb.experiments run --name v1-closure --scenarios road_closure --controllers fixed_time,actuated,max_pressure,rl --seeds 1-3 --workers 6
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `road_closure`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 3 | 119.6 ± 3.7 | baseline | – | – | 587.3 ± 62.9 | 3.21 ± 0.22 | 6.5 ± 2.5% | 195.8 ± 4.3 | 41.8 ± 4.5 | 22.0 ± 0.0 | 17 ± 72 | – |
| actuated | 1 | uniform | on | 3 | 83.8 ± 1.2 | 29.9 ± 3.0% | -35.8 ± 4.7 | 0.003 | 541.0 ± 64.6 | 2.86 ± 0.10 | 2.3 ± 0.2% | 124.8 ± 4.2 | 38.6 ± 3.9 | 10.3 ± 1.4 | 98 ± 52 | – |
| max_pressure | 1 | uniform | on | 3 | 94.7 ± 13.7 | 20.8 ± 12.9% | -24.9 ± 15.9 | 0.043 | 560.6 ± 46.8 | 3.57 ± 0.79 | 2.3 ± 0.4% | 135.4 ± 22.3 | 49.6 ± 2.9 | 11.0 ± 2.5 | 105 ± 232 | – |
| rl | 1 | uniform | on | 3 | 170.2 ± 101.3 | -42.0 ± 79.8% | 50.6 ± 97.6 | 0.156 | 846.3 ± 394.1 | 5.51 ± 2.81 | 2.9 ± 2.5% | 202.6 ± 96.3 | 134.4 ± 108.9 | 17.7 ± 7.6 | 1888 ± 1898 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 12 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.06 ± 0.01 | 0.88 ± 0.22 | 0.36 ± 0.04 | 0 ± 0 | 0 ± 0 |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | actuated | 1 | 3 | 934 ± 40 | 0 | 56.26 ± 7.65 | – | – | – | 98 ± 52 |
| road_closure | fixed_time | 1 | 3 | – | 3 | 54.40 ± 12.60 | – | – | – | 17 ± 72 |
| road_closure | max_pressure | 1 | 3 | 1038 ± 1239 | 1 | 70.47 ± 22.90 | – | – | – | 105 ± 232 |
| road_closure | rl | 1 | 3 | 1716 | 2 | 151.23 ± 121.45 | – | – | – | 1888 ± 1898 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| road_closure | actuated | 1 | uniform | on | 3 | 3743 ± 166 | 90 ± 5 | 2.3 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 82.4 ± 1.2 |
| road_closure | fixed_time | 1 | uniform | on | 3 | 3583 ± 148 | 248 ± 99 | 6.5 ± 2.5 | 39 ± 92 | 0.0 ± 0.0 | 118.3 ± 3.1 |
| road_closure | max_pressure | 1 | uniform | on | 3 | 3745 ± 143 | 88 ± 18 | 2.3 ± 0.4 | 0 ± 0 | 0.0 ± 0.0 | 92.9 ± 13.3 |
| road_closure | rl | 1 | uniform | on | 3 | 3721 ± 107 | 112 ± 98 | 2.9 ± 2.5 | 0 ± 0 | 0.3 ± 1.4 | 169.6 ± 112.0 |

## Compute cost

12 runs ok, 0 failed · experiment wall time 69.2 s with [6] worker(s) · sum of run wall times 387.7 s · 167.1× faster than real time per run · data 51.4 MB (4.28 MB/run, 2.85 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| actuated | 36.1 | 6.44 |
| fixed_time | 37.5 | 6.72 |
| max_pressure | 26.4 | 4.69 |
| rl | 29.2 | 5.2 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
