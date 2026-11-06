# Regression screen: `max_pressure_plus` (max_pressure_plus (rho 0.25)) vs `max_pressure`

Experiment `final_d125` · verdict **PASS** · rules: delay regression ≤ +5.0 %, unfinished share ≤ +0.5 pp and not significantly above +0.1 pp, EV travel time not significantly above +1 s and no more EVs left unarrived on any seed, no safety events, every candidate run finished, at least 2 paired seeds per condition. Paired 95 % t-intervals, not adjusted for the number of conditions.

| Scenario | Demand / params | Seeds | Baseline delay | Candidate delay | Change | Unfinished Δ pp [95 % CI] | EV Δ s | EVs not arrived Δ | Benefits | Result |
|---|---|---:|---:|---:|---:|---|---:|---:|---|---|
| earthquake-5601c3 | cov 1, end 4500 | 30 | 247.20 | 237.37 | -4.0 % | -1.77 [-2.53, -1.01] | -26.40 | 0.00 | mean_delay_incl_depart_s, spillback_duration_s | PASS |
| emergency-5601c3 | cov 1, end 4500 | 30 | 45.46 | 41.24 | -9.3 % | -0.06 [-0.29, 0.17] | -3.13 | 0.00 | mean_delay_s, mean_delay_incl_depart_s, queue_p95_veh | PASS |
| off_peak-5601c3 | cov 1, end 4500 | 30 | 22.32 | 22.37 | 0.2 % | 0.00 [-0.00, 0.01] | – | – | – | PASS |
| road_closure-5601c3 | cov 1, end 5400 | 30 | 115.66 | 115.07 | -0.5 % | -1.18 [-1.89, -0.46] | – | – | mean_delay_incl_depart_s | PASS |
| rush_hour-5601c3 | cov 1, end 4500 | 30 | 41.58 | 41.21 | -0.9 % | -0.01 [-0.13, 0.11] | – | – | – | PASS |
| sinkhole_cross-5601c3 | cov 1, end 4500 | 30 | 119.71 | 118.07 | -1.4 % | -0.68 [-1.70, 0.35] | – | – | – | PASS |
| special_event-5601c3 | cov 1, end 4500 | 30 | 81.35 | 73.61 | -9.5 % | -0.91 [-1.22, -0.61] | – | – | mean_delay_s, mean_delay_incl_depart_s, spillback_duration_s, queue_p95_veh | PASS |

Scenario names with a `-<hash>` suffix carry scenario parameters (e.g. demand_scale); see experiment.json.
