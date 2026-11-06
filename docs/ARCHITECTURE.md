# Architecture — Team B Signal Twin

A SUMO simulation of a four-junction corridor, five-plus ways to run its signals, and a
3D digital twin that shows cars and signals moving live. Everything runs from one Python
package, `teamb/`.

```
 scenarios/ ──demand + events──┐
                               ▼
 network/ ── SUMO net ──►  sim/env.py (SimEnv) ◄──── twin/server.py ◄──WebSocket──► twin/static (3D web)
                            │   ▲        │                 │
                 observation│   │action  │frames / SPaT    └── api/signal_data.py  (navigation-app feed)
                            ▼   │        ▼
 sensors/ (detectors, probes)   controllers/ ── proposal ──► safety/supervisor.py ──► SUMO signals
                                         │
 evaluation/ (metrics) ◄── tripinfo, signal events ── experiments/ (batch runs, paired reports)
```

## Packages and owners

| Package | What it does | Owner |
|---|---|---|
| `teamb/network/` | builds the SUMO network (J1–J4 + back street) and reads link indices from it | Seong Hyeon (software & integration) |
| `teamb/sim/` | `SimEnv`: one run, the step loop, frames, commands, run outputs | Seong Hyeon |
| `teamb/safety/` | independent safety supervisor (min green, yellow, all-red, rejects, preemption) | Seong Hyeon |
| `teamb/controllers/` | `base.py` + fixed-time/coordinated (Seong Hyeon); actuated, max-pressure, AI recommender, RL (Yunseong) | Yunseong (AI & security) |
| `teamb/sensors/` | loop detectors, navigation-app probe sampling, fake-data cross-check | Doyoung (data & evaluation) |
| `teamb/evaluation/`, `teamb/experiments/` | metrics, batch experiments, paired statistics, reports | Doyoung |
| `teamb/scenarios/`, `teamb/demand/` | demand, emergency/disaster/security scenarios, runtime events | Aditya (scenarios & analysis) |
| `teamb/api/`, `teamb/analysis/` | signal-data API for navigation apps, impact & cost-benefit analysis | Aditya (with Doyoung) |
| `teamb/twin/` | FastAPI server + 3D web digital twin | Seong Hyeon (integration) |

## The step loop (`SimEnv.step`)

```python
observation = sensors.observe(t, controller.observation_source)
controller.observe(observation)
action  = controller.propose_action(state)   # exception or > 0.25 s → fixed-time fallback for that step
safe    = supervisor.validate(action, t)      # malformed parts rejected + logged (SIG-02)
signals = supervisor.apply_safe_action(safe, t, preempt=emergency_vehicle_requests)
SUMO step → sensors.on_step, metrics.on_step, scenario runtime events, controller.log(step)
```

Every simulation step is 1 s. Runs are 900 s warm-up + 3600 s measurement by default.

## Contracts

### Observation (sensors → controller), every step

```jsonc
{
  "t": 1234.0, "coverage": 0.25, "sampling": "uniform",
  "junctions": {
    "J1": {
      "approaches": {               // side the traffic comes FROM: W, E, N, S
        "W": {
          "detector": {"queue": 4, "count": 7, "occupancy": 12.5, "speed": 3.1, "flow_vph": 820.0, "gap_s": 2.4},
          "probe":    {"queue_est": 8.0, "n": 2, "halted": 2, "speed": 0.4, "flow_est_vph": 760.0, "trusted": true,
                       "queue_est_adj": 7.1, "penetration_est": 0.28},   // scaled by the *estimated* probe share
          "fused":    {"queue": 4, "flow_vph": 820.0, "source": "detector"},   // best available estimate
          "oracle":   {"queue": 5, "count": 8}      // ONLY if controller.observation_source == "oracle"
        }
      },
      "exits": {"E": {"edge": "J1_J2", "detector": {...} | null, "closed": false}}   // downstream, for max-pressure
    }
  },
  "closed_edges": ["J2_J3"],        // official closure notices (flood, sinkhole, ...), sorted
  "alerts": [{"type": "probe_detector_mismatch", "junction": "J2", "approach": "N", "probe_queue": 120.0, "detector_queue": 2}]
}
```

- `detector` = E2 lane-area detectors (last 100 m before the stop line) and E1 loops 25 m before it.
- `probe` = vehicles whose navigation app shares data. `queue_est` and `flow_est_vph` are scaled by 1/coverage.
- `trusted: false` means the probe numbers disagree with the loop detectors (possible fake data).
- Ground truth (`oracle`) is never given to a controller unless it is explicitly an oracle benchmark.

### State (supervisor → controller)

```jsonc
{"t": 1234.0, "junctions": {"J1": {"signal": "EW_G", "phase": "EW", "green": true, "time_in_state": 17.0, "can_switch": true}}}
```

Signal states cycle `EW_G → EW_Y → EW_AR → NS_G → NS_Y → NS_AR`.

### Action (controller → supervisor)

`{"J1": "EW", "J2": "NS", "J3": None}` — the green axis each junction should show. `None` or a
missing junction keeps the current green. The supervisor enforces 8 s minimum green,
3 s yellow, 2 s all-red; emergency preemption can cut a green after 5 s.

### Controller interface (`teamb/controllers/base.py`)

`reset(config, seed, topology)`, `observe(observation)`, `propose_action(state)`, `log(step)`,
plus optional twin hooks `pending_recommendation()` and `handle_command(cmd)`.
Register with `@register`; set `name`, `label`, `description`, `owner`, `observation_source`.

### Frame (env → twin), `SimEnv.frame()`

