# Experiment report: `final_d075`

Created 2026-11-06T02:16:11 · baseline **max_pressure** · code `aa0c16c` · SUMO 1.28.0

Matrix: scenarios earthquake-193e6a, emergency-193e6a, off_peak-193e6a, road_closure-193e6a, rush_hour-193e6a, sinkhole_cross-193e6a, special_event-193e6a · controllers fixed_time, max_pressure, max_pressure-b8251d, max_pressure_plus, rl, rl-8582b6 · seeds [201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230] · coverage 1 · sampling uniform · EV preemption on · warm-up 900 s · run end 4500, 5400 s

Scenario parameters: `earthquake-193e6a` = `{"demand_scale": 0.75}` · `emergency-193e6a` = `{"demand_scale": 0.75}` · `off_peak-193e6a` = `{"demand_scale": 0.75}` · `road_closure-193e6a` = `{"demand_scale": 0.75}` · `rush_hour-193e6a` = `{"demand_scale": 0.75}` · `sinkhole_cross-193e6a` = `{"demand_scale": 0.75}` · `special_event-193e6a` = `{"demand_scale": 0.75}`

Controller parameters: `max_pressure-b8251d` = `{"rho": 0.25, "closure_aware": true, "closure_weight": 0.35}` · `rl-8582b6` = `{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}`

Reproduce:

```bash
python -m teamb.experiments run --backend modal --no-report --name final_d075 --workers 100 --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak --seeds 201-230 --scenario-params '{"demand_scale": 0.75}' --controllers max_pressure --controller-params '{"rho": 0.25, "closure_aware": true, "closure_weight": 0.35}'
python -m teamb.experiments run --backend modal --no-report --name final_d075 --workers 100 --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak --seeds 201-230 --scenario-params '{"demand_scale": 0.75}' --controllers rl --controller-params '{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}'
python -m teamb.experiments run --backend modal --no-report --name final_d075 --workers 100 --scenarios rush_hour,special_event,emergency,road_closure,sinkhole_cross,earthquake,off_peak --seeds 201-230 --scenario-params '{"demand_scale": 0.75}' --controllers fixed_time,max_pressure,max_pressure_plus,rl
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `earthquake-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 85.7 ± 4.4 | 15.4 ± 7.5% | -23.4 ± 11.3 | <0.001 | 501.8 ± 27.0 | 2.37 ± 0.10 | 2.5 ± 0.1% | 122.0 ± 6.7 | 40.1 ± 1.5 | 6.7 ± 0.4 | 40 ± 20 | 198.5 ± 8.1 |
| **max_pressure** | 1 | uniform | on | 30 | 109.1 ± 13.9 | baseline | – | – | 606.8 ± 64.0 | 3.76 ± 0.48 | 2.5 ± 0.1% | 151.8 ± 20.3 | 55.3 ± 5.7 | 7.7 ± 0.8 | 344 ± 109 | 213.3 ± 18.8 |
| fixed_time | 1 | uniform | on | 30 | 159.2 ± 14.2 | -55.5 ± 13.8% | 50.1 ± 12.1 | <0.001 | 765.5 ± 58.3 | 3.80 ± 0.22 | 3.3 ± 0.2% | 232.3 ± 18.5 | 68.3 ± 9.3 | 15.4 ± 1.5 | 546 ± 106 | 224.4 ± 21.3 |
| max_pressure_plus | 1 | uniform | on | 30 | 94.5 ± 11.9 | 12.7 ± 3.1% | -14.6 ± 4.2 | <0.001 | 511.9 ± 49.0 | 3.02 ± 0.38 | 2.5 ± 0.1% | 130.1 ± 17.4 | 49.7 ± 4.9 | 6.9 ± 0.8 | 166 ± 79 | 204.5 ± 13.2 |
| rl-8582b6 | 1 | uniform | on | 30 | 169.3 ± 30.1 | -59.7 ± 18.7% | 60.2 ± 24.2 | <0.001 | 927.3 ± 114.9 | 4.29 ± 0.49 | 2.5 ± 0.2% | 219.6 ± 33.5 | 106.5 ± 26.7 | 11.4 ± 2.0 | 1182 ± 198 | 273.4 ± 34.2 |
| rl | 1 | uniform | on | 30 | 90.1 ± 18.4 | 16.6 ± 8.3% | -19.0 ± 14.4 | 0.011 | 506.5 ± 70.4 | 2.70 ± 0.27 | 2.5 ± 0.1% | 120.6 ± 22.4 | 51.8 ± 13.6 | 5.7 ± 1.6 | 217 ± 125 | 203.8 ± 18.2 |

