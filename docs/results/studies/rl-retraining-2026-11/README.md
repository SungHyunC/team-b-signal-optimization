# RL retraining, November 2026

The first RL model (60 episodes × 1,800 s, rush hour only) was the team's lesson that a policy
trained on one situation breaks in another: in the flood it was about twice as slow as
max-pressure. This study trained it on far more and far more varied traffic, on Modal
(`teamb train-rl --backend modal`), and picked a model on held-out seeds.

## Training (13,600 episodes in total)

| Model | Features | Episodes | Scenarios | Demand | Wall time on Modal |
|---|---|---:|---|---|---:|
| rl v1 features | v1 | 2000 | 7 scenarios | 0.75-1.25 | 35.4 min |
| **rl (new default)** | v2 | 2000 | 7 scenarios | 0.75-1.25 | 35.5 min |
| rl v2 fine-tuned | v2 | 5840 (2,000 + 3,840 resumed) | 7 scenarios (weighted) | 0.75-1.4 | 64.8 min |
| rl v2 long | v2 | 5760 | 7 scenarios (weighted) | 0.75-1.4 | 47.5 min |

Every episode is a full-length run of a random scenario at a random demand scale, with seeds
1,000,000+ (never used for evaluation). The fine-tuned model continued the selected model at
demand 0.75-1.4 with earthquake, emergency and flood episodes weighted double; the long run
trained a fresh v2 table on the same mix. Per-round training curves: `curve_<model>.csv`;
hyper-parameters and seed ranges: `meta_<model>.json`.

**Provenance.** The v1 and v2 tables were trained on Modal from commit `ea44faa`, the fine-tuned and
long runs from `f05fee4` (branch improve/unified-project; SUMO 1.28.0, `teamb train-rl --backend
modal --workers 48|96`). The selected table is `models/rl_qtable.json`, SHA-256 `2d1f2c0d104275ee…`.
Validation runs record their code revision in each run's manifest.

## Selection (validation seeds 900-909)

All candidates run with the low-confidence fallback (`fallback_min_visits` 20) unless named
"original". Lower is better.

### Validation, demand 1 (seeds 900-909, mean delay s/veh ± 95 % CI)

| Scenario | max_pressure | rl (first model, original) | rl (first model + fallback) | rl v1 features | rl (new default) | rl v2 fine-tuned | rl v2 long |
|---|---:|---:|---:|---:|---:|---:|---:|
| rush_hour | 29.7 ± 0.7 | 31.0 ± 0.8 | 30.8 ± 0.8 | 30.5 ± 0.6 | 29.8 ± 0.6 | 29.5 ± 0.6 | 31.2 ± 0.4 |
| special_event | 53.8 ± 3.7 | 52.7 ± 2.2 | 49.5 ± 2.1 | 50.5 ± 1.9 | 48.9 ± 2.2 | 49.3 ± 1.7 | 48.9 ± 1.8 |
| emergency | 30.0 ± 0.6 | 31.7 ± 0.7 | 31.7 ± 0.8 | 31.0 ± 0.6 | 30.4 ± 0.5 | 29.5 ± 0.7 | 32.2 ± 0.6 |
| road_closure | 88.8 ± 3.0 | 167.3 ± 17.6 | 101.9 ± 6.1 | 94.9 ± 6.2 | 87.7 ± 3.5 | 88.1 ± 6.2 | 84.2 ± 3.4 |
| sinkhole_cross | 52.2 ± 8.9 | 45.6 ± 4.3 | 45.6 ± 4.0 | 40.5 ± 2.5 | 43.0 ± 3.4 | 45.3 ± 5.3 | 42.4 ± 3.3 |
| earthquake | 228.5 ± 23.3 | 336.9 ± 41.3 | 247.4 ± 23.9 | 314.9 ± 55.0 | 282.5 ± 53.0 | 321.1 ± 45.9 | 275.5 ± 37.5 |
| off_peak | 22.3 ± 0.3 | 18.5 ± 0.3 | 18.5 ± 0.3 | 18.3 ± 0.4 | 18.3 ± 0.3 | 18.2 ± 0.3 | 18.6 ± 0.2 |
| **mean change vs max_pressure** | – | **+16.3 %** | **-0.7 %** | **+0.6 %** | **-3.0 %** | **-0.4 %** | **-2.4 %** |

### Validation, demand 1.25 (seeds 900-909, mean delay s/veh ± 95 % CI)

| Scenario | max_pressure | rl (first model, original) | rl (first model + fallback) | rl v1 features | rl (new default) | rl v2 fine-tuned | rl v2 long |
|---|---:|---:|---:|---:|---:|---:|---:|
| rush_hour | 44.1 ± 5.2 | 55.8 ± 6.1 | 56.0 ± 14.0 | 47.7 ± 4.4 | 43.6 ± 4.2 | 52.4 ± 8.3 | 49.3 ± 9.8 |
| special_event | 78.9 ± 7.2 | 64.0 ± 2.2 | 62.9 ± 1.9 | 63.9 ± 4.4 | 61.7 ± 2.9 | 59.1 ± 3.0 | 59.6 ± 1.2 |
| emergency | 45.8 ± 4.3 | 59.8 ± 7.8 | 55.5 ± 12.8 | 52.5 ± 6.6 | 48.2 ± 5.6 | 58.8 ± 8.8 | 51.1 ± 7.5 |
| road_closure | 120.9 ± 6.2 | 200.2 ± 15.0 | 137.2 ± 5.8 | 154.9 ± 9.5 | 133.9 ± 11.6 | 142.5 ± 7.9 | 134.3 ± 4.8 |
| sinkhole_cross | 119.7 ± 8.4 | 142.5 ± 18.1 | 127.3 ± 9.3 | 112.3 ± 15.7 | 121.5 ± 20.6 | 146.4 ± 14.2 | 126.6 ± 17.8 |
| earthquake | 248.5 ± 17.3 | 411.7 ± 26.9 | 298.0 ± 25.2 | 438.7 ± 36.1 | 418.1 ± 46.8 | 436.0 ± 31.4 | 374.3 ± 33.3 |
| off_peak | 22.4 ± 0.5 | 19.6 ± 0.2 | 19.6 ± 0.2 | 20.4 ± 0.2 | 19.9 ± 0.3 | 19.8 ± 0.3 | 20.3 ± 0.3 |
| **mean change vs max_pressure** | – | **+25.1 %** | **+7.9 %** | **+13.4 %** | **+7.4 %** | **+18.0 %** | **+8.2 %** |

**More episodes did not keep helping.** The v2 table after 2,000 episodes was the best on
validation; 3,840 more episodes at higher demand made heavy traffic worse, and a fresh 5,760-episode
run did not beat it. The tabular state (detector counts in buckets, elapsed green, a blocked bit)
is the limit, not the amount of data; the earthquake, with several closures at once, is where it
shows. A function approximator with downstream and closure features (e.g. DQN with SUMO-RL) is
the natural next step.

The selected model is now `models/rl_qtable.json`; the first model stays as
`models/rl_qtable_v1_rush_hour.json`. Final test results on seeds 201-230 are in the
[controller confirmation](../controller-confirmation-2026-11/README.md).
