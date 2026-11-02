# Data & evaluation — sensors, metrics, experiments

Owner: **Doyoung Lee** (big data & evaluation). Code: `teamb/sensors/`, `teamb/evaluation/`,
`teamb/experiments/`. Tests: `tests/test_data.py` (~30 s).

This is a working first version, built so the team can run it, find what is wrong and improve
it before the final presentation (Nov 5, 2026). Every number in this document can be
reproduced with the commands shown. Nothing is field-calibrated: the corridor, demand and
sensor models are design assumptions.

## Quick start

```bash
python -m teamb run --scenario rush_hour --controller fixed_time --end 1500       # one run
python -m teamb.experiments run --name sample --scenarios rush_hour,emergency \
    --controllers fixed_time,coordinated,actuated,max_pressure --seeds 1-3 --end 2700 --workers 2
python -m teamb.experiments report --name sample --copy-to docs/results/sample-report.md
python -m pytest tests/test_data.py
```

Outputs: `results/runs/<run_id>/` and `results/experiments/<name>/` (layout in
[`results/README.md`](../../results/README.md)). Committed sample: [`docs/results/sample-report.md`](../results/sample-report.md).

## What is where

| File | What it does |
|---|---|
| `sensors/feed.py` | one shared set of TraCI **subscriptions** per run (vehicles, E2/E1 detectors, lane permissions); a 5-s snapshot of positions and time loss |
| `sensors/sampling.py` | who is a probe (`uniform`, `approach_biased`, `speed_biased`) and when a probe reports |
| `sensors/crosscheck.py` | fake-data defense: probe reports vs loop detectors → `trusted`, alerts |
| `sensors/logs.py` | rolling counts, estimation log and detector-interval tables (evaluation only) |
| `sensors/suite.py` | `SensorSuite`: builds the observation every simulated second |
| `evaluation/metrics.py` | `MetricsCollector`: live KPIs for the twin, end-of-run summary, extra run files |
| `evaluation/spillback.py` | spillback with upstream-blocking evidence |
| `evaluation/recovery.py` | recovery time and excess delay after a closure / attack |
| `evaluation/estimation.py` | MAE / RMSE / bias of probe, detector and fused estimates vs ground truth |
| `evaluation/stats.py` | t table, confidence intervals, paired differences, p-values, Holm correction (no scipy) |
| `experiments/runner.py` | the run matrix, parallel worker processes, resume / skip |
| `experiments/analysis.py` | `summary.csv`, paired analysis, `report.json` (twin schema), `report.md` |

```
SUMO ──subscriptions──► feed ──► SensorSuite.observe ──observation──► controller      (no ground truth)
                          │            └─ estimation log (estimate + ground truth) ──┐
                          └────► MetricsCollector (5-s samples) ──► finalize ◄─ tripinfo.xml
                                                                       └─► summary.json + timeseries.csv,
                                                                           estimation.csv, detector_intervals.csv,
                                                                           evaluation.json
experiments.runner: matrix ──► worker processes ──► SimEnv(...).run() ──► runs/  ──► analysis ──► report
```

### Why the feed (per-step cost)

Every TraCI getter is a round trip to SUMO (~30–70 µs). The first sensor version made about
400 per simulated second: `observe()` took 43 ms/step against 1.6 ms for SUMO itself
(measured on the team laptop under load). With subscriptions `observe()` takes ~0.3–1 ms and
makes no round trips; the metrics add ~1 ms (one snapshot every 5 s). The observation values
are identical to the first version (checked step by step over 240 s with `actuated` and
`max_pressure_probe`, whose closed loop would diverge on any difference). The feed is attached
to the connection (`conn._teamb_feed`), so the metrics can read the sensors' logs without any
change to `SimEnv`. Flows and loop counts are counted in `on_step` (every second), so they stay
right when a caller observes less often (`controllers/fast_env.TrainEnv`).

## Sensors

### Observation (contract in `ARCHITECTURE.md`; fields only added, never renamed)

