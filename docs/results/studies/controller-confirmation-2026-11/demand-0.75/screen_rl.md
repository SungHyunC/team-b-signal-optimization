# Regression screen: `rl` (rl (new default)) vs `max_pressure`

Experiment `final_d075` · verdict **FAIL** · rules: delay regression ≤ +5.0 %, unfinished share ≤ +0.5 pp and not significantly above +0.1 pp, EV travel time not significantly above +1 s and no more EVs left unarrived on any seed, no safety events, every candidate run finished, at least 2 paired seeds per condition. Paired 95 % t-intervals, not adjusted for the number of conditions.

| Scenario | Demand / params | Seeds | Baseline delay | Candidate delay | Change | Unfinished Δ pp [95 % CI] | EV Δ s | EVs not arrived Δ | Benefits | Result |
|---|---|---:|---:|---:|---:|---|---:|---:|---|---|
| earthquake-193e6a | cov 1, end 4500 | 30 | 109.10 | 90.08 | -17.4 % | -0.01 [-0.08, 0.05] | -9.58 | 0.00 | mean_delay_s, mean_delay_incl_depart_s, spillback_duration_s, queue_p95_veh | PASS |
| emergency-193e6a | cov 1, end 4500 | 30 | 25.40 | 25.14 | -1.0 % | -0.00 [-0.04, 0.04] | 0.02 | 0.00 | mean_delay_s, mean_delay_incl_depart_s, queue_p95_veh | PASS |
| off_peak-193e6a | cov 1, end 4500 | 30 | 23.16 | 15.94 | -31.2 % | -0.23 [-0.31, -0.14] | – | – | mean_delay_s, mean_delay_incl_depart_s | PASS |
| road_closure-193e6a | cov 1, end 5400 | 30 | 46.09 | 51.29 | 11.3 % | -0.04 [-0.08, 0.01] | – | – | – | FAIL: delay |
| rush_hour-193e6a | cov 1, end 4500 | 30 | 25.04 | 24.85 | -0.8 % | 0.05 [-0.01, 0.10] | – | – | – | PASS |
| sinkhole_cross-193e6a | cov 1, end 4500 | 30 | 28.66 | 28.27 | -1.3 % | -0.02 [-0.08, 0.04] | – | – | mean_delay_s, mean_delay_incl_depart_s, queue_p95_veh | PASS |
| special_event-193e6a | cov 1, end 4500 | 30 | 27.19 | 30.71 | 12.9 % | 0.03 [-0.03, 0.10] | – | – | – | FAIL: delay |

Scenario names with a `-<hash>` suffix carry scenario parameters (e.g. demand_scale); see experiment.json.
