# Scenarios & analysis — demand, events, signal-data API, cost-benefit

Owner: **Aditya Tirunagaru** (scenarios & analysis), with Doyoung for the analysis.
Code: `teamb/scenarios/`, `teamb/demand/`, `teamb/api/`, `teamb/analysis/`.
Tests: `tests/test_scenarios.py` (21 tests, ~1 min: three short SUMO runs, the rest pure Python).
Catalog and verification numbers: [`docs/scenarios.md`](../scenarios.md).

This is a working first version, written so you can run it, see what is weak and improve it
before the final presentation (Nov 5, 2026). Nothing here is field-calibrated: the corridor,
demand and cost numbers are design assumptions, and each one says so.

## Quick start

```bash
python -m teamb list                                                      # scenarios + controllers
python -m teamb run --scenario earthquake --controller fixed_time --end 1800
python -m teamb.experiments run --name cba --scenarios rush_hour,off_peak,emergency \
    --controllers fixed_time,actuated,max_pressure --seeds 1-5 --workers 2
python -m teamb.analysis.impact results/experiments/cba                    # → impact.md + impact.json
python -m teamb twin                                                      # then open http://127.0.0.1:8000/api/v1/spat
python -m pytest tests/test_scenarios.py
```

## What is where

| File | What it does |
|---|---|
| `demand/routes.py` | `Flow` (entry edge → exit edge, veh/h, profile, vehicle mix); writes the SUMO route file; one random stream per flow |
| `demand/profiles.py` | time-of-day shapes: `peak`, `pulse`, `dip`, `combine`, `flat`, `multiplier`, `integral` |
| `demand/corridor.py` | `CorridorDemand`: every named movement at J1–J4 → flows; `approach_volumes()` for a quick v/c check |
| `demand/presets.py` | tuned demand: `RUSH_HOUR` + `RUSH_PROFILE`, `OFF_PEAK`, `EVENING` |
| `scenarios/__init__.py` | `Scenario`, `Event`, `register`, `get_scenario(name, **overrides)`, `available()` |
| `scenarios/catalog.py` | the eight scenarios |
| `scenarios/events.py` | `ScenarioRuntime`: runs events, closures and re-routing, EV tracking, attacks, `report()` |
| `scenarios/routing.py` | static helpers (no TraCI): fastest route avoiding edges, detour, edge descriptions |
| `api/signal_data.py` | `/api/v1` router: SPaT, advisories, network |
| `analysis/impact.py` | paired impact vs a baseline, annualized cost-benefit, markdown/JSON output, CLI |
| `analysis/assumptions.py` | every cost-benefit number with unit, basis and source; `ANNUAL_HOURS`; cost profiles |

```
catalog.py ─ Scenario(flows, events) ─► SimEnv ─ build_routes(seed) ─► routes.rou.xml ─► SUMO
                                            └─ ScenarioRuntime.on_step(t) every step:
                                                 due events · closure re-routing · EV tracker · teleport count
twin / tests ─ /api/v1/* ─► signal_data.py reads supervisor + runtime + topology (never TraCI)
experiments ─ runs/*/summary.json ─► analysis/impact.py ─► impact.md (per-hour table, B/C, assumptions)
```

## How to add a scenario

1. Write a function in `teamb/scenarios/catalog.py` and decorate it with `@register`:

```python
@register
def landslide() -> Scenario:
    return Scenario(
        name="landslide",                                   # unique id (used on the command line)
        title="Landslide · back street blocked",
        title_ko="산사태 · 이면도로 통제",
        description="Rain loosens the hillside: the back street N2–N3 is blocked both ways for 40 min ...",
        flows=rush_flows(),                                 # or your own list of Flow / CorridorDemand(...).flows(profile)
        events=[
            Event(1500, "close_road", {"edge": "N2_N3", "cause": "landslide", "both_directions": True}),
            ev(1560, "NN3_N3", "J2_S2", "firetruck"),
            Event(3900, "reopen_road", {"edge": "N2_N3", "both_directions": True}),
        ],
        category="disaster",                                # baseline | demand | emergency | disaster | security
        question="Does losing the detour route make the arterial fragile?",
        measures=["mean_delay_s", "unfinished_pct", "ev_mean_travel_time_s"],
        owner=ADITYA,
    )
```

