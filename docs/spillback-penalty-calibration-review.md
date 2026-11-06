# Spillback Penalty Calibration — Results and Decision

**Status:** Small-seed calibration review completed. Candidate for confirmatory testing identified; **not** validated or approved for deployment.

## Evidence

- [Successful calibration workflow #41968041524](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968041524) ([committed data](results/studies/calibration-24/README.md))
- [Prior high-demand controller pilot #41959366607](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41959366607)
- Experimental design: [spillback-penalty-calibration.md](https://github.com/SungHyunC/team-b-signal-optimization/blob/77ca85d/docs/spillback-penalty-calibration.md) (on the research commit 77ca85d; the experimental controller is not on `main`)

All **24/24** calibration runs passed strict validation, grouped into four six-run matrices. Tests, prior-pilot diagnostic extraction, and artifact upload succeeded. The data are based on **three new paired seeds (4–6)** for each experiment, so all performance comparisons are exploratory.

## Heavy 125%-demand road closure

| Metric (mean over seeds 4–6) | Original max-pressure | Penalty 1.10, threshold 8 | Penalty 1.25, threshold 8 |
|---|---:|---:|---:|
| Completed-trip mean delay (s/veh) | 132.070 | 117.660 | **105.483** |
| Unfinished vehicles (%) | 8.827 | 8.920 | **7.907** |
| Completed trips (vehicles/run) | 4426.333 | 4420.000 | **4471.667** |
| Confirmed network spillback (s) | 531.667 | 211.667 | **56.667** |
| Queue p95 (vehicles) | 16.333 | 15.667 | **15.333** |

Compared with the original, the 1.25 setting reduces mean completed-trip delay by **26.587 s/veh (20.1% of the original mean)**, reduces unfinished share by **0.920 percentage points**, increases completed trips by **45.334 (1.02%)**, and reduces mean spillback by **475 s (89.3%)**. These percentages are ratios of three-seed group means, **not** confidence bounds.

The 1.10 setting lowers delay and spillback but slightly worsens completion metrics. The 1.25 setting is the only one that meets all the prespecified *directional* heavy-closure thresholds in this small sample.

## Nominal rush-hour regression

| Metric (mean over seeds 4–6) | Original max-pressure | Penalty 1.10, threshold 8 | Penalty 1.25, threshold 8 |
|---|---:|---:|---:|
| Completed-trip mean delay (s/veh) | 29.837 | 29.453 | **29.403** |
| Unfinished vehicles (%) | **2.657** | 2.697 | 2.697 |
| Completed trips (vehicles/run) | **3332.667** | 3331.333 | 3331.333 |
| Confirmed network spillback (s) | 0 | 0 | 0 |
| Queue p95 (vehicles) | 3.333 | 3.333 | 3.333 |

Neither experimental setting exceeds the prespecified 5%-delay regression guardrail. The differences are small and not proof of equivalence or superiority.

## Prior-pilot phase switching diagnostic

A separate read-only diagnosis of seeds 1–3 analyzed event counts and congestion before, during and after closure. The previously unsuccessful stronger penalty (threshold 6, multiplier 1.50) had **zero recorded controller errors, fallback steps and rejected actions**, but completed far fewer vehicles than original max-pressure. During the closure, mean signal-switch events per run were ~293 (original) vs ~288 (strong penalty); max stopped queue across junctions was ~15.6 vs ~19.8 vehicles. After reopening, mean maximum queue was ~19.2 vs ~28.9 vehicles.

These observations suggest the original strong penalty's throughput loss cannot be explained simply by a dramatic increase in signal-switch frequency. They do **not** prove a causal mechanism. Switching aggregates are not a complete safety or network-flow analysis.

## Decision and next validation gate

- **Advance penalty multiplier 1.25 with downstream queue threshold 8 to a pre-registered 30-seed confirmatory simulation**, compared directly with the original max-pressure controller.
- Retain penalty 1.10 and previous penalty 1.50 as exploratory comparisons only; do not select either.
- Confirmatory evaluation should include 125%-demand road closure as primary, plus normal rush hour and emergency scenarios at nominal and higher demand to detect regressions, and the 75% road closure to check for over-restriction.
- Hold parameters fixed during confirmation and use matched paired seeds, one code revision and SUMO version, strict audits, confidence intervals, throughput and unfinished vehicles, link-level spillback, emergency travel time and fallback/rejection/error counts.
- Explicitly assess both a **material mean delay improvement** and absence of worsening completion/unfinished share; do not approve based on reduced spillback alone.
- Three-seed calibration was used to choose parameters. For more defensible confirmation, use new independent seeds not used in tuning (e.g. 31–60) rather than relying only on seed sets 1–6.
- **No controller code changes or merge into `main` are authorized by the calibration result.** The original max-pressure controller remains the validated reference.

## Limits

Simulation demand, network and diversion assumptions are synthetic and not field calibrated. The 24-run strict audit assures run integrity, **not** a guarantee of traffic safety or a statistically significant improvement. The calibration's log-based metrics did not independently expose every new run's fallback and rejected-action count; inspect these per-run summaries in the confirmatory quality gate.