Per approach (side the traffic comes from) of every signalized junction:

| Block | Field | Unit | Meaning |
|---|---|---|---|
| `detector` | `queue` | veh | E2 halting vehicles (< 1.39 m/s) in the last 100 m before the stop line |
| | `count` | veh | vehicles in the E2 zone |
| | `occupancy` | % | E2 occupancy, mean over lanes |
| | `speed` | m/s | E2 mean speed, mean over lanes (0 if empty) |
| | `flow_vph` | veh/h | E1 loop (25 m before the stop line) counts over the last 5 min |
| | `gap_s` | s | time since any loop of the approach last saw a vehicle |
| `probe` | `queue_est` | veh | halted probe reports ÷ coverage |
| | `n`, `halted` | reports | probe reports this second (incl. fake ones), of which halted (< 0.1 m/s) |
| | `speed` | m/s | mean reported speed; `null` = no report this second |
| | `flow_est_vph` | veh/h | probes that crossed the stop line in the last 5 min ÷ coverage |
| | `trusted` | bool | `false` = the cross-check flagged the probe data |
| | `queue_est_adj` | veh | halted reports ÷ `penetration_est` (new) |
| | `penetration_est` | 0–1 | probe crossings ÷ loop counts over 15 min, shrunk toward the coverage while counts are small (new) |
| `fused` | `queue`, `flow_vph`, `source` | veh, veh/h | detector queue; when the detector zone is full **and** probes are trusted, max(detector, `queue_est_adj`) (new) |
| `oracle` | `queue`, `count` | veh | ground truth, **only** for `observation_source == "oracle"` |

### Sampling mechanisms (`--sampling` / `SimEnv(sampling=...)`)

Selection is per trip (a driver shares data for the whole trip or not at all).

| Mechanism | Model | What it should do to the estimates |
|---|---|---|
| `uniform` | P(probe) = coverage c | unbiased, noisy at low c |
| `approach_biased[:r]` | arterial-entry drivers are r× (default 2) as likely to share as cross-street drivers; per-group p_g = min(1, k·w_g) with Σ s_g·p_g = c (k by bisection, shares s_g estimated online) | overall share ≈ c, arterial queues overestimated, cross-street queues underestimated |
| `speed_biased[:p]` | probes chosen like `uniform`; a stopped phone reports in a given second with probability p (default 0.3), a moving one always | queues underestimated at every coverage; the penetration fix cannot correct it (penetration is measured on moving vehicles) |

Measured (rush hour, fixed-time, seed 1, 900–1800 s; `estimation.csv`): queue bias (estimate −
truth, veh per approach) — uniform ≈ 0 at every coverage; approach-biased +1.2 on arterial and
−0.2 on cross-street approaches at 10–50 %; speed-biased ≈ −1.8 at every coverage (−3.1 arterial).
The penetration-adjusted estimate removes most of the approach bias at 25–50 % (0.52 → 0.25 and
0.49 → 0.12), not at 10 % (the penetration estimate is too noisy there), and not the stopped-phone bias.

### Fake-data cross-check (`crosscheck.py`)

For one approach and second: H = halted probe reports (raw, not scaled), Q_det = E2 halting
count, p = estimated penetration, C_zone = E2 length / 7 m per lane, C_lane = Σ lane length / 7 m.
Suspicious if

1. **storage** H > C_lane + 2 — more stopped phones than cars fit on the road;
2. **detector** (zone not full) H > Q_det + max(3, 0.25·Q_det) — probes are a subset of the cars;
3. **statistical** (zone not full) H > p·Q_det + 3.5·√(p(1−p)·Q_det) + 2 — H would be Binomial(Q_det, p).

