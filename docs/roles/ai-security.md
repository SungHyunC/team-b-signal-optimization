# AI & security — signal controllers, AI recommender, RL and defenses

Owner: **Yunseong Lee** (AI & security). Code: `teamb/controllers/`. Tests: `tests/test_controllers.py`.

This is a working first version, built so the team can run it, see what is wrong, and improve
it before the final presentation (Nov 5, 2026). Every number below can be reproduced with the
commands shown; nothing is field-calibrated.

## Quick start

```bash
python -m teamb run --scenario rush_hour --controller max_pressure --end 1500
python -m teamb run --scenario fake_data_attack --controller max_pressure_probe   # gets fooled
python -m teamb.controllers.rl_train                                              # retrain RL (~10 min)
python -m pytest tests/test_controllers.py                                        # ~1 min
```

In the twin every controller is in the dropdown. With `ai_recommender`, the search starts at
t = 600 s; when the recommendation turns **pending**, approve or reject it (`approve` / `reject`
commands with the recommendation `id`), or send `optimize` to search again now.

## What is where

| File | What it does |
|---|---|
| `common.py` | `AdaptiveController` base: decision clock, own min/max green, fixed-time fallback on bad data |
| `defense.py` | `ObservationGuard`: stale / replayed observations, untrusted or physically impossible probe values |
| `actuated.py` | `actuated` — gap-out / max-out from loop detectors |
| `max_pressure.py` | `max_pressure` (detectors) and `max_pressure_probe` (navigation probes, no defense) |
| `demand_model.py` | demand estimate from probe data only, and OD flows that reproduce it |
| `optimizer.py` | timing-plan search (Optuna TPE) by simulating the estimated demand; cache; background worker |
| `ai_recommender.py` | `ai_recommender` — recommend → engineer approves → apply |
| `rl.py`, `rl_train.py` | `rl` — tabular Q-learning controller and its training script |
| `fast_env.py` | `SimEnv` subclasses that skip work the plan search / RL training do not need |
| `models/rl_qtable.json` | the trained Q-table (see `models/README.md`) |

`fixed_time` and `coordinated` (Seong Hyeon, `fixed_time.py`) are the baselines; their
`TimingPlan` is also the plan format the AI recommender searches and applies.

## How a controller plugs in

Every step the env gives the controller an observation (detectors, probes) and the signal state,
and the controller *proposes* a green axis per junction (`{"J1": "EW", "J2": None, ...}`). The
safety supervisor (`teamb/safety/`) enforces 8 s minimum green, 3 s yellow and 2 s all-red,
rejects malformed proposals, and handles emergency preemption. None of my controllers builds
signal states or bypasses the supervisor; the tests check that the supervisor never sees an
invalid proposal from them.

The adaptive controllers decide on a clock (actuated every 1 s, max-pressure and RL every 5 s)
and only once a green has lasted their own `min_green` (10 s, never below the supervisor's 8 s).
If the observation is missing, stale or replayed, they run the approved fixed-time plan (90 s,
50/50) until good data returns.

## 1. Actuated (`actuated`)

Classic gap-out / max-out, the way most US and Korean actuated signals work:

- keep the green at least `min_green` (10 s);
- nobody waiting on the other street (`detector.count` and `queue` are 0) → rest in green;
- a car crossed a green-axis loop within `gap_out` seconds (`detector.gap_s ≤ 3 s`) → extend;
- otherwise switch (gap-out), and always switch at `max_green` (50 s) if the other street waits.

`gap_s` is the smallest over the lanes of an approach and over both green approaches, so the
green ends only when both directions have a gap (like crossing the barrier in a dual-ring
controller). Tune: `gap_out` (2.5–4 s typical), `min_green`, `max_green`.

## 2. Max-pressure (`max_pressure`, `max_pressure_probe`)

Varaiya (2013). For junction *j* and axis *p* (EW or NS):

```
pressure(p) = Σ_{approaches a of p}  w(a) · ( x_up(a) − x_down(a) )
```

- `x_up(a)`: cars on approach *a* that want to cross (moving or stopped);
- `x_down(a)`: *stopped* cars on the road that *a*'s straight-on traffic enters (W → exit E,
  E → exit W, N → exit S, S → exit N) — the room that is gone there; 0 when that road leaves
  the corridor;
