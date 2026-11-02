# Digital twin — live 3D corridor, server and web app

Owner: **Seong Hyeon (Joshua) Kim** (software & integration).
Code: `teamb/twin/` (server) and `teamb/twin/static/` (web app, no build step).
Tests: `tests/test_twin.py` (9 tests, ~15 s: one short SUMO session at max speed plus REST checks),
`tests/test_site.py` (online demo: encoding, a short recorded run, the static page).
Online demo: **https://sunghyunc.github.io/team-b-signal-optimization/** (recorded runs, see below).

The twin runs one live SUMO simulation and shows it in 3D in the browser: cars, trucks, buses,
ambulances and fire trucks drive through the four signals, the signal heads change color, queues
glow on the road, and you can dispatch an emergency vehicle, flood a road or fake navigation
data while it runs. It is the centerpiece of the Nov 5 presentation, so it is built to be
reliable on a laptop with a projector: one command, one browser tab.

## Quick start

```bash
python -m teamb twin                    # http://127.0.0.1:8000  (--port 8765 to change)
python -m pytest tests/test_twin.py     # server tests
python -m teamb.twin.vendor             # once, while online: offline copy of three.js for the venue
```

Open the page and a run starts by itself (rush hour, fixed-time, from 4:00 so the roads are
already busy). Pick a scenario/controller in the top bar and press **Restart**.

Demo links (the page restarts the run if it differs from these settings):

| What to show | URL |
|---|---|
| Ambulance gets a green wave | `/?scenario=emergency&controller=coordinated&start=1170&speed=2&camera=J1` |
| Flood closes the arterial, traffic detours | `/?scenario=road_closure&controller=max_pressure&start=1470&speed=5` |
| Fake navigation data (Berlin "99 phones") | `/?scenario=fake_data_attack&controller=max_pressure_probe&start=1470&speed=5&camera=J2` |
| AI recommends, engineer approves | `/?scenario=rush_hour&controller=ai_recommender&start=590&speed=5` |
| Full-screen 3D for the projector | add `&present=1` (or press **P**) |

Parameters: `scenario`, `controller`, `seed`, `coverage` (0.25 or 25), `ev=0`, `start` (sim
seconds to fast-forward to), `speed` (1, 2, 5, 10, 20, max), `camera` (overview, J1–J4, top),
`present=1`, `autostart=0`.

Keys: **Space** play/pause · **.** one step · **0** overview · **1–4** junctions · **T** top view ·
**F** follow the newest emergency vehicle · **P** hide the side panels · **Esc** close the road menu.

## Online demo (GitHub Pages)

GitHub Pages only serves files, so SUMO cannot run there. `teamb/twin/site.py` simulates each
run in `DEMO_RUNS` once (same `SimEnv`, seed 1), saves every frame, and publishes the same web
app with `window.TWIN_STATIC` set. `static/js/replay.js` then plays the files through the same
interface as the WebSocket, so the panels and the 3D view work unchanged: pick a run, play,
pause, change speed, click anywhere on the timeline (a recording can rewind). Actions, the AI
card's buttons and the coverage/EV switches explain that they need the live twin.

```bash
python -m teamb.twin.site build     # ~3 min: records all runs into site/ (gitignored)
python -m teamb.twin.site serve     # http://127.0.0.1:8001, check it before publishing
python -m teamb.twin.site deploy    # build + force-push site/ to the gh-pages branch
```

- **Add a run:** append a `DemoRun(scenario, controller, note)` to `DEMO_RUNS`. A variant with
  different `controller_params` needs its own `key` and `label` (see the detector cross-check run).
- **Data:** `data/runs/<id>/run.json` (status, vehicle ids, events, KPI history) plus one file per
  5 simulated minutes, loaded only when playback reaches it (~0.7 MB per 30 min over the wire).
  Vehicles are delta-encoded (`encode_vehicles`), unchanged fields are left out.
- **Results tab:** `results/experiments/*/report.json` when you have them, else the published
  copies in `docs/results/reports/`.
- **When to redeploy:** after a change on `main` that shows in the twin (controllers, scenarios,
  web app). The gh-pages branch is replaced on every deploy, so it never grows.

## What is where