## Scenario `emergency-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 25.3 ± 0.2 | 0.3 ± 1.0% | -0.1 ± 0.3 | 1.000 | 161.1 ± 0.5 | 0.88 ± 0.01 | 2.5 ± 0.1% | 23.6 ± 0.3 | 27.5 ± 0.3 | 2.1 ± 0.1 | 0 ± 0 | 96.1 ± 1.1 |
| **max_pressure** | 1 | uniform | on | 30 | 25.4 ± 0.2 | baseline | – | – | 161.4 ± 0.6 | 0.88 ± 0.01 | 2.5 ± 0.1% | 23.8 ± 0.4 | 27.4 ± 0.4 | 2.1 ± 0.1 | 0 ± 0 | 95.8 ± 1.1 |
| fixed_time | 1 | uniform | on | 30 | 60.5 ± 0.6 | -138.4 ± 1.9% | 35.1 ± 0.5 | <0.001 | 236.2 ± 2.0 | 1.49 ± 0.01 | 3.3 ± 0.1% | 85.9 ± 0.9 | 29.3 ± 0.3 | 10.4 ± 0.2 | 0 ± 0 | 109.8 ± 1.2 |
| max_pressure_plus | 1 | uniform | on | 30 | 25.3 ± 0.2 | 0.3 ± 1.0% | -0.1 ± 0.3 | 1.000 | 161.1 ± 0.5 | 0.88 ± 0.01 | 2.5 ± 0.1% | 23.6 ± 0.3 | 27.5 ± 0.3 | 2.1 ± 0.1 | 0 ± 0 | 96.1 ± 1.1 |
| rl-8582b6 | 1 | uniform | on | 30 | 25.5 ± 0.2 | -0.3 ± 0.9% | 0.1 ± 0.2 | 1.000 | 159.0 ± 0.6 | 0.93 ± 0.01 | 2.5 ± 0.1% | 22.4 ± 0.3 | 29.4 ± 0.3 | 2.5 ± 0.2 | 0 ± 0 | 95.1 ± 1.2 |
| rl | 1 | uniform | on | 30 | 25.1 ± 0.2 | 1.0 ± 1.0% | -0.3 ± 0.3 | 0.194 | 162.0 ± 0.6 | 1.01 ± 0.01 | 2.5 ± 0.1% | 26.2 ± 0.3 | 23.8 ± 0.3 | 2.0 ± 0.0 | 0 ± 0 | 95.8 ± 0.9 |

## Scenario `off_peak-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 23.2 ± 0.3 | 0.0 ± 0.0% | 0.0 ± 0.0 | 1.000 | 164.2 ± 1.1 | 0.69 ± 0.01 | 3.2 ± 0.2% | 19.2 ± 0.4 | 28.6 ± 0.5 | 1.0 ± 0.0 | 0 ± 0 | – |
| **max_pressure** | 1 | uniform | on | 30 | 23.2 ± 0.3 | baseline | – | – | 164.2 ± 1.1 | 0.69 ± 0.01 | 3.2 ± 0.2% | 19.2 ± 0.4 | 28.6 ± 0.5 | 1.0 ± 0.0 | 0 ± 0 | – |
| fixed_time | 1 | uniform | on | 30 | 51.9 ± 0.5 | -124.4 ± 3.4% | 28.7 ± 0.5 | <0.001 | 210.4 ± 0.4 | 1.29 ± 0.01 | 4.0 ± 0.2% | 71.6 ± 0.4 | 25.4 ± 0.6 | 3.0 ± 0.1 | 0 ± 0 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 23.2 ± 0.3 | 0.0 ± 0.0% | 0.0 ± 0.0 | 1.000 | 164.2 ± 1.1 | 0.69 ± 0.01 | 3.2 ± 0.2% | 19.2 ± 0.4 | 28.6 ± 0.5 | 1.0 ± 0.0 | 0 ± 0 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 16.5 ± 0.2 | 28.7 ± 1.1% | -6.7 ± 0.3 | <0.001 | 151.2 ± 0.8 | 0.73 ± 0.01 | 3.0 ± 0.2% | 17.2 ± 0.3 | 15.5 ± 0.3 | 1.0 ± 0.0 | 0 ± 0 | – |
| rl | 1 | uniform | on | 30 | 15.9 ± 0.2 | 31.1 ± 1.0% | -7.2 ± 0.3 | <0.001 | 152.3 ± 0.7 | 0.73 ± 0.01 | 3.0 ± 0.2% | 18.0 ± 0.3 | 13.1 ± 0.2 | 0.9 ± 0.1 | 0 ± 0 | – |

