# Spillback Penalty Calibration — Experimental Gate

**Status:** Small-screen experiment started; do **not** select a winner or merge before actual results are reviewed.

## Motivation
The first spillback-aware variant (threshold 6 stopped vehicles, multiplier 1.5) reduced mean confirmed spillback in a three-seed 125%-demand road-closure pilot, but increased unfinished vehicles from 6.6% to 11.7%, with fewer completed trips and a normal-rush-hour delay regression. It failed the holistic pilot decision gate.

## Diagnostics before calibration
Read the previous pilot's `timeseries.csv` and `signal_events.csv` over three defined time windows:
- Before closure: [900,1500) simulated seconds
- During closure: [1500,3300)
- After reopening: [3300,end)
Report switching events, halting vehicles, maximum queues, network delay rate, and confirmed spillback samples by controller. These aggregates cannot prove why bottlenecks form; they support a targeted interpretation.

## Prespecified calibration screen

Use **new seeds 4–6** for both the 125%-demand road closure and the nominal rush-hour regression. Compare each candidate to the **original max-pressure controller on the same seed and scenario**. Two experimental parameter sets:
- Mild: downstream queue threshold 8, multiplier 1.10
- Moderate: downstream queue threshold 8, multiplier 1.25

24 total runs (two settings × two scenarios × two controllers × three seeds). A repeated original baseline run in the two settings is intentional for independent audit of each experiment.

**Directional screen, not proof of superiority:**
1. Strict audit completes; no controller errors, safety-supervisor rejected actions, or fallback regression.
2. At heavy road closure, do not accept a candidate with >1 percentage-point increase in average unfinished vehicles compared with original, or >1% decline in average completed trips. Keep both comparisons visible even if its mean delay improves.
3. Look for a reduction in confirmed spillback **without** deterioration in mean delay, queue p95, and throughput.
4. On nominal rush hour, do not accept a >5% increase in mean delay relative to the paired original baseline.
5. Treat any results on three seeds as exploratory, even if every threshold is met. No full 30-seed test automatically starts; review evidence and precommit an independent replication before selecting a winner.
6. If neither passes, retain original max-pressure, report the failed hypothesis, and return to queue/storage-aware control design.

Code, fixed-time controller, original max-pressure controller, and prior full 540-run evidence remain unchanged. The work is confined to `feature/validation-sandbox-explainability`.

[Calibration GitHub Actions workflow](../.github/workflows/spillback-penalty-calibration.yml)
