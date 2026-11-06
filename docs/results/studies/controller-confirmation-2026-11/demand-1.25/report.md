# Experiment report: `final_d125`

Created 2026-11-06T02:16:23 · baseline **max_pressure** · code `aa0c16c` · SUMO 1.28.0

Matrix: scenarios earthquake-5601c3, emergency-5601c3, off_peak-5601c3, road_closure-5601c3, rush_hour-5601c3, sinkhole_cross-5601c3, special_event-5601c3 · controllers fixed_time, max_pressure, max_pressure-b8251d, max_pressure_plus, rl, rl-8582b6 · seeds [201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end 4500, 5400 s

Scenario parameters: `earthquake-5601c3` = `{"demand_scale": 1.25}` · `emergency-5601c3` = `{"demand_scale": 1.25}` · `off_peak-5601c3` = `{"demand_scale": 1.25}` · `road_closure-5601c3` = `{"demand_scale": 1.25}` · `rush_hour-5601c3` = `{"demand_scale": 1.25}` · `sinkhole_cross-5601c3` = `{"demand_scale": 1.25}` · `special_event-5601c3` = `{"demand_scale": 1.25}`

Controller parameters: `max_pressure-b8251d` = `{"rho": 0.25, "closure_aware": true, "closure_weight": 0.35}` · `rl-8582b6` = `{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}`

Reproduce:

```bash
python -m teamb.experiments run --backend modal --no-report --name final_d125 --workers 100 --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak --seeds 201-230 --scenario-params '{"demand_scale": 1.25}' --controllers max_pressure --controller-params '{"rho": 0.25, "closure_aware": true, "closure_weight": 0.35}'
python -m teamb.experiments run --backend modal --no-report --name final_d125 --workers 100 --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak --seeds 201-230 --scenario-params '{"demand_scale": 1.25}' --controllers rl --controller-params '{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}'
python -m teamb.experiments run --backend modal --no-report --name final_d125 --workers 100 --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak --seeds 201-230 --scenario-params '{"demand_scale": 1.25}' --controllers fixed_time,max_pressure,max_pressure_plus,rl
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `earthquake-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 176.0 ± 6.0 | 28.3 ± 3.0% | -71.2 ± 9.2 | <0.001 | 729.0 ± 21.4 | 5.35 ± 0.15 | 6.1 ± 0.8% | 253.0 ± 8.7 | 85.9 ± 4.5 | 22.8 ± 0.5 | 720 ± 117 | 303.3 ± 22.7 |
| **max_pressure** | 1 | uniform | on | 30 | 247.2 ± 8.5 | baseline | – | – | 1111.3 ± 43.3 | 8.45 ± 0.22 | 11.6 ± 0.7% | 357.7 ± 13.0 | 131.9 ± 5.9 | 20.9 ± 0.6 | 1643 ± 90 | 417.9 ± 28.8 |
| fixed_time | 1 | uniform | on | 30 | 257.4 ± 10.1 | -5.1 ± 5.8% | 10.2 ± 13.9 | 0.143 | 1093.3 ± 44.2 | 5.96 ± 0.15 | 15.2 ± 0.6% | 409.9 ± 13.9 | 112.0 ± 7.3 | 30.9 ± 0.7 | 1412 ± 100 | 396.9 ± 36.3 |
| max_pressure_plus | 1 | uniform | on | 30 | 237.4 ± 11.2 | 3.7 ± 4.2% | -9.8 ± 10.3 | 0.121 | 1069.7 ± 55.5 | 7.42 ± 0.29 | 9.8 ± 0.8% | 337.8 ± 16.2 | 128.4 ± 7.8 | 21.6 ± 0.8 | 1484 ± 138 | 391.5 ± 32.4 |
| rl-8582b6 | 1 | uniform | on | 30 | 386.6 ± 21.0 | -56.8 ± 7.5% | 139.4 ± 18.5 | <0.001 | 1422.9 ± 77.9 | 9.58 ± 0.27 | 19.0 ± 1.8% | 429.6 ± 18.4 | 338.8 ± 26.6 | 31.3 ± 1.4 | 2864 ± 54 | 544.2 ± 44.7 |
| rl | 1 | uniform | on | 30 | 411.8 ± 21.3 | -68.5 ± 11.8% | 164.6 ± 24.3 | <0.001 | 1605.3 ± 79.1 | 8.42 ± 0.25 | 20.9 ± 1.7% | 478.3 ± 31.2 | 345.7 ± 17.8 | 36.4 ± 1.2 | 2867 ± 49 | 585.2 ± 59.6 |

## Scenario `emergency-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 41.3 ± 1.4 | 7.2 ± 5.0% | -4.2 ± 3.0 | 0.024 | 192.6 ± 5.3 | 1.41 ± 0.06 | 2.8 ± 0.2% | 43.3 ± 1.8 | 38.7 ± 1.0 | 5.9 ± 0.3 | 1 ± 3 | 108.4 ± 1.5 |
| **max_pressure** | 1 | uniform | on | 30 | 45.5 ± 3.2 | baseline | – | – | 209.9 ± 13.1 | 1.61 ± 0.14 | 2.9 ± 0.2% | 50.2 ± 4.7 | 39.7 ± 1.6 | 6.7 ± 0.6 | 4 ± 7 | 111.5 ± 2.7 |
| fixed_time | 1 | uniform | on | 30 | 107.6 ± 1.7 | -143.1 ± 13.9% | 62.1 ± 3.4 | <0.001 | 412.4 ± 6.7 | 2.68 ± 0.05 | 11.9 ± 0.6% | 176.2 ± 3.4 | 36.9 ± 0.7 | 26.5 ± 0.5 | 2 ± 2 | 135.3 ± 3.5 |
| max_pressure_plus | 1 | uniform | on | 30 | 41.2 ± 1.3 | 7.2 ± 5.0% | -4.2 ± 3.0 | 0.024 | 192.5 ± 5.1 | 1.41 ± 0.06 | 2.8 ± 0.2% | 43.3 ± 1.7 | 38.7 ± 1.0 | 5.9 ± 0.3 | 1 ± 3 | 108.4 ± 1.5 |
| rl-8582b6 | 1 | uniform | on | 30 | 54.4 ± 3.8 | -21.1 ± 7.5% | 9.0 ± 3.4 | <0.001 | 227.2 ± 14.1 | 1.84 ± 0.14 | 3.1 ± 0.3% | 48.0 ± 3.3 | 62.4 ± 5.0 | 8.7 ± 0.8 | 30 ± 29 | 112.0 ± 2.1 |
| rl | 1 | uniform | on | 30 | 43.9 ± 2.3 | 1.6 ± 5.5% | -1.6 ± 3.1 | 0.313 | 194.4 ± 7.7 | 1.48 ± 0.07 | 2.9 ± 0.1% | 40.2 ± 1.0 | 48.5 ± 4.1 | 6.8 ± 0.6 | 2 ± 4 | 109.8 ± 2.1 |

## Scenario `off_peak-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 22.4 ± 0.2 | -0.2 ± 0.4% | 0.1 ± 0.1 | 0.518 | 157.8 ± 0.8 | 0.73 ± 0.01 | 3.1 ± 0.2% | 18.1 ± 0.2 | 28.3 ± 0.4 | 1.7 ± 0.2 | 0 ± 0 | – |
| **max_pressure** | 1 | uniform | on | 30 | 22.3 ± 0.2 | baseline | – | – | 157.5 ± 0.7 | 0.73 ± 0.01 | 3.1 ± 0.2% | 18.0 ± 0.2 | 28.2 ± 0.4 | 1.7 ± 0.2 | 0 ± 0 | – |
| fixed_time | 1 | uniform | on | 30 | 53.4 ± 0.2 | -139.3 ± 2.2% | 31.1 ± 0.3 | <0.001 | 212.0 ± 0.4 | 1.31 ± 0.01 | 3.9 ± 0.2% | 73.9 ± 0.4 | 26.0 ± 0.4 | 5.2 ± 0.1 | 0 ± 0 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 22.4 ± 0.2 | -0.2 ± 0.4% | 0.1 ± 0.1 | 0.518 | 157.8 ± 0.8 | 0.73 ± 0.01 | 3.1 ± 0.2% | 18.1 ± 0.2 | 28.3 ± 0.4 | 1.7 ± 0.2 | 0 ± 0 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 19.8 ± 0.2 | 11.4 ± 1.1% | -2.6 ± 0.3 | <0.001 | 153.6 ± 0.6 | 0.85 ± 0.01 | 3.0 ± 0.2% | 19.0 ± 0.2 | 20.8 ± 0.3 | 1.0 ± 0.0 | 0 ± 0 | – |
| rl | 1 | uniform | on | 30 | 19.9 ± 0.2 | 10.7 ± 1.2% | -2.4 ± 0.3 | <0.001 | 156.5 ± 0.6 | 0.93 ± 0.01 | 3.0 ± 0.2% | 21.9 ± 0.3 | 17.2 ± 0.3 | 1.0 ± 0.0 | 0 ± 0 | – |

## Scenario `road_closure-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 104.7 ± 3.1 | 8.8 ± 3.6% | -10.9 ± 4.3 | <0.001 | 522.9 ± 23.3 | 4.08 ± 0.14 | 5.6 ± 0.7% | 154.4 ± 5.5 | 51.5 ± 1.6 | 15.4 ± 0.4 | 146 ± 59 | – |
| **max_pressure** | 1 | uniform | on | 30 | 115.7 ± 4.3 | baseline | – | – | 577.8 ± 26.2 | 4.60 ± 0.18 | 6.5 ± 0.8% | 168.2 ± 6.8 | 60.4 ± 2.7 | 15.2 ± 0.4 | 281 ± 100 | – |
| fixed_time | 1 | uniform | on | 30 | 126.7 ± 2.5 | -10.6 ± 4.6% | 11.0 ± 4.7 | <0.001 | 598.3 ± 18.5 | 3.36 ± 0.07 | 13.8 ± 0.4% | 214.3 ± 3.9 | 49.1 ± 2.2 | 26.6 ± 0.3 | 139 ± 55 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 115.1 ± 3.9 | -0.0 ± 3.4% | -0.6 ± 3.9 | 0.761 | 576.8 ± 19.6 | 4.33 ± 0.15 | 5.4 ± 0.8% | 163.6 ± 6.3 | 62.8 ± 2.3 | 15.4 ± 0.4 | 286 ± 93 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 206.0 ± 5.9 | -79.2 ± 6.3% | 90.3 ± 5.2 | <0.001 | 859.4 ± 28.6 | 6.72 ± 0.16 | 10.9 ± 0.7% | 227.8 ± 6.4 | 181.9 ± 8.2 | 23.0 ± 0.6 | 2701 ± 125 | – |
| rl | 1 | uniform | on | 30 | 136.1 ± 4.5 | -18.3 ± 4.1% | 20.4 ± 4.4 | <0.001 | 751.5 ± 19.3 | 4.20 ± 0.10 | 4.2 ± 0.3% | 141.4 ± 4.9 | 130.1 ± 5.7 | 20.8 ± 0.5 | 1634 ± 158 | – |

## Scenario `rush_hour-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 41.2 ± 3.1 | -0.4 ± 8.4% | -0.4 ± 3.6 | 1.000 | 195.2 ± 11.4 | 1.41 ± 0.13 | 2.8 ± 0.1% | 43.7 ± 4.5 | 38.2 ± 1.5 | 5.7 ± 0.6 | 4 ± 8 | – |
| **max_pressure** | 1 | uniform | on | 30 | 41.6 ± 2.4 | baseline | – | – | 195.4 ± 9.1 | 1.45 ± 0.11 | 2.8 ± 0.1% | 44.9 ± 3.3 | 37.6 ± 1.4 | 5.8 ± 0.5 | 0 ± 0 | – |
| fixed_time | 1 | uniform | on | 30 | 106.9 ± 1.4 | -161.8 ± 12.3% | 65.3 ± 2.9 | <0.001 | 397.2 ± 6.8 | 2.57 ± 0.04 | 12.3 ± 0.5% | 178.3 ± 3.0 | 34.1 ± 0.4 | 26.8 ± 0.4 | 0 ± 0 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 41.2 ± 3.1 | -0.4 ± 8.4% | -0.4 ± 3.6 | 1.000 | 195.2 ± 11.4 | 1.41 ± 0.13 | 2.8 ± 0.1% | 43.7 ± 4.5 | 38.2 ± 1.5 | 5.7 ± 0.6 | 4 ± 8 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 51.4 ± 3.8 | -24.1 ± 7.5% | 9.8 ± 3.3 | <0.001 | 216.5 ± 12.6 | 1.74 ± 0.15 | 3.1 ± 0.3% | 45.5 ± 3.9 | 58.7 ± 4.5 | 8.1 ± 0.8 | 27 ± 21 | – |
| rl | 1 | uniform | on | 30 | 42.6 ± 2.4 | -3.3 ± 5.3% | 1.0 ± 2.3 | 1.000 | 192.7 ± 9.8 | 1.44 ± 0.07 | 2.8 ± 0.1% | 39.3 ± 1.1 | 46.7 ± 4.3 | 6.6 ± 0.6 | 12 ± 25 | – |

## Scenario `sinkhole_cross-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 119.8 ± 4.6 | -0.8 ± 4.1% | 0.1 ± 4.8 | 1.000 | 517.3 ± 22.0 | 4.65 ± 0.20 | 8.8 ± 0.9% | 143.2 ± 5.7 | 93.7 ± 4.6 | 18.3 ± 0.6 | 333 ± 102 | – |
| **max_pressure** | 1 | uniform | on | 30 | 119.7 ± 5.3 | baseline | – | – | 514.1 ± 21.4 | 4.89 ± 0.23 | 9.2 ± 0.9% | 148.8 ± 7.1 | 87.7 ± 4.3 | 17.7 ± 0.6 | 297 ± 73 | – |
| fixed_time | 1 | uniform | on | 30 | 152.0 ± 4.1 | -28.4 ± 6.0% | 32.3 ± 5.1 | <0.001 | 640.6 ± 20.4 | 3.77 ± 0.11 | 18.4 ± 0.6% | 247.9 ± 6.1 | 67.6 ± 3.5 | 32.0 ± 1.1 | 108 ± 44 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 118.1 ± 4.2 | -0.1 ± 6.0% | -1.6 ± 6.7 | 1.000 | 505.1 ± 18.9 | 4.60 ± 0.18 | 8.5 ± 0.6% | 143.3 ± 5.7 | 89.9 ± 3.7 | 18.1 ± 0.5 | 296 ± 89 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 126.6 ± 8.1 | -6.8 ± 7.2% | 6.9 ± 8.7 | 0.455 | 521.1 ± 32.1 | 4.20 ± 0.26 | 5.7 ± 0.7% | 91.3 ± 7.8 | 172.0 ± 11.3 | 19.1 ± 1.0 | 1288 ± 140 | – |
| rl | 1 | uniform | on | 30 | 122.5 ± 6.1 | -3.2 ± 5.4% | 2.8 ± 6.5 | 1.000 | 543.3 ± 28.0 | 3.86 ± 0.17 | 6.9 ± 0.9% | 105.7 ± 8.8 | 143.0 ± 6.2 | 22.3 ± 1.2 | 993 ± 142 | – |

## Scenario `special_event-5601c3`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 73.5 ± 3.1 | 8.9 ± 3.6% | -7.8 ± 3.2 | <0.001 | 324.1 ± 12.2 | 2.87 ± 0.14 | 6.4 ± 0.4% | 74.2 ± 4.8 | 72.8 ± 1.7 | 12.9 ± 0.4 | 32 ± 16 | – |
| **max_pressure** | 1 | uniform | on | 30 | 81.3 ± 3.9 | baseline | – | – | 348.5 ± 14.1 | 3.36 ± 0.16 | 7.3 ± 0.4% | 86.0 ± 6.0 | 76.3 ± 2.0 | 13.4 ± 0.4 | 84 ± 39 | – |
| fixed_time | 1 | uniform | on | 30 | 93.2 ± 2.0 | -16.0 ± 4.7% | 11.9 ± 3.4 | <0.001 | 312.1 ± 11.4 | 2.17 ± 0.06 | 5.3 ± 0.3% | 116.9 ± 3.2 | 68.1 ± 1.0 | 19.4 ± 0.5 | 88 ± 18 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 73.6 ± 3.1 | 8.8 ± 3.7% | -7.7 ± 3.3 | <0.001 | 324.7 ± 12.4 | 2.87 ± 0.14 | 6.4 ± 0.4% | 74.2 ± 4.7 | 73.0 ± 1.8 | 12.9 ± 0.4 | 35 ± 20 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 65.0 ± 1.4 | 19.1 ± 3.3% | -16.3 ± 3.5 | <0.001 | 323.3 ± 6.6 | 2.28 ± 0.05 | 7.2 ± 0.2% | 44.6 ± 1.0 | 88.9 ± 2.1 | 12.6 ± 0.3 | 32 ± 13 | – |
| rl | 1 | uniform | on | 30 | 60.6 ± 1.3 | 24.5 ± 3.5% | -20.7 ± 3.9 | <0.001 | 315.9 ± 8.2 | 2.01 ± 0.04 | 7.2 ± 0.3% | 40.4 ± 0.7 | 84.5 ± 2.1 | 12.7 ± 0.4 | 15 ± 7 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 1260 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.06 ± 0.00 | 1.04 ± 0.05 | 0.56 ± 0.02 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| earthquake | fixed_time | 1 | on | 30 | 7.0 ± 0.0 | 396.9 ± 36.3 | 284.0 ± 36.3 | 257.4 ± 10.1 | 210.7 ± 11.5 | – | – |
| earthquake | max_pressure-b8251d | 1 | on | 30 | 7.0 ± 0.0 | 303.3 ± 22.7 | 190.4 ± 22.7 | 176.0 ± 6.0 | 138.3 ± 6.1 | – | – |
| earthquake | max_pressure | 1 | on | 30 | 7.0 ± 0.0 | 417.9 ± 28.8 | 302.7 ± 27.2 | 247.1 ± 8.5 | 223.3 ± 9.7 | – | – |
| earthquake | max_pressure_plus | 1 | on | 30 | 7.0 ± 0.0 | 391.5 ± 32.4 | 278.6 ± 32.4 | 237.3 ± 11.2 | 216.8 ± 14.5 | – | – |
| earthquake | rl-8582b6 | 1 | on | 30 | 7.0 ± 0.0 | 544.2 ± 44.7 | 430.9 ± 43.7 | 386.5 ± 21.0 | 364.0 ± 29.0 | – | – |
| earthquake | rl | 1 | on | 30 | 7.0 ± 0.0 | 585.2 ± 59.6 | 469.9 ± 58.9 | 411.6 ± 21.2 | 414.8 ± 25.1 | – | – |
| emergency | fixed_time | 1 | on | 30 | 9.6 ± 0.2 | 135.3 ± 3.5 | 58.4 ± 3.4 | 107.7 ± 1.7 | 38.0 ± 5.7 | – | – |
| emergency | max_pressure-b8251d | 1 | on | 30 | 10.0 ± 0.0 | 108.4 ± 1.5 | 30.6 ± 1.5 | 41.3 ± 1.4 | 13.4 ± 1.6 | – | – |
| emergency | max_pressure | 1 | on | 30 | 10.0 ± 0.0 | 111.5 ± 2.7 | 33.8 ± 2.7 | 45.5 ± 3.2 | 17.7 ± 3.8 | – | – |
| emergency | max_pressure_plus | 1 | on | 30 | 10.0 ± 0.0 | 108.4 ± 1.5 | 30.7 ± 1.5 | 41.3 ± 1.4 | 13.4 ± 1.6 | – | – |
| emergency | rl-8582b6 | 1 | on | 30 | 10.0 ± 0.0 | 112.0 ± 2.1 | 34.2 ± 2.1 | 54.5 ± 3.8 | 24.2 ± 3.5 | – | – |
| emergency | rl | 1 | on | 30 | 10.0 ± 0.0 | 109.8 ± 2.1 | 32.1 ± 2.1 | 43.9 ± 2.3 | 14.5 ± 2.3 | – | – |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| earthquake | fixed_time | 1 | 30 | – | 30 | 147.87 ± 8.80 | – | – | – | 1412 ± 100 |
| earthquake | max_pressure-b8251d | 1 | 30 | 711 | 29 | 129.65 ± 4.87 | – | – | – | 720 ± 117 |
| earthquake | max_pressure | 1 | 30 | – | 30 | 178.62 ± 5.84 | – | – | – | 1643 ± 90 |
| earthquake | max_pressure_plus | 1 | 30 | – | 30 | 173.70 ± 8.15 | – | – | – | 1484 ± 138 |
| earthquake | rl-8582b6 | 1 | 30 | – | 30 | 329.85 ± 14.60 | – | – | – | 2864 ± 54 |
| earthquake | rl | 1 | 30 | – | 30 | 340.62 ± 12.07 | – | – | – | 2867 ± 49 |
| road_closure | fixed_time | 1 | 30 | 822 ± 140 | 13 | 30.71 ± 5.51 | – | – | – | 139 ± 55 |
| road_closure | max_pressure-b8251d | 1 | 30 | – | 30 | 92.74 ± 4.49 | – | – | – | 146 ± 59 |
| road_closure | max_pressure | 1 | 30 | 1804 ± 858 | 28 | 104.97 ± 5.97 | – | – | – | 281 ± 100 |
| road_closure | max_pressure_plus | 1 | 30 | 1888 ± 1048 | 28 | 107.06 ± 6.28 | – | – | – | 286 ± 93 |
| road_closure | rl-8582b6 | 1 | 30 | – | 30 | 243.69 ± 12.20 | – | – | – | 2701 ± 125 |
| road_closure | rl | 1 | 30 | – | 30 | 139.67 ± 7.33 | – | – | – | 1634 ± 158 |
| sinkhole_cross | fixed_time | 1 | 30 | 650 ± 81 | 20 | 59.51 ± 6.71 | – | – | – | 108 ± 44 |
| sinkhole_cross | max_pressure-b8251d | 1 | 30 | – | 30 | 101.92 ± 5.81 | – | – | – | 333 ± 102 |
| sinkhole_cross | max_pressure | 1 | 30 | – | 30 | 99.94 ± 6.09 | – | – | – | 297 ± 73 |
| sinkhole_cross | max_pressure_plus | 1 | 30 | – | 30 | 100.23 ± 5.27 | – | – | – | 296 ± 89 |
| sinkhole_cross | rl-8582b6 | 1 | 30 | – | 30 | 115.32 ± 10.87 | – | – | – | 1288 ± 140 |
| sinkhole_cross | rl | 1 | 30 | – | 30 | 112.95 ± 8.63 | – | – | – | 993 ± 142 |

## PERF-01: completed and unfinished trips

Depart delay = time waiting to enter a blocked entry lane (not in the delay column, which is timeLoss). Accrued delay incl. unfinished is a lower bound: trips still driving have only part of their delay.

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | depart delay s | delay + depart delay s | accrued delay incl. unfinished s (lower bound) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| earthquake | fixed_time | 1 | uniform | on | 30 | 2697 ± 23 | 482 ± 19 | 15.2 ± 0.6 | 292 ± 20 | 1.0 ± 0.4 | 190.4 ± 6.5 | 409.8 ± 13.8 | 248.9 ± 9.5 |
| earthquake | max_pressure-b8251d | 1 | uniform | on | 30 | 2985 ± 25 | 195 ± 26 | 6.1 ± 0.8 | 16 ± 12 | 0.9 ± 0.5 | 151.2 ± 9.4 | 328.7 ± 12.9 | 171.1 ± 5.7 |
| earthquake | max_pressure | 1 | uniform | on | 30 | 2812 ± 28 | 368 ± 24 | 11.6 ± 0.7 | 142 ± 22 | 1.1 ± 0.6 | 193.8 ± 9.2 | 416.7 ± 12.9 | 236.8 ± 7.8 |
| earthquake | max_pressure_plus | 1 | uniform | on | 30 | 2868 ± 26 | 312 ± 27 | 9.8 ± 0.8 | 99 ± 23 | 1.3 ± 0.7 | 177.0 ± 10.8 | 399.9 ± 17.5 | 227.4 ± 10.4 |
| earthquake | rl-8582b6 | 1 | uniform | on | 30 | 2574 ± 55 | 606 ± 58 | 19.0 ± 1.8 | 143 ± 38 | 14.9 ± 3.5 | 187.3 ± 19.6 | 557.2 ± 33.4 | 413.9 ± 21.1 |
| earthquake | rl | 1 | uniform | on | 30 | 2514 ± 50 | 666 ± 56 | 20.9 ± 1.7 | 253 ± 55 | 18.4 ± 2.3 | 221.8 ± 13.2 | 605.4 ± 23.5 | 442.4 ± 20.1 |
| emergency | fixed_time | 1 | uniform | on | 30 | 3734 ± 20 | 506 ± 30 | 11.9 ± 0.7 | 293 ± 29 | 0.0 ± 0.0 | 109.1 ± 9.3 | 196.7 ± 9.4 | 108.6 ± 1.7 |
| emergency | max_pressure-b8251d | 1 | uniform | on | 30 | 4120 ± 27 | 120 ± 11 | 2.8 ± 0.2 | 1 ± 2 | 0.0 ± 0.0 | 0.7 ± 0.2 | 41.8 ± 1.4 | 40.8 ± 1.6 |
| emergency | max_pressure | 1 | uniform | on | 30 | 4118 ± 23 | 122 ± 7 | 2.9 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.6 ± 0.2 | 46.1 ± 3.3 | 44.8 ± 3.2 |
| emergency | max_pressure_plus | 1 | uniform | on | 30 | 4121 ± 27 | 120 ± 10 | 2.8 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.6 ± 0.1 | 41.8 ± 1.4 | 40.8 ± 1.6 |
| emergency | rl-8582b6 | 1 | uniform | on | 30 | 4108 ± 24 | 133 ± 12 | 3.1 ± 0.3 | 0 ± 0 | 0.0 ± 0.0 | 0.6 ± 0.1 | 55.0 ± 3.8 | 53.7 ± 3.8 |
| emergency | rl | 1 | uniform | on | 30 | 4117 ± 25 | 123 ± 6 | 2.9 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 44.4 ± 2.3 | 43.3 ± 2.3 |
| off_peak | fixed_time | 1 | uniform | on | 30 | 1352 ± 15 | 55 ± 3 | 3.9 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 53.9 ± 0.2 | 52.8 ± 0.2 |
| off_peak | max_pressure-b8251d | 1 | uniform | on | 30 | 1363 ± 15 | 44 ± 3 | 3.1 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 22.9 ± 0.2 | 22.1 ± 0.2 |
| off_peak | max_pressure | 1 | uniform | on | 30 | 1364 ± 15 | 44 ± 3 | 3.1 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 22.8 ± 0.2 | 22.1 ± 0.2 |
| off_peak | max_pressure_plus | 1 | uniform | on | 30 | 1363 ± 15 | 44 ± 3 | 3.1 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 22.9 ± 0.2 | 22.1 ± 0.2 |
| off_peak | rl-8582b6 | 1 | uniform | on | 30 | 1365 ± 15 | 42 ± 3 | 3.0 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 20.3 ± 0.2 | 19.5 ± 0.2 |
| off_peak | rl | 1 | uniform | on | 30 | 1366 ± 15 | 42 ± 3 | 3.0 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 20.4 ± 0.2 | 19.6 ± 0.2 |
| road_closure | fixed_time | 1 | uniform | on | 30 | 4168 ± 19 | 668 ± 22 | 13.8 ± 0.4 | 454 ± 19 | 0.0 ± 0.0 | 247.8 ± 8.2 | 348.9 ± 7.7 | 125.7 ± 2.4 |
| road_closure | max_pressure-b8251d | 1 | uniform | on | 30 | 4564 ± 32 | 272 ± 34 | 5.6 ± 0.7 | 58 ± 26 | 0.0 ± 0.1 | 153.1 ± 6.1 | 258.0 ± 6.4 | 103.8 ± 3.3 |
| road_closure | max_pressure | 1 | uniform | on | 30 | 4518 ± 34 | 317 ± 38 | 6.5 ± 0.8 | 90 ± 27 | 0.1 ± 0.1 | 147.9 ± 7.5 | 260.3 ± 9.2 | 114.8 ± 4.5 |
| road_closure | max_pressure_plus | 1 | uniform | on | 30 | 4575 ± 34 | 261 ± 41 | 5.4 ± 0.8 | 45 ± 24 | 0.1 ± 0.1 | 130.9 ± 6.8 | 246.0 ± 8.5 | 114.2 ± 4.4 |
| road_closure | rl-8582b6 | 1 | uniform | on | 30 | 4308 ± 35 | 527 ± 38 | 10.9 ± 0.8 | 78 ± 21 | 2.1 ± 0.7 | 127.0 ± 5.8 | 331.7 ± 8.3 | 223.0 ± 8.7 |
| road_closure | rl | 1 | uniform | on | 30 | 4634 ± 23 | 201 ± 13 | 4.2 ± 0.3 | 1 ± 1 | 1.0 ± 0.4 | 96.9 ± 3.8 | 237.0 ± 7.1 | 137.8 ± 5.2 |
| rush_hour | fixed_time | 1 | uniform | on | 30 | 3709 ± 23 | 521 ± 24 | 12.3 ± 0.5 | 308 ± 25 | 0.0 ± 0.0 | 116.0 ± 10.6 | 201.9 ± 11.0 | 107.3 ± 1.3 |
| rush_hour | max_pressure-b8251d | 1 | uniform | on | 30 | 4111 ± 25 | 120 ± 6 | 2.8 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.7 ± 0.3 | 41.9 ± 3.3 | 40.6 ± 3.1 |
| rush_hour | max_pressure | 1 | uniform | on | 30 | 4110 ± 26 | 120 ± 6 | 2.8 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 42.1 ± 2.4 | 40.9 ± 2.4 |
| rush_hour | max_pressure_plus | 1 | uniform | on | 30 | 4111 ± 25 | 120 ± 6 | 2.8 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.7 ± 0.3 | 41.9 ± 3.3 | 40.6 ± 3.1 |
| rush_hour | rl-8582b6 | 1 | uniform | on | 30 | 4097 ± 22 | 133 ± 12 | 3.1 ± 0.3 | 0 ± 0 | 0.0 ± 0.0 | 0.7 ± 0.2 | 52.0 ± 4.0 | 50.6 ± 3.9 |
| rush_hour | rl | 1 | uniform | on | 30 | 4110 ± 24 | 120 ± 7 | 2.8 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 43.1 ± 2.4 | 42.0 ± 2.4 |
| sinkhole_cross | fixed_time | 1 | uniform | on | 30 | 3452 ± 21 | 778 ± 30 | 18.4 ± 0.6 | 568 ± 29 | 0.0 ± 0.0 | 176.3 ± 8.2 | 287.8 ± 6.4 | 152.0 ± 4.1 |
| sinkhole_cross | max_pressure-b8251d | 1 | uniform | on | 30 | 3858 ± 32 | 372 ± 40 | 8.8 ± 0.9 | 115 ± 29 | 0.0 ± 0.1 | 49.7 ± 6.7 | 157.9 ± 7.6 | 120.8 ± 5.2 |
| sinkhole_cross | max_pressure | 1 | uniform | on | 30 | 3839 ± 33 | 391 ± 40 | 9.2 ± 0.9 | 140 ± 31 | 0.0 ± 0.0 | 57.3 ± 8.7 | 163.7 ± 10.2 | 120.7 ± 5.5 |
| sinkhole_cross | max_pressure_plus | 1 | uniform | on | 30 | 3869 ± 34 | 361 ± 25 | 8.5 ± 0.6 | 104 ± 20 | 0.0 ± 0.0 | 51.8 ± 7.2 | 158.7 ± 8.4 | 119.1 ± 4.4 |
| sinkhole_cross | rl-8582b6 | 1 | uniform | on | 30 | 3988 ± 27 | 242 ± 29 | 5.7 ± 0.7 | 4 ± 4 | 1.2 ± 0.4 | 2.7 ± 1.6 | 129.1 ± 9.1 | 130.9 ± 9.2 |
| sinkhole_cross | rl | 1 | uniform | on | 30 | 3937 ± 31 | 294 ± 38 | 6.9 ± 0.9 | 24 ± 20 | 0.5 ± 0.4 | 9.8 ± 4.1 | 130.1 ± 8.4 | 128.3 ± 7.3 |
| special_event | fixed_time | 1 | uniform | on | 30 | 3958 ± 24 | 223 ± 13 | 5.3 ± 0.3 | 5 ± 5 | 0.0 ± 0.0 | 40.2 ± 3.7 | 132.6 ± 3.7 | 92.5 ± 2.1 |
| special_event | max_pressure-b8251d | 1 | uniform | on | 30 | 3913 ± 24 | 268 ± 18 | 6.4 ± 0.4 | 35 ± 10 | 0.0 ± 0.0 | 49.6 ± 2.1 | 114.9 ± 3.7 | 74.2 ± 3.3 |
| special_event | max_pressure | 1 | uniform | on | 30 | 3873 ± 23 | 307 ± 20 | 7.3 ± 0.5 | 48 ± 11 | 0.0 ± 0.0 | 51.0 ± 2.0 | 124.4 ± 4.6 | 82.3 ± 4.1 |
| special_event | max_pressure_plus | 1 | uniform | on | 30 | 3912 ± 24 | 269 ± 18 | 6.4 ± 0.4 | 35 ± 10 | 0.0 ± 0.0 | 49.7 ± 2.1 | 115.0 ± 3.8 | 74.3 ± 3.4 |
| special_event | rl-8582b6 | 1 | uniform | on | 30 | 3881 ± 24 | 299 ± 11 | 7.2 ± 0.2 | 103 ± 9 | 0.0 ± 0.0 | 48.5 ± 1.7 | 102.5 ± 1.9 | 64.9 ± 1.4 |
| special_event | rl | 1 | uniform | on | 30 | 3878 ± 25 | 303 ± 14 | 7.2 ± 0.3 | 116 ± 13 | 0.0 ± 0.0 | 45.8 ± 2.2 | 94.9 ± 2.2 | 60.7 ± 1.2 |

## Compute cost

1260 runs ok, 0 failed, 0 incomplete · experiment wall time 2263.4 s with [100] worker(s) · sum of run wall times 15757.2 s · 370.1× faster than real time per run · data 5092.6 MB (4.04 MB/run, 3.14 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 13.6 | 2.89 |
| max_pressure | 12.1 | 2.57 |
| max_pressure-b8251d | 11.6 | 2.43 |
| max_pressure_plus | 11.9 | 2.53 |
| rl | 12.7 | 2.71 |
| rl-8582b6 | 13.1 | 2.76 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