- `w(a)`: 1, or the lane count with `weighted=True` (Varaiya weights each movement by its
  saturation flow).

Every 5 s it keeps the current green unless `pressure(other) > pressure(current) + margin`
(margin 2 cars), which avoids flip-flopping — every switch costs 5 s of yellow + all-red.
Serving the higher pressure moves cars from long queues into roads with room; in theory it
is throughput-optimal and needs no timing plan.

**What counts as "cars" (`measure` upstream, `down_measure` downstream).** The first version
used stopped cars only (`detector.queue`) on both sides, as the spec said. On our corridor that
backfires: when an axis turns green its cars start moving, its "queue" drops to ~0 within
seconds, and the controller flips back right after min green. In a first test arterial greens
averaged only 11–14 s, the arterial lost capacity, and mean delay was **82.5 s — worse than fixed-time (69.4 s)** on
rush hour (2 seeds, 2700 s). Varaiya's model is store-and-forward, where the queue is every car
on the link, so upstream we now count every car in the detector zone (`measure="count"`,
`detector.count`). Downstream only stopped cars take away room (`down_measure="queue"`);
counting moving cars there — a platoon that was just released — made the probe version
flip-flop. With the defaults: **29.7 s**. Both options stay available for comparison
(`measure="queue"` reproduces the literal spec). Lane weighting made little difference here.

**Sources.** `source="detector"` (default) uses loop detectors. `source="probe"` uses
navigation-app probes only: `probe.n / coverage` (`count`) or `probe.queue_est` (`queue`) on the
approach, and the probe estimate on the downstream junction's approach for `x_down`.
`max_pressure_probe` is that controller with no defense — the target of the fake-data attack.
`defense=True` ignores probe entries flagged `trusted: false` by the sensors' cross-check or
claiming more cars than the lanes can physically hold, and uses the loop detector there.

## 3. AI recommender (`ai_recommender`)

Modeled on Google's Project Green Light: the AI never drives the signals; it recommends a
timing plan, an engineer approves it, and only then it is applied.

```
run the current plan (fixed-time 90 s) ─► collect probe data ─► t = search_at (600 s) or "optimize"
   ─► estimate demand (probes only) ─► search plans in simulation ─► recommendation "pending"
   ─► engineer: approve → plan applied   |   reject → keep the current plan
```

**Demand model (`demand_model.py`).** Only navigation-app probe data, never detectors or ground
truth. Every 10 s it samples each approach's `probe.flow_est_vph` (probes that crossed the stop
line, scaled by 1/coverage) and `probe.queue_est`. Over the last `window_s` (300 s):

```
demand(a) = mean probe flow(a) + max(0, queue_est at window end − at window start) / window
```

The second term is unserved demand (cars that arrived but could not leave). Approaches with no
usable sample borrow the mean of the same approach at the other junctions. The approach volumes
become OD flows by flow conservation: through traffic on the arterial and the cross streets,
plus turning traffic wherever the arterial volume changes between two junctions (cars that
leave turn onto a cross street; cars that join come from one). The test
`test_od_flows_reproduce_the_approach_volumes` checks that these OD flows give back exactly the
approach volumes. At low coverage each probe stands for many cars, so the model gets noisy —
that is the sampling-bias experiment, so do not "fix" it with detector data.

**Search (`optimizer.py`).** Optuna TPE (seeded with the run seed, multivariate) over:

| parameter | range |
|---|---|
| cycle | 60–150 s, 5 s steps (one common cycle) |
| EW share of the usable green, per junction | 0.25–0.85 |
| offset of J2, J3, J4 (J1 is the reference) | 0–1 × cycle |

