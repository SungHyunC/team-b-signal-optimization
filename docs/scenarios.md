# Scenario catalog · 시나리오 목록

Owner: Aditya (scenarios & analysis), with Doyoung. Code: `teamb/scenarios/`, `teamb/demand/`.

A scenario is **demand** (origin–destination flows with a time-of-day shape) plus **timed
events** (emergency dispatches, road closures, fake-data attacks). Every controller runs the
*same* scenario with the *same* seed, so differences come from the controller alone.

```bash
python -m teamb list                                              # all scenarios and controllers
python -m teamb run --scenario road_closure --controller fixed_time --end 1800
python -m teamb.experiments run --name cmp --scenarios rush_hour,emergency --controllers fixed_time,max_pressure --seeds 1-5
python -m teamb.analysis.impact results/experiments/cmp           # value of the difference (docs/roles/scenarios-analysis.md)
```

Runs last 4,500 s: a 900 s warm-up, then the 3,600 s measurement window `[900, 4500)`.
Metrics only count trips that depart inside the window, and unfinished trips are always
reported (PERF-01).

## The corridor

```
            NN1      NN2      NN3      NN4            north entries / exits
             |        |        |        |
            N1 ----- N2 ----- N3 ----- N4             back street, 1 lane each way, 30 km/h (detour)
             |        |        |        |
  W0 ====== J1 ===== J2 ===== J3 ===== J4 ====== E5   arterial, 2 lanes each way, 50 km/h
             |        |        |        |
            S1       S2       S3       S4             south entries / exits
```

J1–J4 are signalized (300 m apart), N1–N4 are priority junctions where the cross street has
the right of way over the back street. Cross streets have 1 lane each way at 40 km/h.
The signals have two phases (EW, NS); left turns get a permissive green and there are no
left-turn bays.

## How demand is generated (`teamb/demand/`)

- **Flows** (`routes.Flow`): an entry edge, an exit edge and a rate in veh/h. SUMO picks the
  route when the vehicle departs; for trips it uses live (smoothed) edge travel times, so a few
  drivers take the back street when the arterial is jammed — like a navigation app at departure.
- **Arrivals** are a Poisson process. A flow's rate can follow a **profile**
  (`profiles.py`: `peak`, `pulse`, `dip`, `combine`), sampled by thinning.
- **One random stream per flow**, seeded from `(seed, origin, destination, name)`. The same seed
  always gives the same vehicles (REP-01); adding a flow never changes the others; and two
  scenarios that share a flow share its arrivals (common random numbers → less noisy
  scenario-to-scenario comparisons).
- **Vehicle mix**: `Flow.mix = {"car": 0.96, "truck": 0.04}`; buses run along the arterial.
- **Named movements** (`corridor.CorridorDemand`): through traffic, right turns from the
  arterial, and right/left turns from the cross streets at every junction; per-junction
  cross-street volumes. Arterial left turns are off by default (no bays → a waiting left-turner
  would block a through lane; a network limitation).
- `demand_scale` scales every flow: `get_scenario("rush_hour", demand_scale=1.2)` or
  `SimEnv(..., scenario_params={"demand_scale": 1.2})` — the light / near-capacity / oversaturated
  levels of the research report's factorial design (§8.2).

### Rush-hour demand (peak hour, veh/h) — `presets.RUSH_HOUR`

| Movement | J1 | J2 | J3 | J4 |
|---|---:|---:|---:|---:|
| Eastbound through (W0 → E5) | 1,200 (4 % trucks) | | | |
| Westbound through (E5 → W0) | 550 (4 % trucks) | | | |
| Buses each way along the arterial | 4 | | | |
| Cross street through, each direction | 110 | 200 | 170 | 110 |
| Eastbound right (W → S) | 35 | 35 | 35 | 35 |
| Westbound right (E → N) | 25 | 25 | 25 | 25 |
| Northbound right onto EB (S → E) | 40 | 40 | 40 | 40 |
| Southbound right onto WB (N → W) | 30 | 30 | 30 | 30 |
| Northbound left onto WB (S → W) | 15 | 15 | 15 | 15 |
| Southbound left onto EB (N → E) | 20 | 20 | 20 | 20 |

Time-of-day shape `RUSH_PROFILE` (multiplier of the peak): 0.80 at t = 0 → 0.85 at 900 s
(end of warm-up) → ramp up to 1.0 at 1,800 s → **25-minute peak** to 3,300 s → ramp down to
0.75 at 4,500 s. About 3,400 trips depart in the measurement window.

Volume / capacity at the peak, for the 90 s fixed-time baseline (50/50 split, 40 s green per
axis, ≈ 820 veh/h per lane):

