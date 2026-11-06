# Regression screen: `rl` (rl (new default)) vs `max_pressure`

Experiment `final_d125` · verdict **FAIL** · rules: delay regression ≤ +5.0 %, unfinished share ≤ +0.5 pp and not significantly above +0.1 pp, EV travel time not significantly above +1 s and no more EVs left unarrived on any seed, no safety events, every candidate run finished, at least 2 paired seeds per condition. Paired 95 % t-intervals, not adjusted for the number of conditions.

| Scenario | Demand / params | Seeds | Baseline delay | Candidate delay | Change | Unfinished Δ pp [95 % CI] | EV Δ s | EVs not arrived Δ | Benefits | Result |
|---|---|---:|---:|---:|---:|---|---:|---:|---|---|
| earthquake-5601c3 | cov 1, end 4500 | 30 | 247.20 | 411.77 | 66.6 % | 9.34 [7.60, 11.07] | 167.30 | 0.40 | – | FAIL: delay, throughput, emergency |
| emergency-5601c3 | cov 1, end 4500 | 30 | 45.46 | 43.90 | -3.4 % | 0.01 [-0.11, 0.14] | -1.68 | 0.00 | – | PASS |
| off_peak-5601c3 | cov 1, end 4500 | 30 | 22.32 | 19.92 | -10.8 % | -0.15 [-0.23, -0.06] | – | – | mean_delay_s, mean_delay_incl_depart_s, queue_p95_veh | PASS |
| road_closure-5601c3 | cov 1, end 5400 | 30 | 115.66 | 136.10 | 17.7 % | -2.40 [-3.01, -1.78] | – | – | mean_delay_incl_depart_s | FAIL: delay |
| rush_hour-5601c3 | cov 1, end 4500 | 30 | 41.58 | 42.59 | 2.4 % | 0.01 [-0.10, 0.13] | – | – | – | PASS |
| sinkhole_cross-5601c3 | cov 1, end 4500 | 30 | 119.71 | 122.50 | 2.3 % | -2.29 [-3.21, -1.37] | – | – | mean_delay_incl_depart_s | PASS |
| special_event-5601c3 | cov 1, end 4500 | 30 | 81.35 | 60.60 | -25.5 % | -0.09 [-0.41, 0.22] | – | – | mean_delay_s, mean_delay_incl_depart_s, spillback_duration_s, queue_p95_veh | PASS |

Scenario names with a `-<hash>` suffix carry scenario parameters (e.g. demand_scale); see experiment.json.