## Scenario `road_closure-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 51.5 ± 2.2 | -12.4 ± 3.8% | 5.4 ± 1.9 | <0.001 | 385.1 ± 14.1 | 1.81 ± 0.07 | 2.3 ± 0.1% | 70.8 ± 3.6 | 29.6 ± 0.6 | 4.2 ± 0.3 | 2 ± 3 | – |
| **max_pressure** | 1 | uniform | on | 30 | 46.1 ± 2.4 | baseline | – | – | 332.9 ± 12.6 | 1.56 ± 0.07 | 2.3 ± 0.1% | 59.3 ± 3.9 | 31.2 ± 0.9 | 3.7 ± 0.2 | 2 ± 2 | – |
| fixed_time | 1 | uniform | on | 30 | 106.2 ± 2.0 | -133.0 ± 7.6% | 60.1 ± 1.8 | <0.001 | 592.9 ± 10.2 | 2.89 ± 0.05 | 2.9 ± 0.1% | 169.9 ± 3.6 | 35.1 ± 0.8 | 14.2 ± 0.4 | 8 ± 5 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 45.2 ± 1.5 | 1.2 ± 2.3% | -0.9 ± 1.3 | 0.193 | 323.8 ± 8.0 | 1.51 ± 0.04 | 2.3 ± 0.1% | 57.9 ± 2.4 | 30.9 ± 0.6 | 3.6 ± 0.2 | 1 ± 2 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 81.3 ± 7.4 | -76.2 ± 13.1% | 35.2 ± 6.2 | <0.001 | 555.2 ± 44.0 | 2.51 ± 0.19 | 2.3 ± 0.1% | 101.4 ± 10.0 | 58.7 ± 4.6 | 6.8 ± 0.6 | 585 ± 127 | – |
| rl | 1 | uniform | on | 30 | 51.3 ± 2.6 | -11.7 ± 3.9% | 5.2 ± 1.9 | <0.001 | 384.1 ± 16.3 | 1.96 ± 0.09 | 2.2 ± 0.1% | 68.8 ± 4.4 | 31.6 ± 0.9 | 3.9 ± 0.2 | 21 ± 16 | – |

## Scenario `rush_hour-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 24.9 ± 0.2 | 0.5 ± 0.7% | -0.1 ± 0.2 | 0.463 | 160.0 ± 0.6 | 0.86 ± 0.01 | 2.6 ± 0.1% | 23.1 ± 0.2 | 27.2 ± 0.3 | 2.1 ± 0.1 | 0 ± 0 | – |
| **max_pressure** | 1 | uniform | on | 30 | 25.0 ± 0.2 | baseline | – | – | 160.0 ± 0.6 | 0.87 ± 0.01 | 2.5 ± 0.1% | 23.3 ± 0.3 | 27.2 ± 0.3 | 2.1 ± 0.1 | 0 ± 0 | – |
| fixed_time | 1 | uniform | on | 30 | 61.7 ± 0.6 | -146.4 ± 2.8% | 36.6 ± 0.6 | <0.001 | 236.1 ± 1.7 | 1.44 ± 0.01 | 3.3 ± 0.1% | 88.4 ± 0.8 | 28.8 ± 0.3 | 10.8 ± 0.2 | 0 ± 0 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 24.9 ± 0.2 | 0.5 ± 0.7% | -0.1 ± 0.2 | 0.463 | 160.0 ± 0.6 | 0.86 ± 0.01 | 2.6 ± 0.1% | 23.1 ± 0.2 | 27.2 ± 0.3 | 2.1 ± 0.1 | 0 ± 0 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 25.1 ± 0.2 | -0.2 ± 0.9% | 0.1 ± 0.2 | 0.667 | 158.2 ± 0.6 | 0.92 ± 0.01 | 2.5 ± 0.1% | 22.2 ± 0.3 | 28.7 ± 0.3 | 2.3 ± 0.2 | 0 ± 0 | – |
| rl | 1 | uniform | on | 30 | 24.9 ± 0.2 | 0.7 ± 0.8% | -0.2 ± 0.2 | 0.288 | 161.1 ± 0.6 | 1.01 ± 0.01 | 2.5 ± 0.1% | 26.0 ± 0.3 | 23.5 ± 0.2 | 2.0 ± 0.1 | 0 ± 0 | – |