2. Check it: `python -m teamb list`, then `python -m pytest tests/test_scenarios.py` (every
   scenario is validated and built for two seeds automatically), then a short run:
   `python -m teamb run --scenario landslide --end 1800`. Look at `teleports` and `never_inserted`
   in the summary — both should stay near zero unless the scenario is meant to overload the network.
3. Add a row to the table in `docs/scenarios.md` and, if it represents real operating hours,
   an entry in `ANNUAL_HOURS` (`teamb/analysis/assumptions.py`).

Tips
- Edge ids are `<from>_<to>` (`J2_J3` = eastbound between J2 and J3; see the map in
  `docs/scenarios.md`). Only inner edges (between J* and N* nodes) can be closed.
- Event times are simulation seconds; the measurement window is 900–4,500 s.
- To try variations without new code: `get_scenario("earthquake", demand_scale=0.6, events=[...])`, or
  `SimEnv(..., scenario_params={...})`, or the experiments runner's `--scenario-params`.
- A demand surge: `Flow(origin, destination, rate, name=..., profile=pulse(start=..., rise=..., hold=..., fall=...))`.
  Remember that SUMO routes trips on live travel times at departure: a surge entering at NN3 will
  partly spread over the back street. Start it on an inner edge (as the stadium garage does,
  `N3_J3`) if all of it must pass one junction.

## How to add an event type

Event kinds are methods of `ScenarioRuntime` listed in `EVENT_KINDS` (`teamb/scenarios/events.py`).
Example — a lane closure (one lane blocked by debris):

```python
EVENT_KINDS = (..., "close_lane")

def close_lane(self, edge: str, lane: int = 1, cause: str = "debris") -> dict:
    lane_id = f"{edge}_{lane}"
    if lane_id not in self.topology.edge_lanes(edge):        # 1. validate → ValueError with a clear message
        raise ValueError(f"edge {edge} has no lane {lane}")
    if lane_id in self._permissions:                         # 2. idempotent: no change, no log
        return {"lane": lane_id, "closed": False}
    self._permissions[lane_id] = list(self.conn.lane.getAllowed(lane_id))
    self.conn.lane.setDisallowed(lane_id, ["all"])           # 3. act through TraCI
    self.env.log_event("lane_closed", edge=edge, lane=lane, cause=cause)   # 4. log real changes
    return {"lane": lane_id, "closed": True}                 # 5. return something JSON-serializable
```

Then add a test in `tests/test_scenarios.py`. Rules: never crash the run (`on_step` already
turns a failing scheduled event into an `event_failed` log entry), keep per-step work small
(TraCI calls cost ~50 µs each), and never call TraCI from the API.
Scheduled events work at once. **Twin commands** for a new kind also need one line in
`SimEnv.handle_command` (core, owned by Seong Hyeon): it forwards only the five original kinds
today (requested: forward everything in `EVENT_KINDS`).

## Signal-data API (for navigation apps)

Like Busan sharing live signal timing with navigation apps. The twin mounts the router, so with
`python -m teamb twin` running:

| Endpoint | Returns |
|---|---|
| `GET /api/v1` | version, endpoint list, units, whether a simulation is running |
| `GET /api/v1/spat` | signal phase & timing for J1–J4 |
| `GET /api/v1/spat/{junction}` | one junction (`J2`, case-insensitive); 404 if unknown |
| `GET /api/v1/advisories` | road closures with detours, active preemptions, emergency vehicles, warnings |
| `GET /api/v1/network` | junctions, approaches, lanes, movements, signal rules — static, works without a simulation |

Every response has `api_version`, `source`, `generated_at` (UTC, ISO 8601), `t` (simulation
seconds), `scenario`, `controller` and `units` (s, m, m/s; positions in SUMO meters, headings
0° = north, clockwise). Errors: **503** `{"detail": "no simulation running"}` (or "has finished"),
**404** for an unknown junction. Live responses carry `Cache-Control: no-store`.

