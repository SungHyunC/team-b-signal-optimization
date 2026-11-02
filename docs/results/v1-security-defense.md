# Experiment report: `v1-security-defense`

Created 2026-11-02T01:25:18 · baseline **fixed_time** · code `c0cbfb9` · SUMO 1.28.0

Matrix: scenarios fake_data_attack · controllers max_pressure_probe-584350 · seeds [1, 2, 3] · coverage 0.25 · sampling uniform · EV preemption on · warm-up 900 s · run end  s

Controller parameters: `max_pressure_probe-584350` = `{"defense": true}`

Reproduce:

```bash
python -m teamb.experiments run --name v1-security-defense --scenarios fake_data_attack --controllers max_pressure_probe --coverages 25 --seeds 1-3 --workers 3 --controller-params '{"max_pressure_probe": {"defense": true}}'
```

**How to read this.** Delay = mean SUMO time loss of trips that start after the warm-up and finish (s/veh, lower is better). `a ± b` = mean over seeds ± half-width of the 95 % t-interval. **Δ vs baseline** = paired improvement on the same demand seeds, 100 × (baseline − candidate) / baseline: positive means less delay than the baseline. p = paired t-test, Holm-corrected within a scenario. Unfinished % must be read next to delay (PERF-01): a controller that keeps cars out of the network can look fast.

## Scenario `fake_data_attack`

| controller | cov | sampling | EV pre | n | delay s | Δ vs base | diff s | p (Holm) | p95 TT s | stops/veh | unfinished | arterial delay | cross delay | queue p95 | spillback s | EV TT s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| max_pressure_probe-584350 | 0.25 | uniform | on | 3 | 48.2 ± 12.7 | – | – | – | 217.7 ± 56.4 | 1.48 ± 0.53 | 2.7 ± 0.3% | 35.5 ± 6.4 | 63.9 ± 20.5 | 7.3 ± 1.4 | 20 ± 86 | – |

## Sensor estimation accuracy (all runs pooled)

Errors per approach and 5-s sample against SUMO ground truth (evaluation only; controllers never see it). Detector = E2 zone (last 100 m), so it misses queues longer than that.

| sampling | coverage | runs | probe share | queue MAE | queue bias | bias arterial | bias cross | adj. bias | detector MAE | fused MAE | flow MAE | false alarm s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 0.25 | 3 | 0.262 ± 0.010 | 1.14 ± 0.21 | -0.26 ± 0.05 | -0.14 ± 0.16 | -0.39 ± 0.21 | -0.20 ± 0.10 | 0.24 ± 0.12 | 0.31 ± 0.14 | 112 ± 18 | 0 ± 0 |

## Fake-data attack and the cross-check

| scenario | controller | cov | sampling | n | detected | detection delay s | alert s | false alarm s | delay s |
|---|---|---|---|---|---|---|---|---|---|
| fake_data_attack | max_pressure_probe-584350 | 0.25 | uniform | 3 | 100% | 2.0 ± 0.0 | 1807 ± 0 | 0 ± 0 | 48.2 ± 12.7 |

## Recovery after disruptions

Recovery = time after the event ends until the network delay rate stays within 10 % (+1 veh) of its pre-event level for 2 min. Censored = not recovered before the run ended. Demand follows a time-of-day profile, so the pre-event level can be out of reach; the *vs no event* columns compare with the same seed and controller run without the event (`--counterfactual`) at the same clock time.

| scenario | controller | cov | n | recovery s (pre-event) | censored | excess veh·h | recovery s (vs no event) | censored | excess vs no event veh·h | spillback s |
|---|---|---|---|---|---|---|---|---|---|---|
| fake_data_attack | max_pressure_probe-584350 | 0.25 | 3 | 653 ± 193 | 0 | 13.02 ± 11.84 | – | – | – | 20 ± 86 |

## PERF-01: completed and unfinished trips

| scenario | controller | cov | sampling | EV pre | n | completed | unfinished | unfinished % | never inserted | teleports | delay incl. unfinished s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fake_data_attack | max_pressure_probe-584350 | 0.25 | uniform | on | 3 | 3250 ± 91 | 89 ± 10 | 2.7 ± 0.3 | 0 ± 1 | 0.0 ± 0.0 | 47.6 ± 12.1 |

## Compute cost

3 runs ok, 0 failed · experiment wall time 13.1 s with [3] worker(s) · sum of run wall times 38.4 s · 351.7× faster than real time per run · data 11.2 MB (3.75 MB/run, 3.0 MB per simulated hour).

| controller | mean wall per run s | ms per simulated second |
|---|---|---|
| max_pressure_probe-584350 | 12.8 | 2.58 |

## Caveats

- Simulation of a synthetic 4-junction corridor with provisional (not field-calibrated) parameters; numbers show relative differences between controllers under the same demand, not real-world effects.
- Few seeds give wide intervals; the role plan targets ≥ 20 paired seeds for the primary comparison.
- A short run end (< 900 s warm-up + 3600 s) measures fewer trips and favours short trips among the finished ones; compare unfinished % across controllers.
