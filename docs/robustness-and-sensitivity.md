# Robustness and Sensitivity Testing

## Objective
Test whether the previously observed advantage of max-pressure over fixed-time control persists under changed traffic demand. These are simulated scenarios, not calibrated field conditions.

## Existing reference
The completed 180-run experiment used rush_hour, emergency, and road_closure with paired seeds 1–30, baseline demand, and full default scenario duration. Keep those results as the nominal-demand reference, but do not pool raw metrics from different code/SUMO revisions without checking provenance.

## Design
- Scenarios: rush_hour, emergency, road_closure.
- Controllers: fixed_time and max_pressure.
- Demand scales: 0.75, 1.00 (existing nominal reference), 1.25.
- Seeds: 1–30 for each scenario/controller/scale in the full study.
- Extra runs required: 3 scenarios × 2 controllers × 2 new demand scales × 30 seeds = **360 runs**.
- The two new demand scales get distinct experiment names and strict audits.
- A small pilot (seed 1 per condition, 12 runs) first checks generation, SUMO execution, and strict validation. Pilot results are not statistical proof.
- Use identical seed and demand model within each controller pair, and inspect corresponding demand hashes. Variants at different scales are not paired to each other for controller-effect estimation.
- Do not report one overall percentage without reporting each scenario and scale.

## Primary checks
1. Mean delay in s/vehicle for completed trips, paired max-pressure minus fixed-time with 95% CI.
2. Percentage unfinished, completion/throughput, p95 travel time, queue p95, and spillback: ensure the apparent delay gain is not caused by excluding vehicles that fail to complete.
3. For emergency, inspect emergency-vehicle travel time as a separate operational endpoint; mean traffic delay is not a proxy for first-responder benefit.
4. For road closure, inspect recovery and diversion assumptions independently; the assumed diversion is not calibrated local evidence.
5. Define the practically important threshold before interpreting full-matrix confidence intervals. Report all seed counts and CI widths.

## Pilot commands
```bash
python -m teamb.experiments run --name robustness_pilot_low --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1 --workers 2 --scenario-params '{"demand_scale":0.75}' --strict-validation
python -m teamb.experiments run --name robustness_pilot_high --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1 --workers 2 --scenario-params '{"demand_scale":1.25}' --strict-validation
```

## Full-matrix commands (after pilot review)
```bash
python -m teamb.experiments run --name robustness_low --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1-30 --workers 2 --scenario-params '{"demand_scale":0.75}' --strict-validation
python -m teamb.experiments run --name robustness_high --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1-30 --workers 2 --scenario-params '{"demand_scale":1.25}' --strict-validation
```

## Approval gate
Pilot must pass strict validation and show no model/configuration errors before the full 360-run stage. The full stage requires complete run audits, paired statistical reports, and a check for baseline fairness and unfinished-trip bias. No real-world generalization until field calibration.