```bash
curl -s localhost:8000/api/v1/spat/J2 | python -m json.tool
```

```jsonc
{ "api_version": "1.0", "t": 73.0, "controller": "fixed_time", "junction": "J2",
  "signal": "NS_G", "axis": "NS", "colors": {"W": "R", "E": "R", "N": "G", "S": "G"},
  "time_in_state": 28.0, "min_time_to_change": 0.0, "preempted_by": null,      // same as the twin frame
  "phase": "green", "state_ends_in_s": {"min": 0.0, "max": null, "likely": 12.0},
  "prediction": "timing_plan",                       // timing_plan | exact (yellow/all-red) | minimum_only
  "approaches": {
    "N": {"edge": "N2_J2", "state": "green", "next_color": "Y",
          "next_change_in_s": {"min": 0.0, "max": null, "likely": 12.0}, "next_change_at_t": {"min": 73.0, "likely": 85.0}},
    "W": {"edge": "J1_J2", "state": "red", "next_color": "G",
          "next_change_in_s": {"min": 5.0, "max": null, "likely": 17.0}} } }
```

`min` comes from the safety rules (minimum green, 3 s yellow, 2 s all-red; 5 s when an EV
preempts). `likely` comes from the controller's timing plan when it has one (`fixed_time`,
`coordinated`, an applied AI-recommender plan); adaptive controllers decide every second, so
only the minimum is known (`prediction: "minimum_only"`) — exactly the problem real SPaT feeds
have with adaptive signals.

`/api/v1/advisories` during a flood with an ambulance approaching J1:

```jsonc
{ "counts": {"closures": 1, "preemptions": 1, "emergency_vehicles": 1},
  "closures": [{"edge": "J2_J3", "direction": "EB", "cause": "flood", "since_t": 60.0,
                "detour": ["J2_N2", "N2_N3", "N3_J3"], "detour_nodes": ["J2", "N2", "N3", "J3"]}],
  "preemptions": [{"junction": "J1", "axis": "EW", "vehicle": "ambulance_1", "since_t": 72.0}],
  "emergency_vehicles": [{"vehicle": "ambulance_1", "edge": "W0_J1", "speed_mps": 13.56,
                          "next_junction": "J1", "approach": "W", "distance_to_junction_m": 122.7, "eta_s": 9.0}],
  "warnings": [{"type": "emergency_vehicle_approaching", "severity": "high", "junction": "J1",
                "message": "Ambulance approaching J1 from the west in about 9 s. Pull over, yield and keep the junction clear."},
               {"type": "signal_preempted", ...}, {"type": "road_closed", ...}] }
```

EV warnings start 300 m before a junction (`EV_WARNING_DISTANCE_M`); preemption starts at
150 m (`config.EV_PREEMPT_DISTANCE_M`).

**Thread safety (keep this rule).** The twin steps SUMO on its own thread, and TraCI is one
socket. The API therefore only reads Python state — `env.supervisor`, `env.runtime` (closures,
the EV tracker updated in `on_step`), `env.topology` — and never calls TraCI. If you need new
live data, collect it in `ScenarioRuntime.on_step` and read it from the API.

Testing it without the twin (see `test_signal_data_api`):

```python
app = FastAPI(); app.include_router(build_router(lambda: env)); client = TestClient(app)
```

## Impact & cost-benefit analysis

`python -m teamb.analysis.impact results/experiments/<name>` (or any folder of runs, a JSON list
of summaries, a `summary.csv`; `--baseline coordinated`, `--params my.json`, `--out`, `--json`).
It writes `impact.md` and `impact.json` into the experiment folder.

**Method** (formulas also in the module docstring). Runs are paired by seed with the baseline
(same scenario, coverage, sampling, preemption), so every controller saw identical demand.

1. Per run: `delay veh·h per hour = (mean_delay_s × completed + unfinished × 300 s) / 3600 / window_h`.
   Unfinished trips are charged 300 s each so stranding vehicles never looks good (PERF-01);
   a candidate with > 1 pp more unfinished trips than the baseline is flagged and not counted.