| File | What it does |
|---|---|
| `twin/server.py` | FastAPI app: REST, WebSocket `/ws`, static files, mounts `teamb/api/signal_data.py` at `/api/v1` |
| `twin/session.py` | `TwinSession`: the one live `SimEnv`, its sim thread, pacing, fast-forward, broadcasting |
| `twin/meta.py` | `/api/meta` (controllers, scenarios, closable roads, EV routes, attack targets), `/api/results` |
| `twin/vendor.py` | downloads the pinned three.js files for offline use |
| `twin/site.py` | online demo: records `DEMO_RUNS`, writes the static site, publishes it on gh-pages |
| `static/js/replay.js` | online demo: `ReplaySocket` plays recorded runs like the server would |
| `static/index.html`, `static/css/twin.css` | page layout and the dark "operations center" style |
| `static/js/main.js` | entry point: loads meta + geometry, builds everything, routes WebSocket messages |
| `static/js/net.js` | REST helpers, `TwinSocket` (auto-reconnect, `control()`/`command()` return the reply) |
| `static/js/scene.js` | renderer, camera, orbit controls, lights + shadows, sky, ground, camera presets, follow cam |
| `static/js/roads.js` | asphalt from lane shapes, junction pads, US markings, stop lines, crosswalks, road picking |
| `static/js/city.js` | blocks with curbs/sidewalks, seeded buildings, trees, street lights |
| `static/js/signals.js` | poles, mast arms, 3-lamp heads, colored stop bars, junction labels |
| `static/js/vehicles.js` | instanced vehicle models per kind, interpolation, brake lights, EV light bars, glow, labels |
| `static/js/overlays.js` | queue strips, closures (flood/sinkhole/crash + barricades), fake phones + alerts, preemption rings |
| `static/js/ui/*.js` | panels: `topbar` (session, playback, clock, timeline), `kpis`, `junctions`, `events`, `actions`, `ai`, `spat`, `viewport` (title, banners, overlay, camera bar, legend) |
| `static/js/results.js` | Results tab: charts and tables from `results/experiments/*/report.json` |
| `static/js/recorder.js` | Record button: 3D view + small HUD to a WebM file |
| `static/js/util.js` | coordinates, seeded random, formatting, constant-size text sprites |

## How it works

```
 browser ──POST /api/session──► server ──restart()──┐
    ▲                                                 ▼
    │  {type: frame | status | hello | reply}    queue ──► sim thread (TwinSession._run)
    └──────────── WebSocket /ws ◄── Hub ◄───────────────── env.step() … env.frame() (≤ 12 fps)
       {type: control | command} ──► submit() ─► queue ─► env.handle_command() between steps
```

- **One thread owns SUMO.** TraCI is a single socket; two threads talking to it corrupt it.
  Every call that may touch TraCI (`start`, `step`, `frame`, `handle_command`, `close`) runs on
  the sim thread. Web handlers put a function on a queue and await its `Future`. Even the
  signal-data router gets a proxy (`EnvProxy`) whose method calls run on the sim thread.
- **Pacing.** `speed` = simulated seconds per wall second. Paced mode steps whenever a step is
  due (and never tries to "catch up" after a hiccup); `max` and fast-forward step as fast as
  SUMO goes (about 20–50× real time on a laptop). Frames go out at most 12 times a second.
- **Smooth motion.** At 1× there is one frame per second. The browser moves every vehicle from
  where it is drawn to its newest position over the measured frame interval, so motion looks
  continuous at any speed. SUMO reports the front bumper; models are shifted back half a length.
- **Frames drain events.** `SimEnv.frame()` empties the env's event list, so the session calls it
  in one place and keeps the drained events (and a KPI history) for browsers that connect later.
  The session also merges `controller.drain_events()` (e.g. `recommendation_ready`, `plan_applied`).
- **Sessions.** Every (re)start gets a new `sid`; frames carry it, so a browser drops stale
  frames. Twin runs write their outputs to `results/twin/<run_id>/` (not `results/runs/`).
- **Coordinates.** SUMO (x east, y north) → three.js `(x, height, -y)`. Headings are
  navigational (0° = north, clockwise) → `rotation.y = -heading`.
- **Readable city.** The preset cameras look north; buildings just south of an east–west street are
  kept low and step up further away (`heightCap` in `city.js`), so the corridor is never hidden.

### Messages

| Direction | Message |
|---|---|
| server → browser | `hello` (status, recent events, KPI history), `frame` (`SimEnv.frame()` + `type`, `sid`), `status` (state, config, speed, end_time, warmup, scenario events, summary when finished), `reply` (`id`, `ok`, result or `error`) |
| browser → server | `{"type": "control", "id", "action": "play" \| "pause" \| "step" \| "reset" \| "speed" \| "jump", "speed", "t"}` |
| browser → server | `{"type": "command", "id", "command": {"type": "dispatch_ev", ...}}` — any `SimEnv.handle_command` command, including controller commands (`approve`, `reject`, `optimize`) |