## Scenario `sinkhole_cross-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 29.3 ± 0.4 | -2.2 ± 1.2% | 0.6 ± 0.3 | 0.004 | 182.2 ± 1.4 | 1.03 ± 0.02 | 2.5 ± 0.1% | 25.0 ± 0.5 | 34.5 ± 0.5 | 2.9 ± 0.1 | 0 ± 0 | – |
| **max_pressure** | 1 | uniform | on | 30 | 28.7 ± 0.4 | baseline | – | – | 178.2 ± 1.4 | 1.03 ± 0.02 | 2.5 ± 0.1% | 25.3 ± 0.5 | 32.8 ± 0.5 | 3.0 ± 0.1 | 0 ± 0 | – |
| fixed_time | 1 | uniform | on | 30 | 122.1 ± 3.4 | -326.7 ± 13.0% | 93.5 ± 3.4 | <0.001 | 520.2 ± 14.3 | 3.06 ± 0.09 | 4.3 ± 0.4% | 190.0 ± 6.3 | 40.2 ± 1.0 | 20.1 ± 1.1 | 1 ± 1 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 28.8 ± 0.4 | -0.4 ± 1.3% | 0.1 ± 0.4 | 0.619 | 178.2 ± 1.4 | 1.03 ± 0.02 | 2.5 ± 0.1% | 25.5 ± 0.4 | 32.8 ± 0.6 | 2.9 ± 0.1 | 0 ± 0 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 29.0 ± 0.3 | -1.4 ± 1.4% | 0.4 ± 0.4 | 0.116 | 179.6 ± 1.2 | 1.07 ± 0.01 | 2.5 ± 0.1% | 23.7 ± 0.3 | 35.7 ± 0.5 | 3.0 ± 0.0 | 0 ± 0 | – |
| rl | 1 | uniform | on | 30 | 28.3 ± 0.3 | 1.3 ± 1.2% | -0.4 ± 0.4 | 0.108 | 175.3 ± 1.0 | 1.15 ± 0.02 | 2.5 ± 0.1% | 27.4 ± 0.4 | 29.4 ± 0.4 | 2.7 ± 0.2 | 0 ± 0 | – |

## Scenario `special_event-193e6a`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure-b8251d | 1 | uniform | on | 30 | 26.9 ± 0.4 | 0.8 ± 1.4% | -0.2 ± 0.4 | 0.433 | 165.0 ± 1.1 | 0.97 ± 0.01 | 3.0 ± 0.1% | 25.1 ± 0.4 | 28.9 ± 0.5 | 2.9 ± 0.1 | 0 ± 0 | – |
| **max_pressure** | 1 | uniform | on | 30 | 27.2 ± 0.5 | baseline | – | – | 165.3 ± 1.2 | 0.99 ± 0.02 | 3.0 ± 0.1% | 25.1 ± 0.5 | 29.5 ± 0.7 | 2.7 ± 0.2 | 0 ± 0 | – |
| fixed_time | 1 | uniform | on | 30 | 60.3 ± 0.9 | -122.0 ± 3.1% | 33.1 ± 0.7 | <0.001 | 223.0 ± 1.6 | 1.46 ± 0.02 | 3.9 ± 0.2% | 80.0 ± 0.4 | 39.0 ± 1.9 | 9.5 ± 0.2 | 2 ± 2 | – |
| max_pressure_plus | 1 | uniform | on | 30 | 26.9 ± 0.4 | 0.8 ± 1.4% | -0.2 ± 0.4 | 0.433 | 165.0 ± 1.1 | 0.97 ± 0.01 | 3.0 ± 0.1% | 25.1 ± 0.4 | 28.9 ± 0.5 | 2.9 ± 0.1 | 0 ± 0 | – |
| rl-8582b6 | 1 | uniform | on | 30 | 36.6 ± 1.6 | -34.5 ± 5.4% | 9.4 ± 1.4 | <0.001 | 204.3 ± 9.1 | 1.31 ± 0.05 | 2.9 ± 0.1% | 26.0 ± 0.5 | 48.1 ± 3.0 | 3.5 ± 0.2 | 3 ± 5 | – |
| rl | 1 | uniform | on | 30 | 30.7 ± 1.0 | -13.0 ± 3.0% | 3.5 ± 0.8 | <0.001 | 173.1 ± 3.6 | 1.25 ± 0.03 | 3.0 ± 0.1% | 28.1 ± 0.4 | 33.5 ± 1.8 | 3.0 ± 0.1 | 1 ± 2 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 1 | 1260 | 1.000 ± 0.000 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.03 ± 0.00 | 0.20 ± 0.01 | 0.14 ± 0.01 | 0 ± 0 | 0 ± 0 |

