# Regression screen: `max_pressure_plus` (max_pressure_plus (rho 0.25)) vs `max_pressure`

Experiment `final_d10` · verdict **PASS** · rules: delay regression ≤ +5.0 %, unfinished share ≤ +0.5 pp and not significantly above +0.1 pp, EV travel time not significantly above +1 s and no more EVs left unarrived on any seed, no safety events, every candidate run finished, at least 2 paired seeds per condition. Paired 95 % t-intervals, not adjusted for the number of conditions.

| Scenario | Demand / params | Seeds | Baseline delay | Candidate delay | Change | Unfinished Δ pp [95 % CI] | EV Δ s | EVs not arrived Δ | Benefits | Result |
|---|---|---:|---:|---:|---:|---|---:|---:|---|---|
| earthquake-c2b747 | cov 1, end 4500 | 30 | 227.50 | 209.83 | -7.8 % | -0.59 [-1.01, -0.17] | -38.48 | 0.00 | mean_delay_s, mean_delay_incl_depart_s, spillback_duration_s | PASS |
| emergency-c2b747 | cov 1, end 4500 | 30 | 29.64 | 29.72 | 0.3 % | 0.06 [0.01, 0.10] | 0.83 | 0.00 | – | PASS |
| off_peak-c2b747 | cov 1, end 4500 | 30 | 22.42 | 22.42 | 0.0 % | 0.00 [0.00, 0.00] | – | – | – | PASS |
| road_closure-c2b747 | cov 1, end 5400 | 30 | 88.42 | 85.83 | -2.9 % | 0.01 [-0.04, 0.06] | – | – | mean_delay_s, mean_delay_incl_depart_s, queue_p95_veh | PASS |
| rush_hour-c2b747 | cov 1, end 4500 | 30 | 29.33 | 29.07 | -0.9 % | 0.01 [-0.04, 0.06] | – | – | – | PASS |
| sinkhole_cross-c2b747 | cov 1, end 4500 | 30 | 47.98 | 43.49 | -9.4 % | -0.04 [-0.15, 0.08] | – | – | queue_p95_veh | PASS |
| special_event-c2b747 | cov 1, end 4500 | 30 | 52.84 | 49.40 | -6.5 % | -0.06 [-0.16, 0.04] | – | – | mean_delay_s, mean_delay_incl_depart_s, queue_p95_veh | PASS |

Scenario names with a `-<hash>` suffix carry scenario parameters (e.g. demand_scale); see experiment.json.
