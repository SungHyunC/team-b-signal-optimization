# Lesson 1 — reproducible statistical validation (30 paired seeds)

## Prerequisites
Install the repository dependencies, SUMO and TraCI on the execution host. Confirm:
```bash
sumo --version
python -c "import traci, sumolib; print('SUMO Python modules ready')"
python -m pytest tests/test_experiment_accuracy.py tests/test_validation_audit.py -q
```

## Design
- Scenarios: `rush_hour`, `emergency`, `road_closure`.
- Controllers: `fixed_time` (baseline) and `max_pressure`.
- Paired seeds: 1–30 per scenario and controller, total 180 planned runs.
- Keep the same SUMO build, network, traffic demand model, seed, sampling, probe coverage, and preemption setting within each comparison.
- Use the scenario's full default duration. Flood recovery must be observed after reopening; do not truncate it at 2700 seconds.
- Run on an unchanged commit. Do not mix output directories from different revisions.

## Run
```bash
python -m teamb.experiments run --name lesson1_validation \
  --scenarios rush_hour,emergency,road_closure \
  --controllers fixed_time,max_pressure \
  --seeds 1-30 --workers 2 --strict-validation
```
Output: `results/experiments/lesson1_validation/report.json`, `report.md`,
`summary.csv`, and `validation.json`. The quality gate exits nonzero on invalid
or missing results. An interrupted run can be resumed using the same command;
use a new experiment name after changing the code, SUMO or network.

## Accuracy and precision review
1. **Internal validity**: check `validation.json` says `complete: true`;
   verify all 180 planned runs are valid and no software/network versions are mixed.
2. **Pairing**: compare the same seed and exactly matching scenario, coverage,
   sampling, preemption and controller configuration. Never interpret a fallback
   comparison across different conditions as a controlled paired result.
3. **Outcomes**: inspect mean delay, 95th percentile travel time, unfinished
   vehicles, queues, spillback, and emergency vehicle travel times.
4. **Uncertainty**: use paired differences and 95% confidence intervals, and
   adjust multiple comparisons where appropriate. Report the number of usable
   pairs; 30 planned seeds does not guarantee 30 valid pairs.
5. **Precision**: define a practical improvement threshold before inspecting
   results (for example, a team-approved number of seconds per vehicle).
   If the 95% confidence interval is too wide to distinguish that threshold,
   increase the seed count using an unchanged experimental design.
6. **Realism**: the traffic-demand profiles and closure diversion assumptions
   are scenario assumptions, not measured local traffic data. Compare traffic
   counts, turning proportions, speed distributions, queue lengths and travel
   times against independent observations before claiming real-world calibration.
7. **Sensitivity**: repeat experiments at demand scales 0.75, 1.0 and 1.25
   (separate experiment names). Compare the direction and magnitude of effects.
   Examine the effect of the assumed 30% flood diversion rate; it is not an
   empirically validated constant.
8. **External validity**: four-intersection simulation results cannot alone
   establish citywide safety, emissions or emergency-response benefits.

## Presentation note
"We used 30 matched traffic seeds for each controller in three scenarios,
audited the completeness and provenance of every run, and reported paired
uncertainty rather than a single best-case percentage. The simulated demand
and diversion rates remain assumptions until calibrated to field data."

**Do not quote numerical improvements until the SUMO runs and quality gate pass.**
