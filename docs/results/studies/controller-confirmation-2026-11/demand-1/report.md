# Experiment report: `final_d10`

Created 2026-11-06T02:16:17 · baseline **max_pressure** · code `aa0c16c` · SUMO 1.28.0

Matrix: scenarios earthquake-c2b747, emergency-c2b747, off_peak-c2b747, road_closure-c2b747, rush_hour-c2b747, sinkhole_cross-c2b747, special_event-c2b747 · controllers fixed_time, max_pressure, max_pressure-b8251d, max_pressure_plus, rl, rl-8582b6 · seeds [201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end 4500, 5400 s

Scenario parameters: `earthquake-c2b747` = `{"demand_scale": 1.0}` · `emergency-c2b747` = `{"demand_scale": 1.0}` · `off_peak-c2b747` = `{"demand_scale": 1.0}` · `road_closure-c2b747` = `{"demand_scale": 1.0}` · `rush_hour-c2b747` = `{"demand_scale": 1.0}` · `sinkhole_cross-c2b747` = `{"demand_scale": 1.0}` · `special_event-c2b747` = `{"demand_scale": 1.0}`

Controller parameters: `max_pressure-b8251d` = `{"rho": 0.25, "closure_aware": true, "closure_weight": 0.35}` · `rl-8582b6` = `{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}`

Reproduce:

```bash
python -m teamb.experiments run --backend modal --no-report --name final_d10 --workers 100 --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak --seeds 201-230 --scenario-params '{"demand_scale": 1.0}' --controllers max_pressure --controller-params '{"rho": 0.25, "closure_aware": true, "closure_weight": 0.35}'
python -m teamb.experiments run --backend modal --no-report --name final_d10 --workers 100 --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak --seeds 201-230 --scenario-params '{"demand_scale": 1.0}' --controllers rl --controller-params '{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}'
python -m teamb.experiments run --backend modal --no-report --name final_d10 --workers 100 --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak --seeds 201-230 --scenario-params '{"demand_scale": 1.0}' --controllers fixed_time,max_pressure,max_pressure_plus,rl
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `earthquake-c2b747`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 144.9 ± 7.0 | 35.8 ± 2.4% | -82.6 ± 8.8 | <0.001 | 674.0 ± 29.1 | 4.18 ± 0.16 | 2.5 ± 0.1% | 209.0 ± 8.8 | 65.1 ± 5.1 | 16.5 ± 0.8 | 367 ± 102 | 263.9 ± 17.6 |
| **max_pressure** | 1 | uniform | on | 30 | 227.5 ± 13.2 | baseline | – | – | 1027.9 ± 57.7 | 7.77 ± 0.25 | 3.3 ± 0.5% | 321.6 ± 16.0 | 111.8 ± 11.1 | 17.7 ± 1.2 | 1348 ± 134 | 352.1 ± 32.0 |
| fixed_time | 1 | uniform | on | 30 | 229.1 ± 17.1 | -0.9 ± 4.7% | 1.6 ± 11.5 | 0.773 | 991.2 ± 58.2 | 5.26 ± 0.21 | 8.6 ± 0.6% | 350.0 ± 21.3 | 95.4 ± 13.3 | 26.7 ± 1.1 | 1008 ± 141 | 317.0 ± 31.8 |
| max_pressure_plus | 1 | uniform | on | 30 | 209.8 ± 12.6 | 7.2 ± 4.2% | -17.7 ± 9.8 | 0.002 | 974.8 ± 49.1 | 6.71 ± 0.28 | 2.7 ± 0.3% | 297.4 ± 16.1 | 101.2 ± 9.0 | 17.4 ± 1.0 | 1092 ± 136 | 313.6 ± 22.6 |
| rl-8582b6 | 1 | uniform | on | 30 | 340.2 ± 21.1 | -50.9 ± 9.1% | 112.7 ± 18.3 | <0.001 | 1330.8 ± 73.0 | 9.08 ± 0.35 | 6.0 ± 1.3% | 406.6 ± 19.1 | 258.4 ± 26.1 | 25.1 ± 2.0 | 2378 ± 133 | 460.0 ± 50.2 |
| rl | 1 | uniform | on | 30 | 281.8 ± 25.4 | -24.7 ± 11.1% | 54.3 ± 23.3 | <0.001 | 1290.5 ± 89.3 | 6.78 ± 0.42 | 3.3 ± 0.5% | 354.5 ± 29.3 | 192.1 ± 22.6 | 23.4 ± 2.1 | 1932 ± 178 | 422.8 ± 48.9 |

## Scenario `emergency-c2b747`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 29.7 ± 0.4 | -0.3 ± 1.3% | 0.1 ± 0.4 | 1.000 | 166.9 ± 1.0 | 1.01 ± 0.02 | 2.6 ± 0.1% | 29.3 ± 0.6 | 30.2 ± 0.3 | 3.2 ± 0.2 | 0 ± 0 | 100.5 ± 1.3 |
| **max_pressure** | 1 | uniform | on | 30 | 29.6 ± 0.3 | baseline | – | – | 167.1 ± 0.8 | 1.02 ± 0.02 | 2.6 ± 0.1% | 29.5 ± 0.4 | 29.9 ± 0.3 | 3.2 ± 0.2 | 0 ± 0 | 99.7 ± 1.2 |
| fixed_time | 1 | uniform | on | 30 | 83.9 ± 4.2 | -183.2 ± 13.8% | 54.3 ± 4.1 | <0.001 | 323.5 ± 19.7 | 2.05 ± 0.11 | 4.2 ± 0.3% | 126.0 ± 7.5 | 33.3 ± 0.4 | 17.5 ± 0.9 | 3 ± 6 | 129.1 ± 3.3 |
| max_pressure_plus | 1 | uniform | on | 30 | 29.7 ± 0.4 | -0.3 ± 1.3% | 0.1 ± 0.4 | 1.000 | 166.9 ± 1.0 | 1.01 ± 0.02 | 2.6 ± 0.1% | 29.3 ± 0.6 | 30.2 ± 0.3 | 3.2 ± 0.2 | 0 ± 0 | 100.5 ± 1.3 |
| rl-8582b6 | 1 | uniform | on | 30 | 31.2 ± 0.4 | -5.2 ± 1.2% | 1.5 ± 0.3 | <0.001 | 166.3 ± 0.8 | 1.06 ± 0.01 | 2.6 ± 0.1% | 27.4 ± 0.4 | 35.9 ± 0.5 | 3.9 ± 0.1 | 0 ± 0 | 100.0 ± 1.2 |
| rl | 1 | uniform | on | 30 | 30.0 ± 0.4 | -1.2 ± 1.1% | 0.3 ± 0.3 | 0.125 | 167.2 ± 0.7 | 1.11 ± 0.02 | 2.6 ± 0.1% | 30.2 ± 0.4 | 29.7 ± 0.4 | 3.4 ± 0.2 | 0 ± 0 | 100.9 ± 1.6 |

## Scenario `off_peak-c2b747`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 22.4 ± 0.2 | 0.0 ± 0.0% | 0.0 ± 0.0 | 1.000 | 158.9 ± 0.9 | 0.71 ± 0.01 | 3.3 ± 0.2% | 17.9 ± 0.3 | 28.5 ± 0.5 | 1.0 ± 0.0 | 0 ± 0 | – |
| **max_pressure** | 1 | uniform | on | 30 | 22.4 ± 0.2 | baseline | – | – | 158.9 ± 0.9 | 0.71 ± 0.01 | 3.3 ± 0.2% | 17.9 ± 0.3 | 28.5 ± 0.5 | 1.0 ± 0.0 | 0 ± 0 | – |
| fixed_time | 1 | uniform | on | 30 | 52.6 ± 0.3 | -134.7 ± 2.5% | 30.2 ± 0.4 | <0.001 | 211.4 ± 0.5 | 1.30 ± 0.01 | 4.1 ± 0.2% | 72.5 ± 0.4 | 25.7 ± 0.4 | 4.1 ± 0.1 | 0 ± 0 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 22.4 ± 0.2 | 0.0 ± 0.0% | 0.0 ± 0.0 | 1.000 | 158.9 ± 0.9 | 0.71 ± 0.01 | 3.3 ± 0.2% | 17.9 ± 0.3 | 28.5 ± 0.5 | 1.0 ± 0.0 | 0 ± 0 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 18.3 ± 0.2 | 18.2 ± 0.9% | -4.1 ± 0.2 | <0.001 | 152.7 ± 0.4 | 0.80 ± 0.01 | 3.2 ± 0.2% | 18.3 ± 0.2 | 18.4 ± 0.2 | 1.0 ± 0.0 | 0 ± 0 | – |
| rl | 1 | uniform | on | 30 | 18.3 ± 0.2 | 18.4 ± 1.0% | -4.1 ± 0.2 | <0.001 | 154.7 ± 0.6 | 0.86 ± 0.01 | 3.2 ± 0.2% | 20.5 ± 0.2 | 15.4 ± 0.2 | 1.0 ± 0.0 | 0 ± 0 | – |

## Scenario `road_closure-c2b747`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 80.4 ± 2.1 | 8.7 ± 2.9% | -8.0 ± 2.7 | <0.001 | 525.8 ± 11.5 | 2.99 ± 0.09 | 2.3 ± 0.1% | 116.3 ± 3.4 | 39.9 ± 1.1 | 10.1 ± 0.4 | 47 ± 25 | – |
| **max_pressure** | 1 | uniform | on | 30 | 88.4 ± 2.7 | baseline | – | – | 532.2 ± 12.0 | 3.33 ± 0.12 | 2.3 ± 0.1% | 125.0 ± 3.9 | 47.0 ± 1.4 | 10.2 ± 0.3 | 82 ± 39 | – |
| fixed_time | 1 | uniform | on | 30 | 119.3 ± 1.2 | -35.7 ± 3.8% | 30.9 ± 2.5 | <0.001 | 594.5 ± 11.5 | 3.12 ± 0.03 | 6.9 ± 0.3% | 196.3 ± 1.8 | 39.9 ± 1.2 | 23.2 ± 0.4 | 29 ± 17 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 85.8 ± 2.4 | 2.7 ± 2.4% | -2.6 ± 2.2 | 0.045 | 527.3 ± 13.7 | 3.06 ± 0.09 | 2.3 ± 0.1% | 120.3 ± 3.7 | 46.9 ± 1.2 | 9.8 ± 0.4 | 71 ± 36 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 169.1 ± 10.0 | -91.8 ± 11.0% | 80.7 ± 9.7 | <0.001 | 859.7 ± 38.1 | 5.30 ± 0.26 | 2.5 ± 0.2% | 203.7 ± 11.1 | 130.0 ± 9.9 | 17.6 ± 0.7 | 1753 ± 192 | – |
| rl | 1 | uniform | on | 30 | 87.2 ± 1.9 | 0.8 ± 3.0% | -1.2 ± 2.7 | 0.388 | 587.8 ± 14.7 | 3.11 ± 0.05 | 2.3 ± 0.1% | 113.2 ± 2.4 | 58.0 ± 2.0 | 10.8 ± 0.4 | 347 ± 91 | – |

## Scenario `rush_hour-c2b747`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 29.1 ± 0.4 | 0.8 ± 1.2% | -0.3 ± 0.4 | 0.466 | 165.7 ± 0.7 | 0.98 ± 0.02 | 2.6 ± 0.1% | 28.4 ± 0.5 | 29.9 ± 0.3 | 3.1 ± 0.1 | 0 ± 0 | – |
| **max_pressure** | 1 | uniform | on | 30 | 29.3 ± 0.3 | baseline | – | – | 166.3 ± 0.8 | 1.01 ± 0.02 | 2.6 ± 0.1% | 29.0 ± 0.5 | 29.7 ± 0.4 | 3.1 ± 0.1 | 0 ± 0 | – |
| fixed_time | 1 | uniform | on | 30 | 81.8 ± 4.3 | -179.2 ± 15.2% | 52.5 ± 4.3 | <0.001 | 310.5 ± 20.4 | 1.87 ± 0.11 | 4.3 ± 0.4% | 123.4 ± 8.0 | 31.8 ± 0.3 | 18.2 ± 1.1 | 0 ± 0 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 29.1 ± 0.4 | 0.8 ± 1.2% | -0.3 ± 0.4 | 0.466 | 165.7 ± 0.7 | 0.98 ± 0.02 | 2.6 ± 0.1% | 28.4 ± 0.5 | 29.9 ± 0.3 | 3.1 ± 0.1 | 0 ± 0 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 30.6 ± 0.4 | -4.5 ± 1.4% | 1.3 ± 0.4 | <0.001 | 165.5 ± 0.9 | 1.04 ± 0.01 | 2.6 ± 0.1% | 26.6 ± 0.3 | 35.6 ± 0.5 | 3.8 ± 0.1 | 0 ± 0 | – |
| rl | 1 | uniform | on | 30 | 29.3 ± 0.4 | -0.1 ± 1.4% | 0.0 ± 0.4 | 0.992 | 165.8 ± 0.6 | 1.08 ± 0.02 | 2.6 ± 0.1% | 29.5 ± 0.4 | 29.1 ± 0.4 | 3.2 ± 0.2 | 0 ± 0 | – |

## Scenario `sinkhole_cross-c2b747`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 45.9 ± 4.3 | 2.0 ± 7.2% | -2.1 ± 4.3 | 0.333 | 234.0 ± 18.9 | 1.68 ± 0.18 | 2.6 ± 0.1% | 43.5 ± 5.2 | 48.9 ± 3.3 | 6.2 ± 0.8 | 7 ± 13 | – |
| **max_pressure** | 1 | uniform | on | 30 | 48.0 ± 5.1 | baseline | – | – | 237.6 ± 21.8 | 1.82 ± 0.21 | 2.6 ± 0.1% | 47.9 ± 6.5 | 48.1 ± 3.4 | 6.3 ± 0.9 | 21 ± 25 | – |
| fixed_time | 1 | uniform | on | 30 | 132.1 ± 1.8 | -188.7 ± 18.9% | 84.1 ± 4.7 | <0.001 | 580.4 ± 10.6 | 3.23 ± 0.05 | 11.8 ± 0.4% | 212.6 ± 2.6 | 49.1 ± 1.6 | 26.1 ± 0.3 | 6 ± 6 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 43.5 ± 3.1 | 6.2 ± 6.4% | -4.5 ± 4.6 | 0.160 | 221.7 ± 14.4 | 1.60 ± 0.13 | 2.6 ± 0.1% | 41.8 ± 3.7 | 45.6 ± 2.4 | 5.6 ± 0.6 | 1 ± 2 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 44.6 ± 1.7 | 2.8 ± 6.7% | -3.3 ± 4.8 | 0.333 | 226.3 ± 6.4 | 1.55 ± 0.06 | 2.6 ± 0.1% | 35.4 ± 1.2 | 56.2 ± 2.5 | 6.0 ± 0.4 | 4 ± 3 | – |
| rl | 1 | uniform | on | 30 | 40.6 ± 1.2 | 11.5 ± 5.8% | -7.3 ± 4.7 | 0.014 | 209.9 ± 5.8 | 1.48 ± 0.04 | 2.6 ± 0.1% | 35.4 ± 0.8 | 47.1 ± 1.9 | 5.1 ± 0.3 | 0 ± 1 | – |

## Scenario `special_event-c2b747`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 49.4 ± 1.5 | 6.4 ± 2.2% | -3.4 ± 1.2 | <0.001 | 232.2 ± 5.6 | 1.89 ± 0.06 | 2.9 ± 0.1% | 44.7 ± 1.4 | 54.6 ± 1.7 | 7.4 ± 0.3 | 4 ± 3 | – |
| **max_pressure** | 1 | uniform | on | 30 | 52.8 ± 1.4 | baseline | – | – | 248.4 ± 5.7 | 2.14 ± 0.07 | 3.0 ± 0.1% | 47.5 ± 1.5 | 58.7 ± 1.6 | 8.0 ± 0.3 | 2 ± 1 | – |
| fixed_time | 1 | uniform | on | 30 | 75.5 ± 0.8 | -43.5 ± 3.3% | 22.7 ± 1.2 | <0.001 | 258.5 ± 3.8 | 1.76 ± 0.02 | 3.9 ± 0.1% | 91.9 ± 1.0 | 57.9 ± 0.8 | 13.9 ± 0.2 | 20 ± 7 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 49.4 ± 1.5 | 6.4 ± 2.2% | -3.4 ± 1.2 | <0.001 | 232.2 ± 5.6 | 1.89 ± 0.06 | 2.9 ± 0.1% | 44.7 ± 1.4 | 54.6 ± 1.7 | 7.4 ± 0.3 | 4 ± 3 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 53.1 ± 0.8 | -0.9 ± 2.4% | 0.3 ± 1.3 | 0.636 | 278.2 ± 6.7 | 1.89 ± 0.03 | 3.5 ± 0.3% | 35.0 ± 0.5 | 73.1 ± 1.3 | 8.5 ± 0.3 | 10 ± 6 | – |
| rl | 1 | uniform | on | 30 | 50.6 ± 1.0 | 3.9 ± 2.4% | -2.3 ± 1.4 | 0.004 | 273.2 ± 6.4 | 1.76 ± 0.03 | 3.3 ± 0.2% | 34.2 ± 0.5 | 68.5 ± 1.7 | 7.6 ± 0.4 | 4 ± 3 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 1260 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.04 ± 0.00 | 0.53 ± 0.03 | 0.30 ± 0.01 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| earthquake | fixed_time | 1 | on | 30 | 7.0 ± 0.0 | 317.0 ± 31.8 | 204.0 ± 31.8 | 229.2 ± 17.0 | 173.7 ± 21.3 | – | – |
| earthquake | max_pressure-b8251d | 1 | on | 30 | 7.0 ± 0.0 | 263.9 ± 17.6 | 151.0 ± 17.5 | 144.9 ± 7.0 | 161.2 ± 8.1 | – | – |
| earthquake | max_pressure | 1 | on | 30 | 7.0 ± 0.0 | 352.1 ± 32.0 | 239.2 ± 32.0 | 227.5 ± 13.1 | 218.5 ± 16.1 | – | – |
| earthquake | max_pressure_plus | 1 | on | 30 | 7.0 ± 0.0 | 313.6 ± 22.6 | 200.8 ± 22.5 | 209.9 ± 12.6 | 213.8 ± 14.6 | – | – |
| earthquake | rl-8582b6 | 1 | on | 30 | 7.0 ± 0.0 | 460.0 ± 50.2 | 347.1 ± 50.3 | 340.2 ± 21.1 | 298.7 ± 28.7 | – | – |
| earthquake | rl | 1 | on | 30 | 7.0 ± 0.0 | 422.8 ± 48.9 | 309.3 ± 48.6 | 281.7 ± 25.4 | 298.2 ± 22.7 | – | – |
| emergency | fixed_time | 1 | on | 30 | 10.0 ± 0.0 | 129.1 ± 3.3 | 51.4 ± 3.3 | 84.0 ± 4.2 | 29.9 ± 6.4 | – | – |
| emergency | max_pressure-b8251d | 1 | on | 30 | 10.0 ± 0.0 | 100.5 ± 1.3 | 22.8 ± 1.3 | 29.7 ± 0.4 | 6.4 ± 0.6 | – | – |
| emergency | max_pressure | 1 | on | 30 | 10.0 ± 0.0 | 99.7 ± 1.2 | 22.0 ± 1.2 | 29.7 ± 0.3 | 6.2 ± 0.5 | – | – |
| emergency | max_pressure_plus | 1 | on | 30 | 10.0 ± 0.0 | 100.5 ± 1.3 | 22.8 ± 1.3 | 29.7 ± 0.4 | 6.4 ± 0.6 | – | – |
| emergency | rl-8582b6 | 1 | on | 30 | 10.0 ± 0.0 | 100.0 ± 1.2 | 22.2 ± 1.2 | 31.2 ± 0.4 | 6.7 ± 0.5 | – | – |
| emergency | rl | 1 | on | 30 | 10.0 ± 0.0 | 100.9 ± 1.6 | 23.2 ± 1.6 | 30.0 ± 0.4 | 6.0 ± 0.5 | – | – |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| earthquake | fixed_time | 1 | 30 | – | 30 | 115.65 ± 11.43 | – | – | – | 1008 ± 141 |
| earthquake | max_pressure-b8251d | 1 | 30 | 359 ± 48 | 0 | 84.74 ± 5.09 | – | – | – | 367 ± 102 |
| earthquake | max_pressure | 1 | 30 | 653 ± 54 | 15 | 141.09 ± 9.22 | – | – | – | 1348 ± 134 |
| earthquake | max_pressure_plus | 1 | 30 | 585 ± 46 | 4 | 129.25 ± 9.02 | – | – | – | 1092 ± 136 |
| earthquake | rl-8582b6 | 1 | 30 | 756 ± 64 | 28 | 228.43 ± 18.26 | – | – | – | 2378 ± 133 |
| earthquake | rl | 1 | 30 | 599 ± 75 | 17 | 182.61 ± 19.25 | – | – | – | 1932 ± 178 |
| road_closure | fixed_time | 1 | 30 | – | 30 | 52.93 ± 2.47 | – | – | – | 29 ± 17 |
| road_closure | max_pressure-b8251d | 1 | 30 | 1070 ± 58 | 0 | 56.12 ± 2.15 | – | – | – | 47 ± 25 |
| road_closure | max_pressure | 1 | 30 | 1174 ± 76 | 0 | 63.90 ± 2.95 | – | – | – | 82 ± 39 |
| road_closure | max_pressure_plus | 1 | 30 | 1031 ± 59 | 0 | 61.69 ± 2.71 | – | – | – | 71 ± 36 |
| road_closure | rl-8582b6 | 1 | 30 | 1594 ± 84 | 7 | 147.85 ± 11.48 | – | – | – | 1753 ± 192 |
| road_closure | rl | 1 | 30 | 1069 ± 57 | 0 | 62.90 ± 2.37 | – | – | – | 347 ± 91 |
| sinkhole_cross | fixed_time | 1 | 30 | – | 30 | 58.66 ± 2.18 | – | – | – | 6 ± 6 |
| sinkhole_cross | max_pressure-b8251d | 1 | 30 | 483 ± 73 | 0 | 18.71 ± 3.86 | – | – | – | 7 ± 13 |
| sinkhole_cross | max_pressure | 1 | 30 | 522 ± 82 | 2 | 20.64 ± 4.74 | – | – | – | 21 ± 25 |
| sinkhole_cross | max_pressure_plus | 1 | 30 | 484 ± 87 | 0 | 16.49 ± 2.98 | – | – | – | 1 ± 2 |
| sinkhole_cross | rl-8582b6 | 1 | 30 | 546 ± 78 | 0 | 16.47 ± 1.70 | – | – | – | 4 ± 3 |
| sinkhole_cross | rl | 1 | 30 | 467 ± 65 | 0 | 13.88 ± 1.21 | – | – | – | 0 ± 1 |

## PERF-01: completed and unfinished trips

Depart delay = time waiting to enter a blocked entry lane (not in the delay column, which is timeLoss). Accrued delay incl. unfinished is a lower bound: trips still driving have only part of their delay.

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | depart delay s | delay + depart delay s | accrued delay incl. unfinished s (lower bound) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| earthquake | fixed_time | 1 | uniform | on | 30 | 2321 ± 15 | 219 ± 15 | 8.6 ± 0.6 | 47 ± 13 | 1.7 ± 1.5 | 105.4 ± 10.6 | 322.8 ± 21.7 | 222.4 ± 15.9 |
| earthquake | max_pressure-b8251d | 1 | uniform | on | 30 | 2476 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.8 ± 0.7 | 44.8 ± 8.2 | 190.9 ± 14.3 | 141.6 ± 6.8 |
| earthquake | max_pressure | 1 | uniform | on | 30 | 2456 ± 19 | 84 ± 12 | 3.3 ± 0.5 | 0 ± 0 | 1.3 ± 1.1 | 63.3 ± 12.8 | 292.3 ± 24.9 | 221.6 ± 12.5 |
| earthquake | max_pressure_plus | 1 | uniform | on | 30 | 2471 ± 18 | 69 ± 7 | 2.7 ± 0.3 | 0 ± 0 | 0.8 ± 0.8 | 50.9 ± 11.4 | 262.1 ± 22.9 | 204.7 ± 12.2 |
| earthquake | rl-8582b6 | 1 | uniform | on | 30 | 2388 ± 28 | 152 ± 33 | 6.0 ± 1.2 | 0 ± 0 | 6.1 ± 2.0 | 52.2 ± 10.7 | 395.2 ± 30.5 | 343.0 ± 23.8 |
| earthquake | rl | 1 | uniform | on | 30 | 2456 ± 17 | 85 ± 14 | 3.3 ± 0.5 | 0 ± 0 | 3.5 ± 1.2 | 40.2 ± 8.9 | 323.4 ± 33.7 | 279.0 ± 26.3 |
| emergency | fixed_time | 1 | uniform | on | 30 | 3247 ± 23 | 142 ± 9 | 4.2 ± 0.2 | 1 ± 1 | 0.0 ± 0.0 | 4.4 ± 2.2 | 88.2 ± 5.9 | 83.7 ± 4.3 |
| emergency | max_pressure-b8251d | 1 | uniform | on | 30 | 3299 ± 22 | 89 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 30.2 ± 0.4 | 29.4 ± 0.4 |
| emergency | max_pressure | 1 | uniform | on | 30 | 3301 ± 22 | 87 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 30.2 ± 0.3 | 29.2 ± 0.3 |
| emergency | max_pressure_plus | 1 | uniform | on | 30 | 3299 ± 22 | 89 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 30.2 ± 0.4 | 29.4 ± 0.4 |
| emergency | rl-8582b6 | 1 | uniform | on | 30 | 3300 ± 22 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 31.7 ± 0.4 | 30.7 ± 0.4 |
| emergency | rl | 1 | uniform | on | 30 | 3302 ± 22 | 87 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 30.5 ± 0.4 | 29.6 ± 0.4 |
| off_peak | fixed_time | 1 | uniform | on | 30 | 1081 ± 12 | 46 ± 3 | 4.1 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 53.1 ± 0.3 | 51.8 ± 0.3 |
| off_peak | max_pressure-b8251d | 1 | uniform | on | 30 | 1090 ± 12 | 38 ± 3 | 3.3 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 22.9 ± 0.2 | 22.1 ± 0.2 |
| off_peak | max_pressure | 1 | uniform | on | 30 | 1090 ± 12 | 38 ± 3 | 3.3 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 22.9 ± 0.2 | 22.1 ± 0.2 |
| off_peak | max_pressure_plus | 1 | uniform | on | 30 | 1090 ± 12 | 38 ± 3 | 3.3 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 22.9 ± 0.2 | 22.1 ± 0.2 |
| off_peak | rl-8582b6 | 1 | uniform | on | 30 | 1091 ± 12 | 36 ± 3 | 3.2 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 18.8 ± 0.2 | 18.1 ± 0.2 |
| off_peak | rl | 1 | uniform | on | 30 | 1091 ± 11 | 36 ± 2 | 3.2 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 18.8 ± 0.2 | 18.0 ± 0.2 |
| road_closure | fixed_time | 1 | uniform | on | 30 | 3594 ± 19 | 268 ± 14 | 6.9 ± 0.3 | 81 ± 13 | 0.0 ± 0.0 | 146.8 ± 4.7 | 261.4 ± 4.7 | 119.0 ± 1.1 |
| road_closure | max_pressure-b8251d | 1 | uniform | on | 30 | 3774 ± 25 | 88 ± 4 | 2.3 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 41.6 ± 3.7 | 123.0 ± 4.7 | 78.9 ± 2.1 |
| road_closure | max_pressure | 1 | uniform | on | 30 | 3774 ± 25 | 88 ± 4 | 2.3 ± 0.1 | 0 ± 0 | 0.1 ± 0.1 | 29.2 ± 3.4 | 118.3 ± 4.7 | 86.7 ± 2.6 |
| road_closure | max_pressure_plus | 1 | uniform | on | 30 | 3774 ± 26 | 89 ± 4 | 2.3 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 26.9 ± 3.1 | 113.4 ± 4.6 | 84.2 ± 2.3 |
| road_closure | rl-8582b6 | 1 | uniform | on | 30 | 3768 ± 24 | 95 ± 9 | 2.5 ± 0.2 | 0 ± 0 | 1.1 ± 0.5 | 29.2 ± 3.1 | 199.0 ± 11.8 | 166.1 ± 10.2 |
| road_closure | rl | 1 | uniform | on | 30 | 3775 ± 26 | 88 ± 4 | 2.3 ± 0.1 | 0 ± 0 | 0.1 ± 0.1 | 33.6 ± 2.9 | 121.7 ± 3.8 | 85.6 ± 1.8 |
| rush_hour | fixed_time | 1 | uniform | on | 30 | 3234 ± 20 | 145 ± 13 | 4.3 ± 0.4 | 3 ± 3 | 0.0 ± 0.0 | 4.4 ± 2.6 | 85.7 ± 6.3 | 81.6 ± 4.6 |
| rush_hour | max_pressure-b8251d | 1 | uniform | on | 30 | 3290 ± 22 | 88 ± 5 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 29.6 ± 0.4 | 28.7 ± 0.4 |
| rush_hour | max_pressure | 1 | uniform | on | 30 | 3290 ± 22 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 29.9 ± 0.3 | 29.0 ± 0.3 |
| rush_hour | max_pressure_plus | 1 | uniform | on | 30 | 3290 ± 22 | 88 ± 5 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 29.6 ± 0.4 | 28.7 ± 0.4 |
| rush_hour | rl-8582b6 | 1 | uniform | on | 30 | 3290 ± 22 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 31.1 ± 0.4 | 30.2 ± 0.4 |
| rush_hour | rl | 1 | uniform | on | 30 | 3290 ± 22 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 29.9 ± 0.4 | 28.9 ± 0.4 |
| sinkhole_cross | fixed_time | 1 | uniform | on | 30 | 2978 ± 21 | 400 ± 16 | 11.8 ± 0.4 | 206 ± 16 | 0.0 ± 0.0 | 124.4 ± 7.3 | 232.1 ± 6.8 | 132.2 ± 1.6 |
| sinkhole_cross | max_pressure-b8251d | 1 | uniform | on | 30 | 3290 ± 22 | 89 ± 5 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.7 ± 0.3 | 46.6 ± 4.5 | 45.1 ± 4.2 |
| sinkhole_cross | max_pressure | 1 | uniform | on | 30 | 3289 ± 22 | 89 ± 5 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.8 ± 0.3 | 48.8 ± 5.4 | 47.2 ± 5.0 |
| sinkhole_cross | max_pressure_plus | 1 | uniform | on | 30 | 3290 ± 22 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.6 ± 0.2 | 44.1 ± 3.2 | 42.7 ± 3.0 |
| sinkhole_cross | rl-8582b6 | 1 | uniform | on | 30 | 3291 ± 22 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 45.2 ± 1.7 | 43.9 ± 1.7 |
| sinkhole_cross | rl | 1 | uniform | on | 30 | 3291 ± 23 | 88 ± 4 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 41.1 ± 1.2 | 40.0 ± 1.2 |
| special_event | fixed_time | 1 | uniform | on | 30 | 3223 ± 21 | 131 ± 4 | 3.9 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 11.2 ± 2.3 | 87.1 ± 2.7 | 74.2 ± 0.7 |
| special_event | max_pressure-b8251d | 1 | uniform | on | 30 | 3256 ± 21 | 98 ± 4 | 2.9 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 9.7 ± 2.8 | 59.4 ± 4.0 | 48.4 ± 1.4 |
| special_event | max_pressure | 1 | uniform | on | 30 | 3254 ± 21 | 100 ± 5 | 3.0 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 14.7 ± 3.3 | 67.9 ± 4.6 | 51.7 ± 1.4 |
| special_event | max_pressure_plus | 1 | uniform | on | 30 | 3256 ± 21 | 98 ± 4 | 2.9 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 9.7 ± 2.8 | 59.4 ± 4.0 | 48.4 ± 1.4 |
| special_event | rl-8582b6 | 1 | uniform | on | 30 | 3238 ± 20 | 116 ± 9 | 3.5 ± 0.2 | 2 ± 2 | 0.0 ± 0.0 | 32.1 ± 3.7 | 84.5 ± 3.4 | 52.3 ± 0.8 |
| special_event | rl | 1 | uniform | on | 30 | 3242 ± 19 | 112 ± 8 | 3.3 ± 0.2 | 1 ± 2 | 0.0 ± 0.0 | 29.8 ± 3.5 | 79.8 ± 3.6 | 49.8 ± 1.1 |

## Compute cost

1260 runs ok, 0 failed, 0 incomplete · experiment wall time 1226.4 s with [100] worker(s) · sum of run wall times 12561.6 s · 464.3× faster than real time per run · data 4402.7 MB (3.49 MB/run, 2.72 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 11.0 | 2.33 |
| max_pressure | 9.6 | 2.03 |
| max_pressure-b8251d | 9.4 | 1.99 |
| max_pressure_plus | 9.6 | 2.04 |
| rl | 9.8 | 2.08 |
| rl-8582b6 | 10.6 | 2.22 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