Each candidate is one headless `SimEnv` run of the *estimated* demand: 300 s warm-up, 900 s of
measured departures, 150 s cool-down so measured cars can finish. Objective (minimised):

```
objective = mean delay (s/veh) + 600 s × (unfinished trips / measured trips)
```

All candidates use the same demand seed (common random numbers), so differences come from the
plan, not the traffic draw. The current plan is evaluated first (the baseline), and the first
trials are engineering guesses — the Webster plan for the estimated flows
(`C0 = (1.5 L + 5)/(1 − Y)`, greens ∝ critical flow ratios) with and without an eastbound green
wave — so even a short search starts from a sensible plan. If no candidate beats the baseline,
the recommendation says so and keeps the current plan.

**Modes.** *Async* (default; the live twin): the search runs in a spawned worker process and is
polled from `log()`, so the simulation never waits; `progress.done/total` updates per trial.
*Sync* (default with `auto_approve=True`; batch experiments and tests): the search runs inside
`log()` — outside the 0.25 s controller budget, which only covers `observe` / `propose_action` —
so results do not depend on wall-clock speed. Results are cached in
`results/cache/ai_recommender/<key>.json`, keyed by everything that determines the search, so
re-running an experiment seed does not repeat the search.

**Recommendation** (`pending_recommendation()`, shown as `frame["recommendation"]`):

Real example (rush hour, seed 2, coverage 100 %, approved automatically; lists shortened):

```jsonc
{"id": "rec1-t600", "status": "approved",            // "searching" | "pending" | "approved" | "rejected"
 "created_t": 600.0,
 "plan": {"cycle": 60.0, "splits": {"J1": 0.751, "J2": 0.676, "J3": 0.629, "J4": 0.724},
          "offsets": {"J1": 0.0, "J2": 24.0, "J3": 48.0, "J4": 12.0}},          // null while searching
 "current_plan": {"cycle": 90.0, "splits": {"J1": 0.5, ...}, "offsets": {}},
 "expected": {"mean_delay_s": 26.46, "baseline_mean_delay_s": 55.64, "improvement_pct": 52.4,
              "objective": 28.22, "baseline_objective": 78.514, "unfinished": 2},  // null while searching
 "based_on": {"coverage": 1.0, "window_s": 300.0, "trials": 30,
              "estimated_flows": {"J1": {"E": 497.0, "N": 135.0, "S": 171.0, "W": 1032.0}, ...},
              "probe_samples": 31, "ignored_untrusted": 0, "defense": false,
              "source": "navigation-app probes only"},
 "progress": {"done": 31, "total": 31}, "note": "", "error": null,
 "decided_by": "auto_approve", "decided_t": 600.0}
```

`expected` is measured on the *estimated* demand model, not on the real traffic; on the real
run this plan gave 33.3 s against 71.1 s for the 90 s plan (−53 %).

A failed search shows as `rejected` with `decided_by: "system"` and an `error`.

**Commands**: `{"type": "approve", "id"}`, `{"type": "reject", "id"}`, `{"type": "optimize"}`; each
returns `{"ok": ...}`. With `approval_token` set, approve/reject must carry the same `"token"`;
every command is written to `controller.audit`.

## 4. Reinforcement learning (`rl`)

Tabular Q-learning in numpy (no torch), one policy shared by the four junctions.

- **Actions** every 5 s, for a junction that has shown green ≥ 10 s: 0 = keep, 1 = switch.
- **State** (288 states, loop detectors only): green axis (EW/NS) × cars on the green axis'
  detectors (`count`, 6 buckets) × stopped cars on the red axis (`queue`, 6 buckets) × seconds
  of green (4 buckets).
- **Reward** per 5 s tick and junction: `r = −(stopped cars on all four approaches) / 10`,
  and `−0.2` when it switches (discourages dithering; the queue term already prices the lost time).