2. Per pair: delay saved (veh·h/h) × value of time per vehicle-hour ($32.22 with 1.52 persons
   per car at $21.10 and 4 % trucks at $35.70); fuel saved = delay saved × 0.25 gal/h idle +
   stops saved × 0.005 gal/stop, valued at the pre-tax price; CO₂ = 8.887 kg/gal; EV time saved
   from `ev_mean_travel_time_s`.
3. Seeds averaged with a 95 % t-interval.
4. Annual benefit = Σ per-hour value × hours per year the scenario stands for (`ANNUAL_HOURS`:
   rush hour 500 h, night 2,920 h, events 40 h, closures a few hours). Compared with the
   deployment cost: capital × capital-recovery factor (7 %, 10 years) + O&M → B/C ratio, payback, NPV.
5. If runs with preemption on *and* off exist, a separate table shows EV time saved and the
   extra delay for everyone else.

**Key assumptions** (full table with sources in every `impact.md`):

| Parameter | Value | Basis |
|---|---|---|
| Value of time | $21.10 / person-h (2023 $) | USDOT BCA Guidance, May 2025 |
| Vehicle occupancy | 1.52 | USDOT BCA Guidance (Caltrans uses 1.15 at peak — try it) |
| Truck value of time | $35.70 / h | USDOT BCA Guidance |
| Idle fuel | 0.25 gal/h | DOE Fact #861 range 0.16–0.39 |
| Fuel per stop | 0.005 gal | physics estimate (derived) |
| Fuel price − tax | $4.27 − $0.762 / gal | Caltrans Cal-B/C 2025 matrix (California) |
| CO₂ | 8.887 kg/gal; $190/t | EPA; EPA 2023 SC-GHG (USDOT 2025 no longer monetizes CO₂ → set 0) |
| Adaptive signal cost | $65,000 / intersection + $5,000/yr | Lodes & Benekohal 2013 (upper end); O&M assumed |
| Actuated / retiming / recommender | $20k / $4k / $5k per intersection | assumptions |
| Discount rate, life | 7 %, 10 years | USDOT 2025; assumption |
| EV runs per year | 1,100 | assumption |

Override any of them: `{"vehicle_occupancy": 1.15, "annual_hours": {"rush_hour": 750}}` in a
JSON file passed with `--params`. Present results as *"under these assumptions"*, with the
ranges, never as measured savings.

## Verification so far

See the table in `docs/scenarios.md`: closures re-route everyone (0 vehicles onto a closed edge,
0 teleports), reopening restores the arterial, EVs from every side arrive with preemption
(133.5 s vs 168.4 s without, 10 EVs at peak demand), and fixed-time rush hour is congested but
never gridlocked while re-balanced timing cuts delay by ~40 %.

## TODO (good next steps)

- [ ] Run the real matrix (≥ 5 seeds, full 4,500 s) for `rush_hour`, `off_peak`, `emergency`
      (preemption on/off) and fill the CSUEB section of Report 4 with `impact.md`.
- [ ] Calibrate: replace the preset volumes with counts from a real corridor (e.g. a Hayward
      arterial near CSUEB, or Sejong) and the costs with a local agency quote.
- [ ] More first responders: police pursuit (high speed, no fixed destination), search & rescue
      convoy (several vehicles), EV arrival times as a distribution, not a mean.
- [ ] More natural disasters: landslide (back street), wildfire evacuation (one-way outbound surge),
      tsunami/flood with rising water closing edges one after another.
- [ ] Try SUMO's bluelight device for EVs (rescue lane, cautious red-light running) as a sensitivity:
      today EVs cannot pass queues, so the preemption benefit is an upper bound.
- [ ] Lane closures (one lane blocked) and speed-limit changes as event types (sketch above).
- [ ] Mock navigation app: a small web page that polls `/api/v1/spat` and shows "green in N s"
      and the advisories for a chosen approach — a good demo for Nov 5.
- [ ] Value emergency response time (survival, property loss) with a cited source instead of hours only.
- [ ] Truck-specific delay from `trips.csv` (vehicle type is there) instead of a fixed truck share.
- [ ] Ideas from the Nov 5 joint session with CSUEB students.
