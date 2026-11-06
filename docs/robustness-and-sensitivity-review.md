# Robustness and Sensitivity Testing — Engineering Review

**Status:** Simulation sensitivity review completed; strong performance is **not** established for every scenario. This review does not approve real-world deployment or a controller algorithm change.

**Evidence**
- [Nominal 100% demand: 180-run validation](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41929708299) ([committed data](results/studies/baseline-180/README.md))
- [75% and 125% demand: 360-run validation](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41946810451) ([committed data](results/studies/robustness-360/README.md))
- [Read-only paired diagnostic analysis](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41958378469) ([committed data](results/studies/congestion-diagnosis/README.md))

## Experimental design and audit

Three scenarios (`rush_hour`, `emergency`, `road_closure`), two controllers (`fixed_time`, `max_pressure`), and thirty paired seeds (1–30) per demand level. The nominal 100% experiment (180 runs) and 75%/125% experiments (180 each) yielded **540/540 full-matrix valid runs**, zero failures. The additional 12-run low/high pilot passed, bringing the total to 552 completed pilot + full-matrix runs, excluding smoke tests.

Both sensitivity matrices passed the strict per-run provenance audit. The read-only diagnostic found **no within-pair code revision, SUMO version, network hash, seed, or demand hash mismatches**. GitHub job logs identify SUMO **1.28.0** for both nominal and sensitivity workflows. Nominal and sensitivity experiments have different commit SHAs; compare within-condition controller pairs, and treat across-experiment trends as descriptive rather than formal tests of interaction. The dependency spec allowed future SUMO updates at the time, so version pinning was desirable for further comparisons; SUMO, traci and sumolib are now pinned to 1.28.0 in `pyproject.toml` and `requirements.txt`.

## Primary outcome — mean delay

Mean SUMO timeLoss for trips departing within the measurement window and **finishing** before simulation end. Lower is better. Percentage reduction below is the reduction between controller group means, not the mean of per-seed percentage reductions. Paired differences and approximate 95% t confidence intervals refer to **fixed-time minus max-pressure** in seconds/vehicle; positive is better for max-pressure.

| Demand | Scenario | Fixed-time mean (s) | Max-pressure mean (s) | Reduction | Paired benefit (s), 95% CI |
|---|---|---:|---:|---:|---|
| 75% | Rush hour | 61.81 | 25.04 | 59.5% | 36.77 [36.13, 37.41] |
| 75% | Emergency | 60.66 | 25.37 | 58.2% | 35.29 [34.64, 35.95] |
| 75% | Road closure | 106.05 | 45.88 | 56.7% | 60.17 [58.50, 61.83] |
| 100% | Rush hour | 83.95 | 29.41 | 65.0% | 54.54 [50.18, 58.90] |
| 100% | Emergency | 89.47 | 30.08 | 66.4% | 59.39 [54.95, 63.83] |
| 100% | Road closure | 119.83 | 93.00 | 22.4% | 26.84 [23.18, 30.49] |
| 125% | Rush hour | 107.58 | 42.56 | 60.4% | 65.02 [62.85, 67.20] |
| 125% | Emergency | 107.38 | 44.65 | 58.4% | 62.73 [60.10, 65.35] |
| 125% | Road closure | 126.02 | 123.77 | **1.8%** | **2.25 [-3.14, 7.65]** |

Values at 75% and 125% are from full-precision summary means displayed to four decimals by the diagnostics, rounded here; nominal values and intervals are reconstructed from two-decimal per-run execution logs. These are **unadjusted** intervals for nine comparisons. No claim of family-wise multiple-comparison significance is made here.

**Conclusion:** The mean-delay advantage is consistent across all tested rush-hour and emergency conditions and low/nominal road-closure demand. Under a road closure at 125% demand, the paired interval spans zero. The review **cannot establish a reliable mean-delay benefit in that condition**.

## Secondary outcomes and selection bias

The primary metric includes only completed trips and must be read alongside completion, never-inserted vehicles, queue occupancy, and spillback.

