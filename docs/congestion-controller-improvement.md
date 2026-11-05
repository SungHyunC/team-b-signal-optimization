# Congestion Controller Improvement — Pilot

**Status:** Experimental, not approved for deployment. Existing `max_pressure` remains unchanged.

## Diagnosis motivating the experiment

In the validated 125%-demand road-closure experiment, max-pressure reduced unfinished vehicles from 14.54% to 8.16% but mean delay decreased only 1.8% (the 95% paired interval includes zero). Confirmed spillback *increased* from 136.33 s to 309.00 s, especially on `N3_J3` and `N4_J4`. Spillback is an observed association, not a proven cause.

## Hypothesis

The existing controller penalizes downstream *stopped queues* but may still move vehicles toward crowded links during heavy detours. Test a separate `max_pressure_spillback` controller that, only when a downstream stopped queue reaches six vehicles, uses `1.5 * max(downstream queue, downstream detector count)` as the downstream pressure penalty. Below the threshold it uses the existing rule. This is a provisional heuristic, not a tuned or statistically validated setting. Moving vehicles contribute to detector count, so the new penalty could worsen performance or induce inefficiency.

## Pilot experiment

- Heavy road closure, 125% demand: 3 controllers (`fixed_time`, `max_pressure`, `max_pressure_spillback`), seeds 1–3, **9 runs**.
- Nominal rush hour, 100% demand: original and experimental max-pressure, seeds 1–3, **6 regression runs**.
- Exact seeds, full default scenario durations, same SUMO environment and strict run validation.
- Unit tests check threshold behavior, missing measurements, and parameter guards. Existing SUMO controller tests check safety interactions.
- Record mean completed-trip delay **alongside** unfinished share, throughput, queue p95, confirmed spillback duration, and controller failures/fallbacks. The pilot's three seeds are an integration and directional screen, **not** sufficient for a statistical superiority claim.
- Compare the variant against the original controller on matched seeds. Improvement on delay must not be purchased by sharply increased unfinished share, safety failures, or worsened spillback; no single metric suffices.
- If the pilot fails tests or substantially worsens multiple key outcomes, stop and investigate rather than advance.
- If promising, predeclare decision criteria and perform a 30-seed independent replication including road closure (75%, 100%, 125%), rush hour, and emergency scenarios; check emergency vehicle travel time and safety outcomes.

## Commands

```bash
python -m pytest tests/test_spillback_aware.py tests/test_controllers.py -q
python -m teamb.experiments run --name congestion_pilot_heavy --scenarios road_closure --controllers fixed_time,max_pressure,max_pressure_spillback --seeds 1-3 --workers 2 --scenario-params '{"demand_scale":1.25}' --strict-validation
python -m teamb.experiments run --name congestion_pilot_nominal --scenarios rush_hour --controllers max_pressure,max_pressure_spillback --seeds 1-3 --workers 2 --strict-validation
```

See the GitHub Actions workflow `.github/workflows/congestion-controller-pilot.yml`. Never change the original baseline outputs or merge into `main` as part of the pilot.