The same is available over HTTP: `POST /api/control`, `POST /api/command`, `POST /api/session`
(`?wait=1` blocks until SUMO is up), `GET /api/state`. States: `idle`, `loading`, `running`,
`paused`, `finished`, `error`. `jump` to an earlier time restarts the run and fast-forwards.

## How to add an overlay (something drawn in 3D from frame data)

1. In `static/js/overlays.js`, write a class with `constructor(ctx)`, `update(frame)`,
   `animate(now, dt)` and optionally `reset()`. `ctx` has `scene`, `geometry`, `index` (lanes by
   id, lanes per edge, signal approaches) and `view` (camera, `viewDistance()`).
2. Append it to `OVERLAYS` at the bottom of the file. That's it — `main.js` creates it and calls it.

```js
export class SpillbackOverlay {
  constructor({ scene, geometry }) { this.mesh = /* … */; scene.add(this.mesh); }
  update(frame) { this.mesh.visible = !!(frame.kpi && frame.kpi.spillback); }
  animate(now) { this.mesh.material.opacity = 0.5 + 0.3 * Math.sin(now / 300); }
}
export const OVERLAYS = [QueueOverlay, ClosureOverlay, AttackOverlay, PreemptionOverlay, SpillbackOverlay];
```

Use `approachFrame(index, 'J2', 'N')` from `util.js` to get an approach's stop point, direction,
width and length, and `makeLabel(text)` for a label that stays readable at any zoom (and shows
up in recordings).

## How to add a panel

1. Add a container to `static/index.html` (e.g. a `<section class="card">` in a side column).
2. Write `static/js/ui/mypanel.js` with a class whose constructor subscribes to the bus:
   `ctx.bus.on('frame', f => …)`, `'status'`, `'hello'`, `'session'` (a new run started).
   Send things with `await ctx.socket.command({type: …})` or `ctx.socket.control('pause')`.
3. Create it in `main.js` next to the others: `new MyPanel(ctx);`.

New event types from `SimEnv.log_event()` show up in the event log automatically; add a line to
`STYLE` in `ui/events.js` to give one its own color and wording. New controllers and scenarios
appear in the top bar automatically (`/api/meta` reads the registries). A controller that
implements `pending_recommendation()` gets the AI card.

## Checks before a demo

- `python -m pytest tests/test_twin.py`
- `for f in $(find teamb/twin/static/js -name '*.js'); do node --experimental-default-type=module --check $f; done`
- Open the page, press **1–4** and **0**, dispatch an ambulance with "follow with the camera".
- On the presentation laptop: `python -m teamb.twin.vendor` while online, then test once offline.
- Chrome/Edge record best (WebM); Safari may not support the Record button.

## Limitations (honest list)

- One live session per server; every open browser sees (and controls) the same run.
- SUMO cannot rewind: jumping back restarts the run and fast-forwards.
- Fast-forward speed is bounded by SUMO + TraCI (~20–50 sim-s per wall second on a laptop), so
  starting a run at 20:00 takes up to a minute. Use the `start` presets for the demo.
- Vehicles inside a junction are drawn at SUMO's reported position; turning paths are linear
  between frames, which can cut corners slightly at high speed.
- The city (buildings, trees) is decorative and generated from the road layout; only roads,
  signals and vehicles come from the simulation.
- The online demo shows recordings: one seed per run, and nothing can be dispatched, closed or
  approved there. Positions are stored to 10 cm and headings to 1°, which is invisible on screen.
- On phones the 3D view takes touch drags for the camera; scroll the page from the top bar or
  the panels below it.

## Next improvements (good first tasks)

- [ ] **A/B split screen**: two sessions side by side (e.g. fixed-time vs AI recommender, same seed).
- [ ] **Demo script mode**: a timed list of camera moves and actions for the Nov 5 presentation.
- [ ] **Turn arrows** on approach lanes and **pedestrian signals** at the crosswalks.
- [ ] **Vehicle inspector**: click a car to see its route, delay so far, and whether it is a probe.
- [ ] **Night mode** (lit windows, headlights) — the emissive lights are already there.
- [ ] **Time-space diagram** panel for the arterial (shows the green wave directly).
- [ ] **KPI comparison overlay**: live mean delay vs the same seed under the baseline controller.
- [ ] Show `/api/v1/advisories` in the SPaT panel (closures and preemptions as an app would get them).