- **Update** — a decision lasts *k* ticks until the junction can decide again (a switch blocks
  it through yellow, all-red and min green), so we use the semi-MDP form:

  ```
  Q(s,a) ← Q(s,a) + α [ R + γ^k max_a' Q(s',a') − Q(s,a) ],    R = Σ_{i<k} γ^i r_i,  γ = 0.9 per tick
  ```
- **Action mask** (rules, not learned): never switch to an empty street; always switch after
  60 s of green if the other street waits. Safety stays with the supervisor.
- **Training** (`rl_train.py`): batch Q-learning with experience replay. Each round runs two
  episodes in parallel with the current table (ε-greedy, ε 0.3 → 0.02; rush hour with a fresh
  seed ≥ 1000 and demand × U(0.85, 1.15)), keeps the last 10 episodes in a replay buffer and sweeps
  it 3 times (α = 0.1). Episodes run in `fast_env.TrainEnv`, which reads the sensors only on the
  5 s decision ticks — exactly what the controller looks at anyway.
- **Artifact**: `models/rl_qtable.json` with the Q-values, feature definition, training curve
  and a SHA-256 checksum; loading refuses a modified file or a feature mismatch. A missing file
  gives a clear "train it first" error.
- **Upgrade path**: [SUMO-RL](https://github.com/LucasAlegre/sumo-rl) (Gymnasium environments for
  SUMO) with a neural policy (DQN / PPO via stable-baselines3) and richer state (per-lane queues,
  downstream occupancy, neighbours' phases). Our observation/action contract maps directly onto
  a Gymnasium env; we kept tabular Q-learning so it runs with the current requirements.

**What it learned** (greedy action per state in `models/rl_qtable.json`): on the arterial
(EW) green it keeps the green while 3 or more cars are still on the detectors and switches
once the platoon has passed and cross-street cars are stopped; on the cross-street (NS) green
it gives the green back as soon as a few arterial cars are stopped — an actuated-like rule
learned from reward alone. Training: 60 episodes × 1800 s, 2 workers, 10.2 min. Mean delay
went from 91 s with the empty table to ~30 s after 10 episodes and then stayed flat (noisy,
because every episode has a new seed and demand scale); the curve is in `meta.curve`.

## Results on rush hour

Setup: `rush_hour` (eastbound morning peak, ramps up to its peak at 1800 s), seeds 1 and 2,
900 s warm-up, measured until 2700 s, coverage 100 % (scenario default). Every controller sees
identical cars for a given seed. `ai_recommender`: `auto_approve=True`, search at 600 s, 30
trials. `rl`: the committed table (trained on seeds ≥ 1000, so these seeds are held out).
**All 20 runs: 0 controller errors, 0 fallback steps, 0 rejected actions.**

| Controller | Mean delay (s/veh) | p95 travel time (s) | Unfinished trips | Stops/veh | Switches | Delay per seed (1, 2) |
|---|---:|---:|---:|---:|---:|---|
| `max_pressure` | **29.7** | 168.0 | 127.5 | 1.05 | 402 | 30.0, 29.4 |
| `rl` | 30.9 | **166.5** | 130.0 | 1.05 | 394 | 30.9, 30.9 |
| `actuated` | 33.3 | 178.3 | 129.5 | 1.29 | 487 | 32.1, 34.4 |
| `ai_recommender` | 35.8 | 177.5 | 135.0 | 1.16 | 323 | 38.3, 33.3 |
| `max_pressure_probe` | 42.7 | 191.5 | 155.5 | 1.23 | 314 | 41.2, 44.3 |
| `coordinated` | 48.2 | 253.5 | 152.5 | 1.17 | 241 | 46.8, 49.6 |
| `fixed_time` (baseline) | 69.4 | 259.0 | 177.5 | 1.55 | 240 | 67.7, 71.1 |
| *variants that explain the defaults* | | | | | | |
| `max_pressure`, `measure="queue"` (stopped cars only, the literal spec) | 82.5 | 382.8 | 262.5 | 3.67 | 612 | 71.4, 93.5 |
| `max_pressure`, `down_measure="count"` | 32.7 | 185.0 | 132.5 | 1.06 | 418 | 31.7, 33.7 |
| `max_pressure_probe`, `down_measure="count"` | 64.2 | 278.6 | 182.0 | 2.63 | 574 | 56.9, 71.6 |

"Unfinished" counts trips that departed in the window but had not arrived by 2700 s — mostly the
last few minutes' departures, the same for every controller, plus congestion.

How to read it (two seeds: treat differences under ~3 s as noise):

- Every adaptive controller roughly **halves fixed-time's delay** (69 → 30–36 s) and cuts the p95
  travel time by about a third. The 90 s, 50/50 plan gives the cross streets far more green than
  they need; even the coordinated green wave (48 s) wins mostly through its 60/40 split.
- `max_pressure` and `rl` are the best and practically tied. RL learned a good actuated-like
  rule in 10 minutes but does not beat a good hand-written rule — expected for a tabular policy.
- `ai_recommender` applies one fixed plan, so it cannot react cycle by cycle like the adaptive
  controllers; it still removes 48 % of the delay, close to what its own model predicted (52–54 %).
  Most of that gain comes from the Webster seed plan (60–65 s cycle, demand-proportional splits):
  in one search the Webster + green-wave seed was the best trial, in the other 30 TPE trials beat
  it by 7 % (model objective). It searched at 600 s, when demand was ~80 % of the peak.
- `max_pressure_probe` is worse than the detector version even at 100 % coverage: probe counts
  cover the whole 285 m link, not just the last 100 m, so "cars waiting" includes cars still far
  from the stop line.
- The variants: stopped-cars-only pressure is the worst controller of all (it flip-flops: 612
  switches), and counting *moving* cars downstream made the probe version flip-flop too.

**Sampling bias, first look** (AI recommender, seed 1, same setup, only the probe share changes):

| Coverage | Real mean delay (s/veh) | Recommended plan | J2 north / south estimate (veh/h) |
|---:|---:|---|---|
| 100 % | 38.3 | 65 s cycle, EW share 0.65–0.81 | 172 / 166 |
| 25 % | 36.4 | 60 s cycle, EW share 0.56–0.79, green wave | 121 / 161 |
| 10 % | 37.8 | 60 s cycle, EW share 0.57–0.85, green wave | 31 / 403 |

At 10 % single cross streets are off by a factor of 2–6 (each probe stands for 10 cars), yet the
real delay does not move: the plan still lands on the 60 s minimum cycle with a green wave, and
the heavy arterial — estimated well even from few probes — dominates. So on *this* demand the
recommendation is robust to coverage; a scenario with balanced or near-capacity cross streets,
and more seeds per coverage level, is the real sampling-bias experiment (TODO, with Doyoung).

Reproduce one row: `python -m teamb run --scenario rush_hour --controller max_pressure --seed 1 --end 2700`
(the AI recommender needs `controller_params={"auto_approve": True}` through `SimEnv`, or the
twin's approve button).

## Parameters a teammate can tune

| Controller | Parameter (default) | Effect |
|---|---|---|
| all adaptive | `min_green` (10), `max_green`, `interval`, `max_obs_age` (10 s) | shortest/longest green this controller asks for; decision period; when data counts as stale |
| `actuated` | `gap_out` (3.0 s), `max_green` (50 s) | shorter gap → snappier switching, longer → fewer switches |
| `max_pressure` | `measure` ("count"), `down_measure` ("queue"), `weighted` (False), `margin` (2 cars), `interval` (5 s), `max_green` (90 s), `source` ("detector"), `defense` (False) | bigger margin → fewer switches; `source="probe", defense=True` → probe-based but defended |
| `ai_recommender` | `search_at` (600 s), `trials` (30), `eval_horizon` (900 s), `eval_warmup` (300 s), `window_s` (300 s), `auto_approve` (False), `sync` (auto), `defense` (False), `cache` (True), `approval_token` (None) | more trials → better plans, slower; longer window → smoother demand estimate but slower to react |
| `rl` | `model_path`, `interval` (5 s), `min_green` (10 s), `max_green` (60 s); training: see `python -m teamb.controllers.rl_train --help` | the bins in `rl.py` define the state; change them → retrain |

Pass them from code with `SimEnv(..., controller_params={...})` or in experiment configs.

## Threat model and defenses

The attacker can send data into the system but cannot change the code. Signals are never at
risk of conflicting greens — the supervisor and the env's SIG-01 guard check every state — so
the threats below are about *efficiency* and *trust*, plus the operator workflow.

| Threat | Example | What it hits | Defense in the prototype | Not yet |
|---|---|---|---|---|
| Spoofed probe reports | 99 phones in a handcart fake a jam (Berlin 2020); `start_attack` | `max_pressure_probe`; the AI recommender's demand model (queue-growth term) | sensors' cross-check (`trusted: false`); `ObservationGuard` rejects probe numbers that exceed the lanes' storage; `defense=True` uses detectors there / drops the samples | small attacks that stay inside both limits; Sybil-resistant probe identities |
| Replayed telemetry | an old observation sent again | any adaptive controller | timestamps must not go backwards → "replayed" → fixed-time fallback | per-message nonces and signatures |
| Stale data | frozen feed, server lag, cut cable | any adaptive controller | observation older than `max_obs_age` → fixed-time fallback | detector health monitoring |
| Spoofed or failed detectors | a loop stuck "occupied" | actuated, max-pressure, RL | `max_green` caps every green, so nobody waits forever | cross-checking detectors against probes in the other direction |
| Model tampering | edited `rl_qtable.json` | `rl` | SHA-256 checksum + feature check on load | real signatures (key outside the repo), model registry |
| Unauthorized commands | someone approves a plan | `ai_recommender` | `approval_token`, id check (only the pending plan), audit log | user roles and authentication in the twin |
| Controller crash / overload | exception, slow search | everything | env falls back to fixed-time on exceptions or > 0.25 s; heavy search runs in a worker process; the supervisor rejects malformed actions | — |
| Privacy | tracking individual phones | probe data | controllers only see per-approach aggregates (counts, estimates), never vehicle ids | retention limits, k-anonymity thresholds at low coverage |

How to show it: run `fake_data_attack` (attack on J2's north approach from 1500 to 3300 s) with
`max_pressure_probe`, then with `max_pressure` + `{"source": "probe", "defense": true}`.
Result (seed 1, coverage 25 %, 99 phantom cars on J2's north approach from 1500 s, measured
900–2700 s):

| Controller | Mean delay (s/veh) | p95 travel time (s) | Unfinished trips |
|---|---:|---:|---:|
| `max_pressure` (loop detectors) | 29.9 | 172.0 | 137 |
| `max_pressure` `{"source": "probe", "defense": true}`, under attack | 41.0 | 192.0 | 153 |
| `max_pressure_probe`, same scenario **without** the attack | 45.1 | 206.0 | 150 |
| `fixed_time` | 67.5 | 259.0 | 176 |
| `max_pressure_probe`, under attack | **95.9** | **527.8** | **465** |

The attack more than doubles the blind controller's delay (45 → 96 s) and triples the unfinished
trips — it ends up far worse than fixed-time, because J2 keeps serving phantom cars on the north
approach while the arterial backs up. With `defense=True` the same controller ignores that
approach's probe numbers (flagged by the cross-check, and 396 cars cannot fit on a 232 m street),
uses the loop detector there, and ends at 41 s — slightly better than the blind controller
*without* the attack, because the same checks also drop implausible readings at 25 % coverage.
Detector-based max-pressure is not affected at all. `tests/test_controllers.py` checks the same
behaviour in a 300 s run.

## Known limitations

- One synthetic corridor and two seeds: the numbers are relative comparisons, not predictions
  for a real road. Use the experiment runner for 10+ seeds and paired statistics before quoting
  a percentage on a slide.
- Detectors see only the last 100 m before the stop line. Longer queues are invisible to
  actuated, max-pressure and RL, so under heavy oversaturation they under-react.
- AI recommender: one common cycle and a two-phase plan (no protected lefts); it plans for the
  demand it saw (searching at 600 s sees about 80 % of the rush-hour peak), with constant flows
  in the model; every candidate is scored on one demand seed, so the winner can be lucky on that
  draw (the TODO is to re-check the top plans on more seeds).
- Turning estimates come only from net volume changes along the arterial; the model cannot tell
  a left from a right turn.
- The AI recommender's demand model is hard to fool with *parked* phantom phones: flows come from
  probes that cross the stop line, which parked phones never do. It is exposed only through the
  queue-growth term, when an attack starts inside the estimation window. A smarter attacker who
  fakes moving phones would get through — that needs trajectory-level plausibility checks.
- RL: tabular, coarse state, one scenario, no coordination between junctions, not tested on
  shifted demand; treat it as a teaching baseline, not a production policy.
- Defense thresholds can be evaded by small attacks (a few phantom cars stay under both the
  cross-check and the storage limit); detectors themselves are trusted; the model checksum is
  not a signature and `approval_token` is a stand-in for real authentication.

## TODO

- **MPC**: queue dynamics `q(t+Δt) = q + arrivals − departures` with storage limits, a short
  demand forecast, optimise the next few switches subject to min/max green (role doc, Advanced 1).
- **MARL / neighbour-aware RL**: CoLight-style coordination, or at least the neighbours' phase and
  downstream occupancy in the state; DQN/PPO through SUMO-RL.
- **Better demand estimation**: turning ratios from probe trajectories, time-of-day profiles,
  shrinkage towards historical counts at low coverage (`queue_est_adj` / `penetration_est` from the
  sensors are a first step), and a coverage sweep (10/25/50/75/100 %) as the sampling-bias experiment.
- **AI recommender**: search a narrower space around the Webster plan (most of the gain comes
  from it, and 30 trials in 8 dimensions barely refine it), re-optimise on a schedule (time-of-day
  plans), evaluate the winner on extra seeds before recommending it, and report uncertainty
  (spread over seeds) with the expected gain. A search takes 31 short simulations — about 2 min
  on an idle laptop, 7–8 min on our heavily loaded test machine; `trials` is the speed knob, and
  the cache makes repeated demos instant.
- **Security**: signed models and messages, detector health checks, an attack sweep (number of
  phantom cars, approach, coverage) to find where the defense stops working.
- **Evaluation**: more seeds and paired statistics (with Doyoung's experiment runner), off-peak and
  event scenarios, inference latency.

## Requests to the integrator (core changes I worked around)

1. **Controller events in SimEnv.** The AI recommender collects `recommendation_ready` /
   `plan_applied` / `recommendation_failed` events (`controller.drain_events()`). The twin session
   already merges them into frames, but headless runs never see them in `env.events`. Suggestion:
   merge `controller.drain_events()` (if present) in `SimEnv.step`, or pass a `log_event`
   callback in `reset`.
2. **A hook outside the 0.25 s budget.** The sync search runs in `log(step)` because it is the
   only hook called outside the timed `_ask`. Please keep it that way, or add an explicit
   `controller.after_step(t)` for heavy work.
3. **A "plan evaluation" mode for SimEnv.** `fast_env.py` swaps `env.sensors` after `start()` and
   wraps `metrics._sample` (a private method) to make plan-search and training runs cheaper. A
   `SimEnv(..., sensors=False, live_kpis=False)` option would remove that coupling — and would
   also skip the sensor feed's per-step TraCI subscriptions, which now cost about a quarter of a
   plan-evaluation run (profiled) although nobody reads them there.
4. **Controller summary in the run summary.** Experiments would like the AI recommendation, the
   defense counters (`guard.rejected`) and RL decision counts in `summary.json`; e.g.
   `summary["controller_info"] = controller.summary()` when the method exists.