| Approach | J1 | J2 | J3 | J4 |
|---|---:|---:|---:|---:|
| West (eastbound arterial, 2 lanes) | 1,344 · 0.82 | 1,369 · 0.83 | 1,394 · 0.85 | 1,419 · 0.87 |
| East (westbound arterial, 2 lanes) | 714 · 0.44 | 694 · 0.42 | 674 · 0.41 | 654 · 0.40 |
| North / South (1 lane) | 160 · 0.20 | 250 · 0.30 | 220 · 0.27 | 160 · 0.20 |

**Tuning check** (peak demand held for 25 min, seed 1, 1,800 s runs): fixed-time 90 s →
mean delay 90.5 s/veh, 2.1 stops/veh, longest queue 57 vehicles on J1's west approach (≈ 70 %
of its storage), **0 teleports, no insertion backlog** — congested but never gridlocked.
The same demand with a 62/38 split gives 53.6 s and coordinated control 49.4 s, so a
controller that re-balances green time has real room to win.

### Other presets

| Preset | Used by | Eastbound / westbound through | Cross streets (each way) | Notes |
|---|---|---|---|---|
| `OFF_PEAK` | off_peak | 300 / 260 | 35 · 60 · 50 · 35 | flat, 10 % trucks; every approach v/c ≤ 0.22 |
| `EVENING` | special_event | 800 / 750 | 90 · 150 · 130 · 90 | flat, balanced |

## The scenarios

| Name | Title · 제목 | Category | What it tests | Demand | Events | Read first |
|---|---|---|---|---|---|---|
| `rush_hour` | Baseline · Rush hour · 출퇴근 혼잡 | baseline | delay, stops and queues in normal peak traffic | rush hour | – | `mean_delay_s`, `stops_per_veh`, `p95_travel_time_s`, `unfinished_pct`, `max_queue_veh`, `spillback_samples` |
| `off_peak` | Night · Light traffic · 야간 한산 | demand | green time wasted at empty junctions (actuated should shine) | off-peak | – | `mean_delay_s`, `stops_per_veh` |
| `special_event` | Stadium lets out · 경기 종료 퇴장 | demand | a surge of ~680 veh/h on one cross street (J3 north) | evening + stadium pulse 1,500–3,600 s | – | `mean_delay_s`, `max_queue_veh`, `spillback_samples`, `unfinished_pct` |
| `emergency` | Emergency vehicle priority · 응급차량 우선 | emergency | EV travel time with preemption, cost to others | rush hour | 10 EVs, 1,200–3,900 s, every side | `ev_mean_travel_time_s`, `preemptions`, `mean_delay_s` |
| `road_closure` | Flood road closure · 침수 도로 폐쇄 | disaster | how far / long congestion spreads, recovery | rush hour, 30 % of EB through diverts during the closure | close J2→J3 1,500 s, reopen 3,300 s | `unfinished_pct`, `mean_delay_s`, `max_queue_veh`, `spillback_samples`, `recovery_time_s` |
| `sinkhole_cross` | Sinkhole on a cross street · 싱크홀 | disaster | spillover when a cross street is cut | rush hour | close J2↔N2 1,500 s, reopen 3,300 s | `mean_delay_s`, `max_queue_veh`, `spillback_samples` |
| `earthquake` | Earthquake · 지진 다중 통제 | disaster | EVs on detours, several closures at once, recovery | rush hour × 0.75 | close J3↔J4 and J1↔N1 at 1,200 s; 7 EVs; reopen 3,000 / 3,600 s | `ev_mean_travel_time_s`, `unfinished_pct`, `throughput_veh_h` |
| `fake_data_attack` | Fake navigation data · 가짜 내비 데이터 | security | does fake probe data fool a controller; is it caught | rush hour, coverage 25 % | 99 phantom cars on J2 north, 1,500–3,300 s | `mean_delay_s`, `rejected_actions`, alerts |

### Details

**rush_hour.** The reference condition. Compare every controller here first.

**off_peak.** Night traffic: a fixed 90 s cycle still makes drivers wait up to ~45 s at an
empty junction. Detector-actuated control should cut delay and stops the most; it is also the
largest block of hours in the cost-benefit annualization.

**special_event.** A stadium garage north of J3 exits onto the cross street between N3 and J3,
so all ~680 veh/h must clear J3's north approach (35 % straight south, 35 % right → west, 30 %
left → east). At the peak that approach is at v/c ≈ 1.04 with a 50/50 split: a controller has
to move green from the arterial to J3's NS phase. Cars wait in the garage when the street is
full (counted as unfinished trips if they never get out).

**emergency.** Ten EVs, one every 300 s from 1,200 s: eastbound and westbound along the whole
arterial, southbound and northbound along cross streets, right turns onto the arterial from
both sides, a westbound left turn across eastbound traffic, a northbound left turn. Run each
controller with and without preemption (`--no-preemption`, or `ev_preemption=False`) — the
impact analysis then prints the preemption effect.