"Zone full" (occupancy ≥ 40 % or Q ≥ 0.7·C_zone on a lane) means the queue may extend beyond the
detector, so only test 1 applies — and it stays so for 60 s after the zone was last full: at
green the front of a long queue (inside the zone) moves off first while its tail beyond the zone
still stands, and the start-up wave (~5 m/s) needs up to a minute to reach the end of a 290 m
approach. Without that memory the first version raised 10–30 s false alarms after long queues at
100 % coverage (found in the sample experiment). Hysteresis: untrusted after 3 suspicious seconds
in a row, trusted again after 10 clean seconds. Alerts carry `test`, `probe_halted` and `since`.
Validation: 0 false-alarm seconds in 12 clean 1800-s runs (10/25/50/100 % × 3 sampling
mechanisms) and in the 24 runs of the sample experiment; the 99-phone attack on J2 N is flagged
2 s after it starts at 10 % and 25 % coverage (storage test). A small attack (a few phones) on an
approach whose detector zone was full in the last minute is only caught by the storage test, i.e.
not at all — a known gap (TODO).

## Data dictionary

Time is simulation time in seconds (1-s steps). Samples every 5 s (`timeseries.csv`,
`estimation.csv`); detector intervals 60 s. Empty CSV cell / JSON `null` = "not defined" (e.g.
no finished EV, one seed only), never zero. Vehicle ids are synthetic SUMO ids (`f<flow>_<n>`,
`ambulance_<n>`); no personal data is produced. Results are regenerated, not archived (`results/`
is gitignored); a run is identified by `run_id` (single runs) or the run name (experiments).

### Vehicle events — `trips.csv` (one row per trip, from SUMO tripinfo)

| Column | Unit | Meaning / null |
|---|---|---|
| `id`, `vtype` | – | vehicle id; type `car`, `truck`, `bus`, `ambulance`, `firetruck` |
| `depart`, `arrival` | s | departure; arrival (−1 = still in the network at the end) |
| `finished` | bool | arrived before the end |
| `duration` | s | travel time (for unfinished: time in the network so far) |
| `time_loss` | s | SUMO timeLoss: time lost against driving at the maximum possible speed |
| `stops` | count | times the vehicle stopped (SUMO waitingCount) |
| `route_length` | m | |
| `depart_delay` | s | waited before it could enter the network (insertion backlog) |
| `waiting_time` | s | time at speed < 0.1 m/s |
| `depart_edge`, `arrival_edge` | – | first / last edge (`arrival_edge` empty if unfinished) |
| `origin` | – | `arterial` (entered on W0_J1 / E5_J4) or `cross` |
| `movement` | – | `arterial_through`, `cross_through`, `turning`, `unknown` (unfinished) |

