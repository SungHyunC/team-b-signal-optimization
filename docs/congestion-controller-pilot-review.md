# Congestion Controller Improvement — Pilot Review

**Disposition:** Integration pilot completed; experimental spillback-aware variant **not approved** for a larger confirmatory matrix in its current form.

## Evidence

- [GitHub Actions run #41959366607](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41959366607)
- Original controller: `max_pressure`; experimental variant: `max_pressure_spillback`.
- 9 road-closure runs at 125% demand: fixed-time, original, and variant × seeds 1–3.
- 6 normal rush-hour runs at 100% demand: original and variant × seeds 1–3.
- Both experiment matrices passed strict validation (9/9 and 6/6); controller tests and artifact upload passed.

## Results

| Heavy road closure (125%) | Fixed-time | Original max-pressure | Spillback-aware variant |
|---|---:|---:|---:|
| Completed-trip mean delay (s/veh) | 126.4 | 115.2 | 112.6 |
| Unfinished vehicles (%) | 14.5 | **6.6** | 11.7 |
| Completed trips, mean per run | 4,131 | **4,512** | 4,264 |
| 95th-percentile queue (veh) | 25.7 | **15.0** | 18.0 |
| Confirmed spillback duration (s) | 210 | 138 | **77** |
| 95th-percentile travel time (s) | 646.1 | 568.0 | 565.7 |

| Normal rush hour (100%) | Original max-pressure | Spillback-aware variant |
|---|---:|---:|
| Completed-trip mean delay (s/veh) | **29.4** | 31.2 |
| Unfinished vehicles (%) | **2.3** | 2.4 |
| 95th-percentile travel time (s) | **166.7** | 173.0 |

Values are the rounded figures emitted in the job's report.md, **three random seeds per group**. The normal-rush-hour comparison report has no fixed-time baseline and therefore contains no paired superiority test for the two max-pressure variants. Three seeds are insufficient for a reliable superiority claim; treat all changes as exploratory.

## Engineering interpretation

The heuristic discourages green into downstream queues above the threshold (six stopped vehicles with 1.5x downstream penalty). At 125% demand under road closure, it coincides with lower measured spillback, but also reduces trip completion and worsens unfinished percentage and queue p95 relative to the existing max-pressure controller. This tradeoff fails the pilot's requirement not to trade off broad network service for one improved metric.

A plausible concern is that overly strong downstream penalties starve upstream throughput; this **remains a hypothesis** until time-series, link movement, and switching evidence is examined. We should not claim the root cause is proven.

## Decision

- **Keep** the original `max_pressure` as the validated controller.
- **Keep** `max_pressure_spillback` isolated as an experimental implementation only; do not deploy or merge it into `main`.
- **Do not** launch the full 30-seed confirmatory experiment for this parameterization.
- **Next:** inspect switching events, bottleneck-edge occupancy, queue and arrival time series during the 125% road closure; consider testing milder penalties (or capacity-aware constraints) as a **new small-screen pilot** with a prespecified minimum completed-trip and safety threshold.
- Do not label a reduction in completed-trip mean delay as a win if it is accompanied by a substantial increase in unfinished vehicles.

## Safety and scope

All tests and run audits completed, but this does not independently prove all possible real-world safety outcomes. Network, traffic demand, and flood diversion assumptions remain synthetic.