**road_closure.** A flash flood closes J2→J3 (eastbound) from 1,500 to 3,300 s. Vehicles are
re-routed over the back street (signed detour J2 → N2 → N3 → J3; navigation users also use
J1 → N1 and N3 → N4 → J4). *Assumption:* 30 % of the regional eastbound through traffic takes
another corridor while the road is closed (`CLOSURE_DIVERSION` in `catalog.py`; set
`share=0` in `with_diversion` for a pure stress test). Without it the eastbound queue spills
back to the entry and keeps ~150 vehicles waiting to enter for the rest of the run at peak demand.

**sinkhole_cross.** The cross street north of J2 (J2↔N2) is closed both ways. North–south
traffic at J2 detours through J1 or J3 and the back street, adding turning traffic at the
neighbouring junctions — the spillover question from Report 1.

**earthquake.** At 1,200 s the J3–J4 bridge closes both ways (until 3,000 s) and debris closes
J1↔N1 (until 3,600 s). All eastbound traffic must squeeze through N4 → J4; demand is 75 % of
the peak. Seven EVs are dispatched from all sides and get routes that avoid the closures.

**fake_data_attack.** 99 phantom probe reports on J2's north approach (the 2020 Berlin
handcart). Watch whether probe-based controllers waste green on J2 NS and whether the
probe/detector cross-check raises alerts (`alerts`, `rejected_actions`).

## Events (`teamb/scenarios/events.py`)

Event kinds = `ScenarioRuntime` methods = twin commands:

| Kind | Parameters | Effect |
|---|---|---|
| `dispatch_ev` | `origin`, `destination` (edge ids), `kind` (`ambulance` / `firetruck`) | adds an EV on the fastest *open* route; returns its id |
| `close_road` | `edge`, `cause`, `both_directions` | closes an inner edge (J*/N* to J*/N*) to all traffic |
| `reopen_road` | `edge`, `both_directions` | restores the lanes and normal routing |
| `start_attack` | `junction`, `approach`, `n` | `n` phantom probe reports (1–500) |
| `stop_attack` | – | clears them |

All events validate their parameters (`ValueError` with a readable message), are idempotent
(repeating one changes nothing and logs nothing), and log a real change with `env.log_event`
(`road_closed`, `road_reopened`, `ev_dispatched`, `attack_started`, `attack_stopped`).
A scheduled event that fails is logged as `event_failed`; the run continues.

**How a closure works.** The lanes stop admitting vehicles (SUMO's router respects lane
permissions, so later trips route around the closure when they depart). Every vehicle with
the edge ahead is re-routed at once; a vehicle too close to the stop line to re-route is
retried every step until it can. Newly departed vehicles are checked again. While the closure
lasts, navigation-app users (probe vehicles, see `coverage`) on a detour re-route every 60 s
on smoothed live travel times. Reopening restores the original lane permissions and re-routes
everyone on free-flow times. Vehicles already on the closed edge drive off it.

### Verification (seed 1, 1,800 s runs at peak demand, fixed-time unless noted)

| Check | Result |
|---|---|
| Closure J2→J3 at 600 s, reopen 1,300 s | 44 vehicles re-routed at the closure; **0 vehicles drove onto the closed edge** (the 20 already on it drove off); trips inserted later all avoided it; detour entries during the closure: J2→N2 74, J1→N1 68, N3→N4 38, N4→J4 58; after reopening J2→J3 carried ~200 vehicles in the remaining 500 s; **0 teleports** |
| Same, without regional diversion | also 0 teleports, but the entry backlog reached ~150 vehicles and drained slowly at peak demand → the 30 % diversion assumption |
| Earthquake (compressed) | 4 edges closed at once, 7 EVs all arrived on open routes, **0 teleports** (one vehicle 10 m from a stop line was first re-routed from the closed edge; fixed by the per-step retry) |
| Sinkhole J2↔N2 | detours via N1 and N3 (e.g. N2→N1 82, J3→N3 97 entries in 10 min), 0 teleports, the street is used again after reopening |
| Stadium surge (compressed) | J3 north queue up to 26 vehicles (≈ 74 % of its storage), 6 spillback samples with fixed-time; max-pressure 53.7 vs fixed-time 75.3 s/veh; 0 teleports |
| 10 EVs from every side | all arrived; mean EV travel time **133.5 s with preemption vs 168.4 s without** (−35 s, −21 %; one EV without preemption had not arrived by 1,800 s); biggest gains on multi-signal trips (S1 → E5: 238 → 136 s) |

## Limitations

- Synthetic, uncalibrated corridor and demand (no field counts); volumes are plausible, not measured.
- No pedestrians, no protected left phases or left-turn bays.
- SUMO emergency vehicles here obey signals and cannot pass queues (no bluelight device), so EV
  times *without* preemption are pessimistic and the preemption benefit is an upper bound.
- Route choice: SUMO routes trips at departure on smoothed live travel times; navigation
  re-routing during closures is our simple model of app users, not a calibrated choice model.
- The 30 % regional diversion during the flood is an assumption.