```jsonc
{
  "t": 1234.0, "scenario": "rush_hour", "controller": "max_pressure", "coverage": 0.25, "ev_preemption": true,
  "vehicles": [["f0_12", 512.3, -4.8, 90.0, 11.2, "probe"]],   // id, x, y, angle° (0 = north, clockwise), speed m/s, kind
  "signals": {"J1": {"signal": "EW_G", "axis": "EW", "colors": {"W": "G", "E": "G", "N": "R", "S": "R"},
                     "time_in_state": 17.0, "min_time_to_change": 0.0, "preempted_by": null}},
  "kpi": {"t": 1230.0, "vehicles": 136, "arrived": 512, "halting": 21, "mean_speed": 8.1, "mean_delay": 41.2,
          "current_mean_delay": 18.0, "queues": {"J1": {"W": 3, "E": 0, "N": 1, "S": 0}}, "spillback": false},
  "events": [{"t": 1200.0, "type": "ev_dispatched", "vehicle": "ambulance_1", "kind": "ambulance"}],
  "phantoms": [[300.0, 12.5]],                 // positions of fake 'stopped cars' (attack)
  "alerts": [...], "closures": [{"edge": "J2_J3", "cause": "flood", "since": 1500.0}],
  "attack": {"junction": "J2", "approach": "N", "n": 99, "since": 1500.0} | null,
  "recommendation": {...} | null,              // AI recommender plan waiting for approval
  "preempting": ["J3"]
}
```

Vehicle kinds: `car`, `probe` (car sharing navigation data), `ambulance`, `firetruck`, `truck`, `bus`.
Event types: `started`, `ev_dispatched`, `ev_arrived`, `preemption`, `road_closed`, `road_reopened`,
`attack_started`, `attack_stopped`, `event_failed` (an event that could not run, with the reason);
controllers may add their own, e.g. `recommendation_ready`.

The online demo records these frames as they are (`teamb/twin/site.py`): new top-level fields are
saved too (only when they change), so they reach the online demo after the next deploy.
`vehicles` must keep its six columns.

### Geometry (env → twin), `SimEnv.geometry()` / `Topology.geometry()`

`bounds`, `lanes[{id, edge, index, kind, width, speed, length, shape[[x, y]...]}]`,
`edges[{id, from, to, kind, lanes}]`, `junctions[{id, x, y, type, signalized, shape}]`,
`tls{J: {x, y, approaches{W: {edge, lanes, axis, stop[x, y], heading}}, exits, links}}`.
Edge kinds: `arterial`, `cross`, `back`.

### Commands (twin → env), `SimEnv.handle_command(cmd)`

| `type` | params |
|---|---|
| `set_coverage` | `value` (0–1, applies to newly departing vehicles) |
| `set_preemption` | `enabled` |
| `dispatch_ev` | `origin`, `destination` (edge ids), `kind` (`ambulance`/`firetruck`) |
| `close_road` / `reopen_road` | `edge`, (`cause`) |
| `start_attack` / `stop_attack` | `junction`, `approach`, `n` |
| anything else | forwarded to `controller.handle_command` (e.g. `approve`, `reject`) |

### Signal data for navigation apps (`SimEnv.spat()`, `/api/v1/...`)

`SimEnv.spat()` → `{"t", "source", "junctions": {J: <same as frame.signals[J]>}}`. While the twin runs,
`teamb/api/signal_data.py` serves it to apps:

| Endpoint | What |
|---|---|
| `GET /api/v1/spat` | signal phase & timing for every junction |
| `GET /api/v1/spat/{junction}` | one junction (404 if unknown) |
| `GET /api/v1/advisories` | closures, active emergency preemptions, approaching-emergency warnings |
| `GET /api/v1/network` | static junction/approach description for app developers |

All return 503 when no simulation is running. Every kind in `teamb.scenarios.events.EVENT_KINDS`
is also accepted as a twin command. `close()` writes `events_report.json` (EV dispatch → arrival
times, closure/attack history, reroutes).

### Run outputs (`results/runs/<run_id>/`)

`summary.json` (metrics + run info), `manifest.json` (code revision, SUMO version, network and
demand hashes, seed, full config), `trips.csv` (one row per trip), `signal_events.csv`,
`preemptions.json`, `events_report.json` (EV dispatch → arrival, closures, attacks, reroutes),
`timeseries.csv` (KPIs every 5 s), `estimation.csv` (probe/detector/fused estimates vs ground truth —
evaluation only), `detector_intervals.csv`, `evaluation.json` (spillback, recovery, estimation error),
`tripinfo.xml`, `routes.rou.xml`. Batch experiments live in `results/experiments/<name>/` with
`summary.csv`, `report.md` and `report.json` (the twin's Results tab reads the latter).

## Network conventions

- Junctions J1–J4 at x = 0, 300, 600, 900 m on the arterial (y = 0); back street N1–N4 at y = 250.
- Edge ids are `<from>_<to>`: eastbound entry `W0_J1`, exit `J4_E5`; westbound entry `E5_J4`, exit `J1_W0`;
  cross streets enter at `NN{i}_N{i}` (south-bound) and `S{i}_J{i}` (north-bound).
- Link indices are read from the generated network, never hard-coded.

## Rules for working in parallel

1. Stay inside your package. Core files (`config.py`, `network/`, `sim/`, `safety/`, `controllers/base.py`,
   `controllers/fixed_time.py`) change only through the integrator.
2. Keep the contracts above. Adding fields is fine; renaming or removing them breaks other parts.
3. Every module gets tests in `tests/`; `pytest` must pass before you push. [CI](../.github/workflows/ci.yml) runs the whole
   suite on every pull request and push to `main`; `pytest -m "not sumo"` is a quick check without SUMO runs.
4. Short test runs (`end_time` ≤ 1200 s) keep the suite fast.