## Emergency vehicles

EV TT = travel time of emergency vehicles. Others' delay = mean delay of all other finished trips. Extra delay near EVs = within-run, movement-stratified difference between trips overlapping an EV trip and the rest (an indication; the clean number is the paired preemption on/off comparison when both were run).

| scenario | controller | cov | EV pre | n | EVs | EV TT s | EV delay s | others' delay s | extra delay near EVs s | EV TT on−off s | others on−off s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| earthquake | fixed_time | 1 | on | 30 | 7.0 ± 0.0 | 224.4 ± 21.3 | 111.5 ± 21.3 | 159.4 ± 14.2 | 141.2 ± 15.4 | – | – |
| earthquake | max_pressure-b8251d | 1 | on | 30 | 7.0 ± 0.0 | 198.5 ± 8.1 | 85.6 ± 8.1 | 85.7 ± 4.4 | 97.8 ± 6.6 | – | – |
| earthquake | max_pressure | 1 | on | 30 | 7.0 ± 0.0 | 213.3 ± 18.8 | 100.5 ± 18.8 | 109.1 ± 13.8 | 127.5 ± 19.8 | – | – |
| earthquake | max_pressure_plus | 1 | on | 30 | 7.0 ± 0.0 | 204.5 ± 13.2 | 91.5 ± 13.2 | 94.5 ± 11.9 | 105.8 ± 17.1 | – | – |
| earthquake | rl-8582b6 | 1 | on | 30 | 7.0 ± 0.0 | 273.4 ± 34.2 | 160.8 ± 34.6 | 169.3 ± 30.1 | 205.8 ± 30.7 | – | – |
| earthquake | rl | 1 | on | 30 | 7.0 ± 0.0 | 203.8 ± 18.2 | 90.8 ± 18.2 | 90.1 ± 18.4 | 102.8 ± 25.1 | – | – |
| emergency | fixed_time | 1 | on | 30 | 10.0 ± 0.0 | 109.8 ± 1.2 | 32.1 ± 1.2 | 60.7 ± 0.6 | 9.1 ± 0.9 | – | – |
| emergency | max_pressure-b8251d | 1 | on | 30 | 10.0 ± 0.0 | 96.1 ± 1.1 | 18.3 ± 1.1 | 25.3 ± 0.2 | 5.0 ± 0.4 | – | – |
| emergency | max_pressure | 1 | on | 30 | 10.0 ± 0.0 | 95.8 ± 1.1 | 18.1 ± 1.1 | 25.4 ± 0.2 | 4.6 ± 0.4 | – | – |
| emergency | max_pressure_plus | 1 | on | 30 | 10.0 ± 0.0 | 96.1 ± 1.1 | 18.3 ± 1.1 | 25.3 ± 0.2 | 5.0 ± 0.4 | – | – |
| emergency | rl-8582b6 | 1 | on | 30 | 10.0 ± 0.0 | 95.1 ± 1.2 | 17.4 ± 1.2 | 25.5 ± 0.2 | 4.2 ± 0.4 | – | – |
| emergency | rl | 1 | on | 30 | 10.0 ± 0.0 | 95.8 ± 0.9 | 18.1 ± 0.9 | 25.2 ± 0.2 | 3.9 ± 0.4 | – | – |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| earthquake | fixed_time | 1 | 30 | 343 ± 68 | 2 | 56.51 ± 7.87 | – | – | – | 546 ± 106 |
| earthquake | max_pressure-b8251d | 1 | 30 | 186 ± 64 | 0 | 33.81 ± 2.47 | – | – | – | 40 ± 20 |
| earthquake | max_pressure | 1 | 30 | 169 ± 54 | 0 | 45.93 ± 7.35 | – | – | – | 344 ± 109 |
| earthquake | max_pressure_plus | 1 | 30 | 184 ± 63 | 0 | 38.38 ± 6.35 | – | – | – | 166 ± 79 |
| earthquake | rl-8582b6 | 1 | 30 | 325 ± 62 | 2 | 78.69 ± 17.29 | – | – | – | 1182 ± 198 |
| earthquake | rl | 1 | 30 | 169 ± 53 | 0 | 36.84 ± 9.99 | – | – | – | 217 ± 125 |
| road_closure | fixed_time | 1 | 30 | 1188 ± 92 | 0 | 37.76 ± 2.23 | – | – | – | 8 ± 5 |
| road_closure | max_pressure-b8251d | 1 | 30 | 389 ± 62 | 0 | 21.71 ± 1.81 | – | – | – | 2 ± 3 |
| road_closure | max_pressure | 1 | 30 | 333 ± 41 | 0 | 17.56 ± 2.00 | – | – | – | 2 ± 2 |
| road_closure | max_pressure_plus | 1 | 30 | 312 ± 47 | 0 | 16.73 ± 1.36 | – | – | – | 1 ± 2 |
| road_closure | rl-8582b6 | 1 | 30 | 802 ± 87 | 0 | 45.10 ± 5.88 | – | – | – | 585 ± 127 |
| road_closure | rl | 1 | 30 | 444 ± 66 | 0 | 21.71 ± 2.29 | – | – | – | 21 ± 16 |
| sinkhole_cross | fixed_time | 1 | 30 | 938 ± 99 | 21 | 47.03 ± 2.80 | – | – | – | 1 ± 1 |
| sinkhole_cross | max_pressure-b8251d | 1 | 30 | 265 ± 67 | 0 | 4.50 ± 0.43 | – | – | – | 0 ± 0 |
| sinkhole_cross | max_pressure | 1 | 30 | 272 ± 85 | 0 | 4.16 ± 0.38 | – | – | – | 0 ± 0 |
| sinkhole_cross | max_pressure_plus | 1 | 30 | 259 ± 66 | 0 | 4.16 ± 0.39 | – | – | – | 0 ± 0 |
| sinkhole_cross | rl-8582b6 | 1 | 30 | 303 ± 77 | 0 | 4.68 ± 0.42 | – | – | – | 0 ± 0 |
| sinkhole_cross | rl | 1 | 30 | 287 ± 66 | 0 | 4.08 ± 0.39 | – | – | – | 0 ± 0 |

