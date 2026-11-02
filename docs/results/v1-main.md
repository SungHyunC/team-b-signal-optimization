# Experiment report: `v1-main`

Created 2026-11-02T01:25:18 · baseline **fixed_time** · code `c0cbfb9` · SUMO 1.28.0

Matrix: scenarios emergency, rush_hour · controllers actuated, ai_recommender-6d7df3, coordinated, fixed_time, max_pressure, rl · seeds [1, 2, 3] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end 2700 s

Controller parameters: `ai_recommender-6d7df3` = `{"auto_approve": true}`

Reproduce:

```bash
python -m teamb.experiments run --name v1-main --scenarios rush_hour,emergency --controllers fixed_time,coordinated,actuated,max_pressure,ai_recommender,rl --seeds 1-3 --end 2700 --workers 6 --controller-params '{"ai_recommender": {"auto_approve": true}}'
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `emergency`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 3 | 72.1 ± 5.8 | baseline | – | – | 277.9 ± 34.8 | 1.78 ± 0.31 | 11.9 ± 3.2% | 108.4 ± 13.2 | 32.2 ± 4.9 | 15.7 ± 1.4 | 0 ± 0 | 110.3 ± 7.6 |
| actuated | 1 | uniform | on | 3 | 30.9 ± 4.7 | 57.2 ± 8.5% | -41.3 ± 8.8 | 0.010 | 173.6 ± 7.2 | 1.15 ± 0.26 | 7.0 ± 2.4% | 35.2 ± 8.1 | 25.7 ± 0.5 | 4.0 ± 0.0 | 0 ± 0 | 95.1 ± 4.2 |
| ai_recommender-6d7df3 | 1 | uniform | on | 3 | 39.1 ± 2.6 | 45.8 ± 7.8% | -33.1 ± 8.4 | 0.010 | 188.0 ± 15.5 | 1.23 ± 0.06 | 7.8 ± 2.9% | 29.1 ± 2.9 | 51.4 ± 4.4 | 5.7 ± 1.4 | 0 ± 0 | 90.1 ± 3.8 |
| coordinated | 1 | uniform | on | 3 | 48.7 ± 2.5 | 32.5 ± 8.0% | -23.5 ± 7.6 | 0.010 | 251.2 ± 19.3 | 1.24 ± 0.03 | 8.0 ± 2.4% | 59.7 ± 3.7 | 35.7 ± 0.6 | 9.3 ± 1.4 | 0 ± 0 | 91.7 ± 13.3 |
| max_pressure | 1 | uniform | on | 3 | 29.8 ± 1.8 | 58.7 ± 4.2% | -42.4 ± 6.2 | 0.006 | 167.6 ± 7.4 | 1.04 ± 0.11 | 6.9 ± 2.6% | 29.9 ± 2.3 | 29.6 ± 1.1 | 3.3 ± 1.4 | 0 ± 0 | 90.6 ± 6.5 |
| rl | 1 | uniform | on | 3 | 31.7 ± 4.7 | 55.9 ± 9.2% | -40.4 ± 9.7 | 0.010 | 167.0 ± 12.4 | 1.11 ± 0.11 | 7.2 ± 2.6% | 28.0 ± 4.4 | 36.3 ± 6.3 | 4.0 ± 0.0 | 0 ± 0 | 91.5 ± 9.2 |

## Scenario `rush_hour`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **fixed_time** | 1 | uniform | on | 3 | 71.0 ± 10.5 | baseline | – | – | 272.7 ± 74.4 | 1.62 ± 0.38 | 10.3 ± 1.0% | 106.9 ± 18.3 | 30.3 ± 5.2 | 16.0 ± 2.5 | 0 ± 0 | – |
| actuated | 1 | uniform | on | 3 | 30.7 ± 5.0 | 56.7 ± 6.7% | -40.3 ± 9.1 | 0.013 | 173.0 ± 17.2 | 1.12 ± 0.20 | 7.2 ± 2.5% | 34.5 ± 8.5 | 26.2 ± 0.7 | 3.7 ± 1.4 | 0 ± 0 | – |
| ai_recommender-6d7df3 | 1 | uniform | on | 3 | 37.6 ± 1.8 | 47.0 ± 9.5% | -33.5 ± 11.8 | 0.021 | 184.1 ± 10.7 | 1.18 ± 0.06 | 7.9 ± 3.4% | 27.3 ± 6.2 | 50.3 ± 5.5 | 5.7 ± 1.4 | 0 ± 0 | – |
| coordinated | 1 | uniform | on | 3 | 48.4 ± 2.2 | 31.8 ± 8.4% | -22.6 ± 9.4 | 0.021 | 254.8 ± 16.9 | 1.18 ± 0.05 | 8.3 ± 2.6% | 59.6 ± 2.9 | 35.2 ± 0.8 | 10.0 ± 2.5 | 0 ± 0 | – |
| max_pressure | 1 | uniform | on | 3 | 29.2 ± 2.9 | 58.7 ± 9.9% | -41.8 ± 13.3 | 0.021 | 167.7 ± 14.6 | 1.01 ± 0.17 | 6.9 ± 3.1% | 28.5 ± 5.7 | 30.0 ± 0.6 | 3.3 ± 1.4 | 0 ± 0 | – |
| rl | 1 | uniform | on | 3 | 30.6 ± 4.3 | 56.7 ± 9.9% | -40.4 ± 12.6 | 0.021 | 165.7 ± 6.3 | 1.07 ± 0.12 | 7.1 ± 2.9% | 26.9 ± 2.3 | 35.2 ± 7.0 | 4.0 ± 0.0 | 0 ± 0 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 36 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.03 ± 0.00 | 0.22 ± 0.04 | 0.20 ± 0.02 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | actuated | 1 | on | 3 | 5.0 ± 0.0 | 95.1 ± 4.2 | 23.5 ± 4.3 | 30.9 ± 4.7 | 6.2 ± 2.9 | – | – |
| emergency | ai_recommender-6d7df3 | 1 | on | 3 | 5.0 ± 0.0 | 90.1 ± 3.8 | 18.7 ± 3.6 | 39.1 ± 2.6 | 14.8 ± 3.4 | – | – |
| emergency | coordinated | 1 | on | 3 | 5.0 ± 0.0 | 91.7 ± 13.3 | 20.2 ± 13.2 | 48.8 ± 2.5 | 24.3 ± 3.3 | – | – |
| emergency | fixed_time | 1 | on | 3 | 5.0 ± 0.0 | 110.3 ± 7.6 | 38.8 ± 7.8 | 72.3 ± 5.9 | 21.4 ± 11.6 | – | – |
| emergency | max_pressure | 1 | on | 3 | 5.0 ± 0.0 | 90.6 ± 6.5 | 19.3 ± 6.7 | 29.8 ± 1.8 | 5.5 ± 3.4 | – | – |
| emergency | rl | 1 | on | 3 | 5.0 ± 0.0 | 91.5 ± 9.2 | 20.1 ± 8.9 | 31.8 ± 4.7 | 6.4 ± 3.9 | – | – |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| emergency | actuated | 1 | uniform | on | 3 | 1594 ± 30 | 119 ± 45 | 7.0 ± 2.4 | 1 ± 3 | 0.0 ± 0.0 | 30.0 ± 4.2 |
| emergency | ai_recommender-6d7df3 | 1 | uniform | on | 3 | 1579 ± 27 | 134 ± 53 | 7.8 ± 2.9 | 1 ± 3 | 0.0 ± 0.0 | 38.1 ± 2.1 |
| emergency | coordinated | 1 | uniform | on | 3 | 1576 ± 37 | 137 ± 44 | 8.0 ± 2.4 | 1 ± 3 | 0.0 ± 0.0 | 47.4 ± 2.3 |
| emergency | fixed_time | 1 | uniform | on | 3 | 1510 ± 85 | 203 ± 54 | 11.9 ± 3.2 | 1 ± 3 | 0.0 ± 0.0 | 74.0 ± 11.1 |
| emergency | max_pressure | 1 | uniform | on | 3 | 1595 ± 31 | 118 ± 47 | 6.9 ± 2.6 | 1 ± 3 | 0.0 ± 0.0 | 28.9 ± 1.7 |
| emergency | rl | 1 | uniform | on | 3 | 1589 ± 27 | 124 ± 47 | 7.2 ± 2.6 | 1 ± 3 | 0.0 ± 0.0 | 30.8 ± 4.3 |
| rush_hour | actuated | 1 | uniform | on | 3 | 1586 ± 17 | 122 ± 46 | 7.2 ± 2.5 | 1 ± 3 | 0.0 ± 0.0 | 29.9 ± 5.0 |
| rush_hour | ai_recommender-6d7df3 | 1 | uniform | on | 3 | 1573 ± 35 | 135 ± 62 | 7.9 ± 3.4 | 1 ± 3 | 0.0 ± 0.0 | 36.9 ± 1.6 |
| rush_hour | coordinated | 1 | uniform | on | 3 | 1566 ± 43 | 142 ± 47 | 8.3 ± 2.6 | 1 ± 3 | 0.0 ± 0.0 | 47.3 ± 2.0 |
| rush_hour | fixed_time | 1 | uniform | on | 3 | 1533 ± 66 | 175 ± 12 | 10.3 ± 1.0 | 1 ± 3 | 0.0 ± 0.0 | 70.2 ± 14.7 |
| rush_hour | max_pressure | 1 | uniform | on | 3 | 1590 ± 38 | 118 ± 56 | 6.9 ± 3.1 | 1 ± 3 | 0.0 ± 0.0 | 28.3 ± 2.7 |
| rush_hour | rl | 1 | uniform | on | 3 | 1587 ± 24 | 121 ± 53 | 7.1 ± 2.9 | 1 ± 3 | 0.0 ± 0.0 | 29.7 ± 4.0 |

## Compute cost

36 runs ok, 0 failed · experiment wall time 329.8 s with [6] worker(s) · sum of run wall times 1701.9 s · 57.1× faster than real time per run · data 88.0 MB (2.45 MB/run, 3.26 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| actuated | 10.1 | 3.35 |
| ai_recommender-6d7df3 | 218.3 | 80.44 |
| coordinated | 12.8 | 4.3 |
| fixed_time | 13.4 | 4.53 |
| max_pressure | 10.3 | 3.4 |
| rl | 18.8 | 6.52 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
