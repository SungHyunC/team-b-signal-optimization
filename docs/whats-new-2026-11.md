# What changed in November 2026: one project, checked and faster

This release turns the prototype into one installable project, fixes the defects a full review
found, makes simulations several times faster, and adds a controller that beats max-pressure
under the team's own regression rule. Every number below can be re-checked with the commands in
the linked documents.

## One project

- `pip install -e ".[dev]"` installs everything, including SUMO 1.28.0 (the version behind every
  published result); extras `fast` (libsumo) and `cloud` (Modal).
- One command, `teamb`, for everything: `doctor`, `twin`, `run`, `exp run|report|screen|list`,
  `impact`, `diagnose`, `sandbox validate|run`, `train-rl`, `site`, `vendor`, `build-net`. The old
  `python -m teamb.…` commands still work.
- `teamb doctor` checks Python, SUMO, the network and a 120 s smoke run.
- One CI workflow on every pull request and push to `main` (full test suite, JavaScript checks and
  tests, a strict SUMO run, the production Docker image). Study workflows run on demand only.
- A [documentation hub](README.md) with working links (a test checks every relative link), and
  the aggregate data of the 30-seed studies committed before their Actions artifacts expire.

## Correctness (about 180 verified review findings fixed)

Highlights, grouped by what they protect:

- **Experiment results.** A run that crashed or was interrupted used to leave a normal-looking
  `summary.json` that resume, the report and `--strict-validation` all accepted. Runs now count as
  finished only when they reached their end time; results are written atomically; resume checks
  that a folder holds exactly the requested run (end time and exact coverage are part of the run
  name); report rows never pair runs with different run ends or preemption settings; one shared
  t-interval implementation serves the report, the impact table and the diagnosis.
- **Impact and cost-benefit.** No double counting of scenario variants or overlapping disruptions,
  entry waits and in-flight trips priced consistently, CO2 value converted to the same dollar year,
  aborted runs never priced.
- **Simulation.** Failures no longer leak SUMO processes or hide the original error; the EV that
  preempts a junction is chosen by rule, not by set order; closures that would strand a trip are
  refused instead of crashing SUMO; trips leaving right after a reopening are routed on free-flow
  weights.
- **Security.** An absolute path in `/vendor/three/…` could read any file the server could read
  (fixed and tested); the AI approval token no longer reaches clients; the WebSocket checks its
  Origin; bounded queues and EV counts; the Docker image runs as a non-root user without test tools.
- **Fake-data defence.** The detector cross-check now catches a 20-phone attack on a busy approach
  (trusted share during the attack 89.5 % → 2.1 %, first alert after 2 s instead of 100 s) with no
  false alarms in any normal-traffic scenario tested.
- **Frontend.** Reloading a shared live twin no longer restarts the run; the replay demo reaches
  "finished" and reports download errors; three.js resources are disposed; the sandbox page fetches
  its lists from the server and both command lines it shows reproduce the same run.

Changes that move published numbers are listed at the end.

## Faster

| | Before | Now |
|---|---:|---:|
| SUMO start | 1.05 s (fixed sleep in `traci.start`) | 0.15 s |
| TraCI round trips per simulated second | 6.8 | 2.8 |
| Full rush-hour run, TraCI socket | 12.1 s | 9.0 s |
| Full rush-hour run, libsumo (`pip install -e ".[fast]"`) | – | 6.1 s, byte-identical outputs |
| Tests | 123 in 130 s | 633 Python + 69 JavaScript in about 110 s (`pytest -m "not sumo"`: 542 in about 15 s) |

Batch experiments use libsumo automatically when it is installed and default to one worker per
core. `teamb exp run --backend modal --workers N` runs a matrix on Modal cloud containers, one
SUMO per container, with the same resume and audit rules as local runs.

## Better controllers

- **`max_pressure_plus`** (max-pressure with lost-time-aware hysteresis, rho = 0.25) passed the
  prespecified regression screen against `max_pressure` in all 21 conditions of a fresh 30-seed
  confirmation (7 scenarios × demand 0.75/1.0/1.25). See the
  [controller confirmation](results/studies/controller-confirmation-2026-11/README.md).
- **`teamb exp screen`** turns the team's decision rule from the spillback study into a command.
- **RL retrained** on 7 scenarios and varied demand (13,600 training episodes across four
  candidates; the best was selected on held-out seeds) with a max-pressure fallback in states it
  has rarely seen. The flood no longer breaks it; the earthquake remains its weak spot. See the
  [RL retraining study](results/studies/rl-retraining-2026-11/README.md).

## Changes that move published numbers

- Closure scenarios (road_closure, sinkhole_cross, earthquake): trips that depart right after a
  reopening are routed on free-flow weights, so their delays differ from the earlier studies, which
  remain valid for the code they ran on.
- `rl` uses the retrained model and a low-confidence fallback by default; the first model with its
  original behaviour is `{"model_path": "models/rl_qtable_v1_rush_hour.json", "fallback_min_visits": 0}`.
- Impact and cost-benefit numbers change (entry waits, in-flight trips, CO2 dollar year,
  annualization once per scenario).
- New run names when `--end` is given (`__e<seconds>`) or coverage is fractional; old folders of
  the same run are adopted on resume.
- The fake-data cross-check flags smaller attacks, which changes alert metrics and the decisions of
  probe-based controllers with the defence on.
- `max_pressure`, `fixed_time`, `actuated` and the other controllers keep their behaviour; rush hour
  seed 1 still gives 76.02 s/veh (fixed-time) and 31.81 s/veh (max-pressure).

## Open items for the team

- **License.** The repository has none (all rights reserved by default). Choose one together.
- **Raw study artifacts** expire on Nov 18–19, 2026. Only aggregates are committed; attach the
  artifact zips to a GitHub Release if the per-run folders should survive.
- **Branches.** Several merged feature branches and draft PR #5 can be closed or tagged.
- **Python 3.10.** The package supports 3.10+; CI tests 3.11 only.