## PERF-01: completed and unfinished trips

Depart delay = time waiting to enter a blocked entry lane (not in the delay column, which is timeLoss). Accrued delay incl. unfinished is a lower bound: trips still driving have only part of their delay.

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | depart delay s | delay + depart delay s | accrued delay incl. unfinished s (lower bound) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| earthquake | fixed_time | 1 | uniform | on | 30 | 1847 ± 18 | 62 ± 4 | 3.2 ± 0.2 | 0 ± 0 | 0.9 ± 1.0 | 6.1 ± 3.3 | 165.5 ± 17.2 | 155.3 ± 13.7 |
| earthquake | max_pressure-b8251d | 1 | uniform | on | 30 | 1862 ± 19 | 48 ± 2 | 2.5 ± 0.1 | 0 ± 0 | 0.6 ± 0.3 | 5.0 ± 2.3 | 90.9 ± 5.9 | 83.9 ± 4.3 |
| earthquake | max_pressure | 1 | uniform | on | 30 | 1862 ± 18 | 48 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.6 ± 0.3 | 1.0 ± 0.7 | 110.1 ± 14.2 | 106.7 ± 13.5 |
| earthquake | max_pressure_plus | 1 | uniform | on | 30 | 1862 ± 18 | 48 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.6 ± 0.3 | 0.7 ± 0.4 | 95.2 ± 12.0 | 92.4 ± 11.6 |
| earthquake | rl-8582b6 | 1 | uniform | on | 30 | 1861 ± 18 | 48 ± 3 | 2.5 ± 0.2 | 0 ± 0 | 1.7 ± 2.0 | 1.9 ± 2.3 | 171.2 ± 32.2 | 166.5 ± 31.2 |
| earthquake | rl | 1 | uniform | on | 30 | 1862 ± 18 | 48 ± 2 | 2.5 ± 0.1 | 0 ± 0 | 1.0 ± 1.1 | 1.3 ± 1.5 | 91.4 ± 19.9 | 88.2 ± 18.1 |
| emergency | fixed_time | 1 | uniform | on | 30 | 2458 ± 18 | 83 ± 4 | 3.3 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 61.0 ± 0.6 | 59.8 ± 0.6 |
| emergency | max_pressure-b8251d | 1 | uniform | on | 30 | 2477 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 25.8 ± 0.1 | 25.0 ± 0.1 |
| emergency | max_pressure | 1 | uniform | on | 30 | 2477 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 25.9 ± 0.2 | 25.1 ± 0.2 |
| emergency | max_pressure_plus | 1 | uniform | on | 30 | 2477 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 25.8 ± 0.1 | 25.0 ± 0.1 |
| emergency | rl-8582b6 | 1 | uniform | on | 30 | 2476 ± 18 | 65 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 26.0 ± 0.2 | 25.2 ± 0.2 |
| emergency | rl | 1 | uniform | on | 30 | 2477 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 25.7 ± 0.2 | 24.8 ± 0.2 |
| off_peak | fixed_time | 1 | uniform | on | 30 | 811 ± 8 | 34 ± 2 | 4.0 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 52.4 ± 0.5 | 51.3 ± 0.5 |
| off_peak | max_pressure-b8251d | 1 | uniform | on | 30 | 818 ± 9 | 27 ± 2 | 3.2 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 23.7 ± 0.3 | 22.9 ± 0.3 |
| off_peak | max_pressure | 1 | uniform | on | 30 | 818 ± 9 | 27 ± 2 | 3.2 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 23.7 ± 0.3 | 22.9 ± 0.3 |
| off_peak | max_pressure_plus | 1 | uniform | on | 30 | 818 ± 9 | 27 ± 2 | 3.2 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 23.7 ± 0.3 | 22.9 ± 0.3 |
| off_peak | rl-8582b6 | 1 | uniform | on | 30 | 820 ± 9 | 26 ± 2 | 3.0 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 17.0 ± 0.2 | 16.3 ± 0.2 |
| off_peak | rl | 1 | uniform | on | 30 | 820 ± 9 | 25 ± 2 | 3.0 ± 0.2 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 16.4 ± 0.2 | 15.8 ± 0.2 |
| road_closure | fixed_time | 1 | uniform | on | 30 | 2811 ± 20 | 83 ± 3 | 2.9 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 31.4 ± 4.5 | 138.6 ± 6.3 | 104.2 ± 2.0 |
| road_closure | max_pressure-b8251d | 1 | uniform | on | 30 | 2830 ± 20 | 65 ± 3 | 2.2 ± 0.1 | 0 ± 0 | 0.0 ± 0.1 | 0.6 ± 0.1 | 52.1 ± 2.2 | 50.6 ± 2.1 |
| road_closure | max_pressure | 1 | uniform | on | 30 | 2829 ± 20 | 66 ± 3 | 2.3 ± 0.1 | 0 ± 0 | 0.0 ± 0.1 | 0.5 ± 0.0 | 46.6 ± 2.4 | 45.4 ± 2.4 |
| road_closure | max_pressure_plus | 1 | uniform | on | 30 | 2829 ± 20 | 65 ± 3 | 2.3 ± 0.1 | 0 ± 0 | 0.0 ± 0.1 | 0.5 ± 0.0 | 45.8 ± 1.5 | 44.5 ± 1.5 |
| road_closure | rl-8582b6 | 1 | uniform | on | 30 | 2829 ± 20 | 65 ± 3 | 2.3 ± 0.1 | 0 ± 0 | 0.1 ± 0.1 | 0.5 ± 0.0 | 81.9 ± 7.4 | 79.8 ± 7.2 |
| road_closure | rl | 1 | uniform | on | 30 | 2830 ± 20 | 65 ± 3 | 2.2 ± 0.1 | 0 ± 0 | 0.0 ± 0.1 | 0.6 ± 0.1 | 51.9 ± 2.7 | 50.4 ± 2.6 |
| rush_hour | fixed_time | 1 | uniform | on | 30 | 2448 ± 18 | 83 ± 4 | 3.3 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 62.2 ± 0.6 | 60.9 ± 0.6 |
| rush_hour | max_pressure-b8251d | 1 | uniform | on | 30 | 2466 ± 18 | 65 ± 2 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 25.4 ± 0.2 | 24.6 ± 0.2 |
| rush_hour | max_pressure | 1 | uniform | on | 30 | 2468 ± 18 | 63 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 25.6 ± 0.2 | 24.7 ± 0.2 |
| rush_hour | max_pressure_plus | 1 | uniform | on | 30 | 2466 ± 18 | 65 ± 2 | 2.6 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 25.4 ± 0.2 | 24.6 ± 0.2 |
| rush_hour | rl-8582b6 | 1 | uniform | on | 30 | 2467 ± 17 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 25.6 ± 0.2 | 24.8 ± 0.2 |
| rush_hour | rl | 1 | uniform | on | 30 | 2467 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 25.4 ± 0.2 | 24.6 ± 0.2 |
| sinkhole_cross | fixed_time | 1 | uniform | on | 30 | 2422 ± 18 | 109 ± 10 | 4.3 ± 0.4 | 1 ± 1 | 0.0 ± 0.0 | 21.7 ± 5.9 | 144.2 ± 8.7 | 121.0 ± 3.7 |
| sinkhole_cross | max_pressure-b8251d | 1 | uniform | on | 30 | 2467 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 29.8 ± 0.4 | 28.9 ± 0.4 |
| sinkhole_cross | max_pressure | 1 | uniform | on | 30 | 2467 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 29.2 ± 0.4 | 28.3 ± 0.4 |
| sinkhole_cross | max_pressure_plus | 1 | uniform | on | 30 | 2467 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 29.3 ± 0.4 | 28.4 ± 0.4 |
| sinkhole_cross | rl-8582b6 | 1 | uniform | on | 30 | 2467 ± 18 | 64 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 29.5 ± 0.3 | 28.6 ± 0.3 |
| sinkhole_cross | rl | 1 | uniform | on | 30 | 2468 ± 18 | 63 ± 3 | 2.5 ± 0.1 | 0 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 28.8 ± 0.3 | 27.9 ± 0.3 |
| special_event | fixed_time | 1 | uniform | on | 30 | 2420 ± 20 | 99 ± 4 | 3.9 ± 0.2 | 1 ± 0 | 0.0 ± 0.0 | 0.7 ± 0.3 | 61.0 ± 1.1 | 59.5 ± 0.9 |
| special_event | max_pressure-b8251d | 1 | uniform | on | 30 | 2444 ± 21 | 75 ± 3 | 3.0 ± 0.1 | 1 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 27.5 ± 0.4 | 26.6 ± 0.4 |
| special_event | max_pressure | 1 | uniform | on | 30 | 2444 ± 21 | 75 ± 3 | 3.0 ± 0.1 | 1 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 27.7 ± 0.5 | 26.8 ± 0.5 |
| special_event | max_pressure_plus | 1 | uniform | on | 30 | 2444 ± 21 | 75 ± 3 | 3.0 ± 0.1 | 1 ± 0 | 0.0 ± 0.0 | 0.5 ± 0.0 | 27.5 ± 0.4 | 26.6 ± 0.4 |
| special_event | rl-8582b6 | 1 | uniform | on | 30 | 2445 ± 21 | 74 ± 4 | 3.0 ± 0.1 | 1 ± 0 | 0.0 ± 0.0 | 2.3 ± 0.9 | 38.9 ± 2.3 | 35.9 ± 1.6 |
| special_event | rl | 1 | uniform | on | 30 | 2443 ± 21 | 76 ± 4 | 3.0 ± 0.1 | 1 ± 0 | 0.0 ± 0.0 | 0.7 ± 0.2 | 31.4 ± 1.1 | 30.2 ± 0.9 |

## Compute cost

1260 runs ok, 0 failed, 0 incomplete · experiment wall time 1057.5 s with [100] worker(s) · sum of run wall times 10137.8 s · 575.3× faster than real time per run · data 3668.0 MB (2.91 MB/run, 2.26 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| fixed_time | 8.9 | 1.89 |
| max_pressure | 7.8 | 1.66 |
| max_pressure-b8251d | 8.0 | 1.67 |
| max_pressure_plus | 7.7 | 1.64 |
| rl | 7.8 | 1.66 |
| rl-8582b6 | 8.1 | 1.69 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