The role plan's per-second vehicle-event schema (`run_id, sim_time_s, vehicle_id_pseudonym,
lane_id, position_m, speed_mps, route_id, observed_flag`) is **not written yet** (data volume:
~200 vehicles × 3600 s ≈ 0.7 M rows/h); the feed already holds lane and speed every second and
position every 5 s, so it is a small addition (TODO below).

### Detector intervals — `detector_intervals.csv`

`detector_id` (e2_<lane>; the loop on the same lane is e1_<lane>), `lane_id`, `start_s`, `end_s`
(60-s intervals, end exclusive), `count` (E1 vehicles), `flow_vph` (count × 3600 / interval),
`occupancy_pct` (mean E2), `speed_mps` (vehicle-weighted mean E2 speed; empty = no vehicle),
`halting_mean` (mean E2 halting), `missing_flag` (always 0: simulated detectors do not fail yet),
`latency_s` (0 in simulation).

### Signal events — `signal_events.csv` (written by the env)

`t`, `junction`, `requested` (axis asked for), `executed` (signal state shown: EW_G, EW_Y, EW_AR,
NS_G, ...), `reason` (`switch`, `yellow_done`, `all_red_done`, `preempt`, `rejected`, `timeout`,
`controller_error`), `detail`. A phase's start is the row that executes it; its end is the next
executed row of the same junction (`phase_start_s`, `phase_end_s` of the role plan).

### Scenario metadata — `manifest.json` → `config`

`seed` (demand seed), `scenario` (scenario id), `flows` (OD demand levels and vehicle mix; turning
ratios follow from the OD flows), `events` (incidents: closures, EV dispatches, attacks),
`coverage` (penetration), `sampling` (mechanism), `ev_preemption`, `warmup`, `end_time`, plus
code revision, SUMO version and network/demand hashes. Weather is not modelled.

### Sensor estimates vs ground truth — `estimation.csv` (evaluation only)

`t, junction, approach, kind (arterial/cross), attacked (0/1), trusted (0/1), n_reports,
true_queue, true_count, true_flow_vph, det_queue, det_flow_vph, probe_queue_est,
probe_queue_adj, probe_flow_est_vph, fused_queue, penetration_est`. Ground truth: halted
(< 0.1 m/s) and all vehicles on the whole approach; flow = vehicles that crossed the stop line in
the last 5 min.

### Time series — `timeseries.csv`

`t, in_window, vehicles, halting, mean_speed (m/s), delay_rate (veh·s lost per s), current_mean_delay
(s, mean time loss so far of vehicles in the network), max_queue (veh), queue_warning (0/1),
spillback_links (count), closed_edges, attack_active, untrusted_approaches, probes`.

## Metric formulas (`summary.json`)

Measurement population: trips that **depart** in [warmup, end). Baseline keys are unchanged.

| Key | Formula / meaning |
|---|---|
| `mean_delay_s` | **primary endpoint**: mean time_loss of finished trips |
| `mean_travel_time_s`, `p95_travel_time_s` | mean / 95th percentile (linear interpolation) of duration, finished trips |
| `stops_per_veh` | mean stops of finished trips |
| `throughput_veh_h` | completed × 3600 / (end − warmup) |
| `completed`, `unfinished`, `unfinished_pct` | PERF-01: unfinished = in network at end + never inserted; pct = 100·unfinished / (completed + unfinished) |
| `planned_in_window`, `inserted_in_window`, `in_network_at_end`, `never_inserted` | flow conservation: completed + unfinished = max(planned, inserted) |
| `mean_delay_incl_unfinished_s` | mean time_loss of all inserted trips (unfinished counted with their delay so far — a lower bound); compare with `mean_delay_s` to see selection bias |
| `mean_depart_delay_s`, `teleports` | insertion delay; SUMO teleports (stuck > 300 s) in the window |
| `arterial_mean_delay_s`, `cross_mean_delay_s` (+ `_p95_`) | delay by origin; `delay_by_origin` has n, mean, p95, travel time, stops |
| `mean_queue_veh`, `max_queue_veh`, `queue_p95_veh` (+ `_arterial_`, `_cross_`) | halted vehicles per approach, 5-s samples in the window |
| `spillback_samples`, `queue_warning_s` | queue-occupancy **warning** only: samples (s) with an approach at ≥ 90 % of storage (halted × 7 m ≥ 0.9 × lane length × lanes) |
| `spillback_duration_s`, `spillback_link_s`, `spillback_events`, `spillback_by_link` | **spillback with evidence**: link entrance blocked (slow car within 15 m of the start, ≥ 50 % of storage slow) AND a feeder's front car stopped at its stop line with a non-red link into that link, in 2 consecutive samples; network seconds / link-seconds / episodes |
| `ev_count`, `ev_mean_travel_time_s`, `ev_mean_delay_s`, `ev_unfinished`, `ev_trips` | emergency vehicles in the window |
| `others_mean_delay_s` | mean delay of finished non-EV trips — compare preemption on vs off on the same seeds |
| `ev_extra_delay_others_s` | within-run indication: Σ_g n_near,g·(delay_near,g − delay_far,g) / Σ_g n_near,g over movements g; "near" = in the network during an EV trip (+30 s); trips of the last 5 min excluded |
| `disruptions`, `recovery_time_s`, `recovery_censored`, `excess_delay_veh_h` | see below |
| `est_queue_mae/_rmse/_bias`, `est_queue_adj_*`, `det_queue_*`, `fused_queue_mae`, `est_flow_*`, `est_queue_bias_arterial/_cross` | estimation error, est − truth over approach × 5-s samples, attacked approaches excluded: MAE = mean│e│, RMSE = √mean e², bias = mean e |
| `alert_episodes`, `alert_s`, `false_alarm_s`, `attacks`, `attack_detected`, `detection_delay_s` | cross-check performance; an alert is true if it overlaps an attack on the same approach (+30 s grace) |
| `probe_share`, `probe_share_arterial`, `probe_share_cross` | realized share of probes among departed vehicles |

Spillback check in practice: in `rush_hour`, `emergency` and a `road_closure` run with 1.25×
demand it stays 0 — the longest queue (76 cars) is on the network entry `W0_J1`, which has no
upstream junction and shows up as insertion backlog (`never_inserted`) instead; inner links peak
at ~32 of ~81 places. In `earthquake` (J3–J4 closed both ways, fixed-time, 2100 s) the back-street
detour fills `N4_J4` and `N3_N4` and blocks the junctions upstream: 115 s, 8 episodes.

**Recovery** (`recovery.py`). Indicator: delay rate r(t) = Σ_vehicles Δtime_loss / Δt over the
5-s sample (seconds of delay the network loses per second). L_pre = mean r over the 10 min before
the event. Smoothed r_s = centered 90-s moving average (one cycle). Recovered at the first
t ≥ event end from which r_s ≤ 1.1·L_pre + 1 for 2 min; `recovery_time_s` = that t − event end;
censored (null) if never before the run ends. Excess delay = ∫ max(0, r − L_pre) dt from the event
start to recovery (or run end), in vehicle-hours. Events come from the feed (closures from lane
permissions, attacks from the sensors).

Because demand follows a time-of-day profile, the pre-event level can be out of reach after the
event even when traffic is fine. Experiments therefore offer `--counterfactual`: every scenario
with events is also run without them (same seed and controller), and the report adds recovery
*vs no event* — normal when r_s(t) ≤ 1.1·r_s,no-event(t) + 1 at the same clock time, and excess
delay against that twin. Checked on `road_closure` (seed 1): with the default end (1200 s after the
reopening) both fixed-time and actuated are censored — 20 min after reopening the network still
holds 2–2.6× the vehicles of its twin (backlog and detour queues draining). Run to 6300 s
(`--end 6300 --scenario-params '{"duration": 6300}'`): actuated recovers 990 s after the reopening
(995 s vs its twin, 59 extra veh·h); fixed-time has not recovered 3000 s later (71 extra veh·h).

## Experiment design

- **Matched demand seeds** (REP-01): seed s gives the same vehicles for every controller, so
  controllers are compared seed by seed. Probe selection uses its own random stream (same probes
  for uniform and speed-biased at a given seed).
- **Pairing**: candidate (scenario, controller, coverage, sampling, preemption) vs the baseline
  controller (default `fixed_time`) with the same scenario and preemption, the same coverage/sampling
  if run, otherwise any (fixed-time ignores sensor data). Only seeds present in both count.
- **Statistics** (`stats.py`): per seed d_i = candidate − baseline and imp_i = 100·(b_i − c_i)/b_i
  (seeds with b_i ≤ 0 skipped); mean ± t_{0.975,n−1}·s/√n; two-sided paired t-test; Holm
  correction within a scenario. `report.json` → `delta_vs_baseline_pct` = mean imp (positive = better).
- **How many seeds**: n ≈ (t·s_d / E)², with s_d the SD of the paired differences from a pilot and
  E the CI half-width you need. The sample report gives s_d per row (`ci95` × √n / t).
- **Train / tune / holdout**: keep seeds used to train RL or tune the AI recommender (e.g. 1–10)
  apart from the reporting seeds (e.g. 101–120) and freeze the holdout scenarios before choosing
  the final controller (checkpoint 3).
- **Selection bias**: always read `unfinished_pct`, `never_inserted` and
  `mean_delay_incl_unfinished_s` next to `mean_delay_s`; a short run end favours short trips among
  the finished ones (the default run is 900 s warm-up + 3600 s).
- **Compute cost**: `report.json → compute` has wall time per run and per controller, ms per
  simulated second, simulation speed-up and MB written; use those (not guesses) for the Databricks
  discussion.

## How to run experiments

```bash
# matrix: scenarios × controllers × seeds × coverages × sampling × preemption (all comma lists)
python -m teamb.experiments run --name NAME --scenarios rush_hour,emergency \
    --controllers fixed_time,coordinated --seeds 1-20 --coverages default --sampling uniform \
    --ev-preemption on --end 4500 --workers 2