| Demand | Scenario | Unfinished % fixed / max | Queue p95 fixed / max (veh) | Confirmed spillback fixed / max (s) |
|---|---|---|---|---|
| 75% | Rush hour | 3.38 / 2.58 | 11.00 / 2.04 | 0 / 0 |
| 75% | Emergency | 3.37 / 2.61 | 10.47 / 2.23 | 0 / 0 |
| 75% | Road closure | 2.98 / 2.35 | 13.94 / 3.67 | 7.67 / 0.33 |
| 125% | Rush hour | 12.26 / 2.68 | 26.84 / 6.07 | 0 / 0 |
| 125% | Emergency | 11.77 / 2.68 | 26.34 / 6.43 | 0.67 / 0 |
| 125% | Road closure | **14.54 / 8.16** | **25.83 / 15.70** | **136.33 / 309.00** |

For the **125% road closure**, max-pressure completes ~307 more vehicles per seed (4,424 vs 4,118), increases throughput from ~3,294 to ~3,539 veh/h, and reduces unfinished share by **6.38 percentage points** (paired 95% CI for candidate-minus-baseline: [-7.24, -5.52] pp). However, confirmed spillback is **172.67 s longer on average** (paired 95% CI [84.05, 261.29] s). The difference in a secondary delay measure that includes *inserted but unfinished* vehicles is -1.87 s for max-pressure minus fixed-time, with paired 95% CI [-7.61, 3.87], also inconclusive. **This auxiliary metric does not account for never-inserted vehicles as complete trips**, and must not be described as a full-population delay estimate.

Observed spillback hotspots at 125% road closure (mean seconds per run, fixed / max-pressure):
- `N3_J3`: 94.00 / 145.83
- `N4_J4`: 30.33 / 68.50
- `J1_J2`: 3.17 / 37.67
- `N2_J2`: 2.33 / 29.67
- `N2_N3`: 4.50 / 22.67

These are observed link-level spillback locations, **not a demonstrated causal mechanism**. A controller that moves more vehicles through a congested corridor may generate more downstream blocking; time-series and signal-phase analysis is needed to establish why.

## Emergency vehicles

Emergency-vehicle travel times were measured for the `emergency` scenario (not inferred from general-traffic delay):
- **75% demand:** fixed 109.58 s; max-pressure 94.98 s; paired improvement 14.60 s, approximate 95% CI [13.70, 15.51] s.
- **125% demand:** fixed 133.88 s; max-pressure 111.32 s; paired improvement 22.56 s, approximate 95% CI [18.36, 26.76] s.
- **100% demand:** not extracted from the nominal experiment's detailed results for this review; do not substitute old three-seed pilot figures.

Road-closure scenarios contain no measured emergency-vehicle observations for this metric; a claim about ambulance travel during road closures requires a separate combined scenario.

## Methodological caveats

1. The four-intersection network, demand profiles, and assumed flood diversion are synthetic and **not field-calibrated**; no real-world effect size or citywide benefit is established.
2. Strong performance in six rush-hour/emergency demand combinations does not imply unconditional robustness. Heavy road closure is a documented performance boundary.
3. Confidence intervals describe repeatability across these **30 simulated random seeds**, not uncertainty from model structure, network calibration, or geography.
4. This review summarizes per-run outputs and automated diagnostic comparisons. It does not independently inspect every raw vehicle trajectory, signal decision, or time-series anomaly.
5. The existing normal-demand 180-run experiment is from an earlier Git commit than the sensitivity runs, although their logs show the same SUMO major/minor version. Exact software/build consistency should be locked for future experiments.

## Review acceptance and handoff

- [x] At least 30 matched seeds per controller/scenario/demand level
- [x] Complete strict provenance/metric audits (540/540 full runs)
- [x] Matched-demand diagnostics found no within-pair provenance mismatch
- [x] Paired delay uncertainty summarized, including an inconclusive interval
- [x] Unfinished-trip, throughput, queue, and spillback tradeoffs assessed
- [x] Emergency-vehicle outcomes examined for light and heavy demand
- [x] Limitations and exceptional heavy-closure case explicitly documented
- [ ] Field calibration and independent real-world evidence (out of scope for simulation sensitivity closure)
- [ ] Confirm baseline fair comparisons against additional adaptive controllers (future benchmarking)
- [ ] Establish mechanisms for excess downstream spillback (next investigation)
- [ ] Verify normal-demand 30-seed emergency-vehicle metric from full artifact (recommended reporting enhancement)

**Disposition:** **Sensitivity review completed with a documented exception**, not “controller robust under all tested conditions.” The next development checkpoint may investigate the heavy-demand road closure, but should not overwrite the validated baseline or deploy a new signal policy without paired regression and safety checks.
