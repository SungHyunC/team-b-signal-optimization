# Regression screen: `max_pressure-b8251d` (max_pressure + rho 0.25 + closure_aware) vs `max_pressure`

Experiment `final_d075` · verdict **FAIL** · rules: delay regression ≤ +5.0 %, unfinished share ≤ +0.5 pp and not significantly above +0.1 pp, EV travel time not significantly above +1 s and no more EVs left unarrived on any seed, no safety events, every candidate run finished, at least 2 paired seeds per condition. Paired 95 % t-intervals, not adjusted for the number of conditions.

| Scenario | Demand / params | Seeds | Baseline delay | Candidate delay | Change | Unfinished Δ pp [95 % CI] | EV Δ s | EVs not arrived Δ | Benefits | Result |
|---|---|---:|---:|---:|---:|---|---:|---:|---|---|
| earthquake-193e6a | cov 1, end 4500 | 30 | 109.10 | 85.75 | -21.4 % | 0.01 [-0.05, 0.08] | -14.84 | 0.00 | mean_delay_s, mean_delay_incl_depart_s, spillback_duration_s, queue_p95_veh | PASS |
| emergency-193e6a | cov 1, end 4500 | 30 | 25.40 | 25.31 | -0.3 % | 0.02 [-0.02, 0.06] | 0.23 | 0.00 | – | PASS |
| off_peak-193e6a | cov 1, end 4500 | 30 | 23.16 | 23.16 | 0.0 % | 0.00 [0.00, 0.00] | – | – | – | PASS |
| road_closure-193e6a | cov 1, end 5400 | 30 | 46.09 | 51.49 | 11.7 % | -0.02 [-0.06, 0.03] | – | – | – | FAIL: delay |
| rush_hour-193e6a | cov 1, end 4500 | 30 | 25.04 | 24.91 | -0.5 % | 0.07 [0.03, 0.11] | – | – | – | PASS |
| sinkhole_cross-193e6a | cov 1, end 4500 | 30 | 28.66 | 29.26 | 2.1 % | 0.02 [-0.04, 0.08] | – | – | – | PASS |
| special_event-193e6a | cov 1, end 4500 | 30 | 27.19 | 26.94 | -0.9 % | -0.01 [-0.05, 0.03] | – | – | – | PASS |

Scenario names with a `-<hash>` suffix carry scenario parameters (e.g. demand_scale); see experiment.json.