python -m teamb.experiments run ... --dry-run          # list the runs only
python -m teamb.experiments report --name NAME --baseline coordinated
python -m teamb.experiments list
```

- Any registered controller works (`python -m teamb list`); `--controller-params` passes JSON to
  every controller, or per controller: `'{"coordinated": {"split": 0.65}}'`. Runs with parameters
  get a `-<hash>` suffix. `--scenario-params '{"demand_scale": 1.2}'` the same for scenarios.
- Finished runs are skipped, so you can add controllers or seeds to an experiment later and re-run
  the report; `--force` re-runs. A failing run writes `error.json` and the rest continues.
- Coverage sweep: run the baseline once (`--coverages 1.0`), then the probe-based controller with
  `--coverages 10,25,50,75,100 --sampling uniform,approach_biased,speed_biased` into the same
  `--name`; the report adds the coverage-sweep and estimation tables.
- Clean EV comparison: `--ev-preemption on,off` adds the paired "on − off" columns.
- Recovery under time-varying demand: `--counterfactual` adds a no-event twin for every scenario
  with events; for closures that reopen late, also extend the run (`--end 6300 --scenario-params
  '{"duration": 6300}'`).
- Each worker is one SUMO process; keep `--workers` ≤ the number of free CPU cores.

## Sample results

[`docs/results/sample-report.md`](../results/sample-report.md): rush hour and emergency,
fixed-time / coordinated / actuated / max-pressure, seeds 1–3, runs to 2700 s (30-min
measurement window), 24 runs in 8.6 min with 2 workers (~15 ms per simulated second under heavy
machine load). Mean delay, paired improvement vs fixed-time (mean ± 95 % CI over 3 seeds):

| | fixed-time | coordinated | actuated | max-pressure |
|---|---|---|---|---|
| rush hour, delay s/veh | 71.0 ± 10.5 | 48.4 ± 2.2 (−31.8 ± 8.4 %) | 30.7 ± 5.0 (−56.7 ± 6.7 %) | 29.2 ± 2.9 (−58.7 ± 9.9 %) |
| emergency, delay s/veh | 72.1 ± 5.8 | 48.7 ± 2.5 (−32.5 ± 8.0 %) | 30.9 ± 4.7 (−57.2 ± 8.5 %) | 29.8 ± 1.8 (−58.7 ± 4.2 %) |
| emergency, EV travel time s | 110.3 ± 7.6 | 91.7 ± 13.3 | 95.1 ± 4.2 | 90.6 ± 6.5 |
| unfinished % (rush hour) | 10.3 | 8.3 | 7.2 | 6.9 |

All Holm-corrected paired p ≤ 0.011; no spillback; 0 false-alarm seconds. Coordination mainly
helps the arterial (arterial delay 107 → 60 s) while cross-street delay rises slightly (30 → 35 s);
the adaptive controllers bring arterial delay to ~30 s without raising cross-street delay. With 3
seeds and 30-min windows these are pilot numbers. The SD of the paired differences is 2.5–5.4
s/veh (s_d = ci95·√n / t₂), so n ≈ (t·s_d / E)² gives intervals of about ±2–4 s with 10 seeds and
±1.2–2.5 s with 20 seeds (the plan).

[`docs/results/coverage-sweep-report.md`](../results/coverage-sweep-report.md): the probe-based
`max_pressure_probe` at 10/25/50/100 % coverage × the three sampling mechanisms (rush hour, seed 1,
1800 s) — the sampling-bias pipeline end to end; one seed, so trends only. In closed loop the
errors feed back: with uniform sampling the queue bias is −0.86 veh at 10 %, −0.18 at 50 %, 0 at
100 % (the controller neglects queues it cannot see, so they grow); approach-biased sampling
starves the under-sampled cross streets (cross-street bias −2.9 / −3.1 veh at 25 / 50 %, delay
62 s vs 38 s with uniform sampling); the stopped-phone bias stays ≈ −1.5 veh at every coverage.
Compare the open-loop numbers above (fixed-time does not react to the estimates).

## Known limitations

- E2 "queue" counts vehicles < 1.39 m/s, ground truth uses < 0.1 m/s; detector bias is therefore
  slightly positive for short queues and negative for queues longer than 100 m.
- Probe reports have no position noise, latency, or map-matching errors; a silent phone simply
  disappears for that second (no "last known position" cache).
- `ev_extra_delay_others_s` is a within-run heuristic; use the paired preemption on/off experiment.
- Spillback evidence is sampled every 5 s; very short blockages are missed by design (2 samples).
- Recovery uses network-wide delay rate; a local disruption in a large network would be diluted.
  The pre-event rule ignores time-of-day demand (use `--counterfactual`), and `road_closure` as
  defined ends only 1200 s after the reopening — too early to see recovery.
- Detectors never fail (`missing_flag` = 0); the cross-check assumes the loops are honest.
- The sample report has 3 seeds and 30-min measurement windows: wide intervals, not a final result.

## TODO for Doyoung

1. **20-seed primary comparison** on the holdout seeds (e.g. 101–120), full 4500-s runs, all
   controllers: `--seeds 101-120 --end 4500`; report the paired CI table in Report 3.
2. **Coverage sweep chart** (estimation error and delay vs coverage, per sampling mechanism) from
   `summary.csv` / `estimation.csv` — a notebook in `notebooks/` reading `results/experiments/*/summary.csv`
   with pandas; one chart per mechanism.
3. **Probe trace** (vehicle-event table of the role plan) as an option, with pseudonymized ids
   (salted hash per run) — measure MB per simulated hour; this is the Databricks volume question.
4. **Databricks visit (Nov 4) questions**: cost of map-matching / geospatial joins for city-wide
   probe data (H3 / Delta); streaming vs micro-batch for 1-s probe feeds; MLOps for the RL model
   (MLflow registry, drift monitoring when penetration changes); retention and privacy of probe
   trajectories; what they measure before claiming cloud cost savings.
5. **Detector failures and latency**: random `missing_flag` intervals and report delays; check the
   controllers and the cross-check still behave (`detector_intervals.csv` is ready for it).
6. **Arrivals on green** (coordination quality) from E1 loop crossings and the signal state.
7. **Evidence register**: Boston / Jeju / Busan figures with source, baseline, sample, metric
   definition, confounders (role plan); keep our simulated results clearly separate from them.
8. **Checkpoint 2/3**: freeze the holdout scenarios and seeds with the team before the final runs.
9. **Disaster recovery table** for the presentation: `road_closure`, `sinkhole_cross`, `earthquake`
   × all controllers × 10 seeds with `--counterfactual --end 6300 --scenario-params '{"duration": 6300}'`;
   ask Aditya whether the scenarios should simply run longer after the reopening.
10. **Small attacks**: a few fake phones on an approach whose detector zone was full in the last
    minute are not caught (only the storage test applies there); try a test on the probe *count*
    against the E1 loop flow, and add replay / stale-timestamp attacks with Yunseong.
11. **Closed-loop sampling bias** (coverage sweep): with few or biased probes, `max_pressure_probe`
    neglects the queues it cannot see, so the bias grows in closed loop — repeat with 10 seeds and
    show it next to the open-loop (fixed-time) errors.
