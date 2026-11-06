# Regression screen: `rl` (rl (new default)) vs `max_pressure`

Experiment `final_d10` · verdict **FAIL** · rules: delay regression ≤ +5.0 %, unfinished share ≤ +0.5 pp and not significantly above +0.1 pp, EV travel time not significantly above +1 s and no more EVs left unarrived on any seed, no safety events, every candidate run finished, at least 2 paired seeds per condition. Paired 95 % t-intervals, not adjusted for the number of conditions.

| Scenario | Demand / params | Seeds | Baseline delay | Candidate delay | Change | Unfinished Δ pp [95 % CI] | EV Δ s | EVs not arrived Δ | Benefits | Result |
|---|---|---:|---:|---:|---:|---|---:|---:|---|---|
| earthquake-c2b747 | cov 1, end 4500 | 30 | 227.50 | 281.80 | 23.9 % | 0.02 [-0.63, 0.67] | 70.72 | 0.03 | – | FAIL: delay, emergency |
| emergency-c2b747 | cov 1, end 4500 | 30 | 29.64 | 29.99 | 1.2 % | -0.01 [-0.06, 0.05] | 1.24 | 0.00 | – | PASS |
| off_peak-c2b747 | cov 1, end 4500 | 30 | 22.42 | 18.29 | -18.4 % | -0.09 [-0.18, -0.01] | – | – | mean_delay_s, mean_delay_incl_depart_s | PASS |
| road_closure-c2b747 | cov 1, end 5400 | 30 | 88.42 | 87.25 | -1.3 % | -0.01 [-0.07, 0.05] | – | – | – | PASS |
| rush_hour-c2b747 | cov 1, end 4500 | 30 | 29.33 | 29.33 | 0.0 % | -0.01 [-0.06, 0.05] | – | – | – | PASS |
| sinkhole_cross-c2b747 | cov 1, end 4500 | 30 | 47.98 | 40.63 | -15.3 % | -0.05 [-0.15, 0.06] | – | – | mean_delay_s, mean_delay_incl_depart_s, queue_p95_veh | PASS |
| special_event-c2b747 | cov 1, end 4500 | 30 | 52.84 | 50.59 | -4.3 % | 0.36 [0.20, 0.51] | – | – | mean_delay_s, queue_p95_veh | FAIL: throughput |

Scenario names with a `-<hash>` suffix carry scenario parameters (e.g. demand_scale); see experiment.json.
