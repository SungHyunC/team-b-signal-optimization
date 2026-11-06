# Team B — Traffic Signal Optimization with Mobility Data and AI

2026 Crimson Silicon Valley SW·AI Leaders Program · Korea University Sejong × CSU East Bay

A SUMO-based **digital twin** of a four-junction corridor. Cars and signals move live in 3D, and
you can switch between signal-control methods, send an ambulance through, flood a road or feed
the AI fake navigation data — then compare the numbers with paired, reproducible experiments.
SUMO 기반 4교차로 **디지털 트윈**입니다. 차량과 신호가 3D로 실시간 움직이고, 신호 제어 방식을 바꾸거나
구급차 출동·도로 침수·가짜 내비 데이터 공격을 걸어 보면서 결과를 비교할 수 있습니다.

**▶ Online demo: https://sunghyunc.github.io/team-b-signal-optimization/** — 13 recorded runs
(rush hour, ambulances, flood, earthquake, fake-data attack, …) replayed in the browser, on phones too.
설치 없이 브라우저(휴대폰 포함)에서 녹화된 시뮬레이션 13개를 바로 볼 수 있습니다.
The page switches between **English and 한국어** (top bar, or `?lang=ko`). 상단의 EN | 한국어 버튼으로 언어를 바꿀 수 있어요.

| Where | What it is |
|---|---|
| [Online demo](https://sunghyunc.github.io/team-b-signal-optimization/) (GitHub Pages) | Prerecorded runs replayed in the browser; it does not run SUMO |
| [Scenario Sandbox](https://sunghyunc.github.io/team-b-signal-optimization/static/sandbox.html) (GitHub Pages) | Build a scenario, export it as JSON, get the exact command to run it; no simulation in the browser |
| Cloud live SUMO (Render) | Real SUMO streamed over WebSockets: one **shared**, password-protected session for a small group, not one simulator per visitor. See the [deployment guide](docs/cloud-live-sumo-deployment.md) |
| Your machine | Everything: `teamb twin` runs the live twin locally, `teamb exp run` the experiments |

![An ambulance gets a green path at J2 while max-pressure runs the corridor](docs/img/twin-emergency.jpg)

![A flood closes the eastbound arterial between J2 and J3; traffic detours over the back street](docs/img/twin-road-closure.jpg)

> The program only requires the five activity reports; this prototype is optional and backs
> Report 3 (problem definition) and Report 5 (results sharing) with results we actually ran.
> Network sizes, timings and demand are design assumptions from Aditya's reference design,
> not field-calibrated values.

## Results

**Validated (30 paired seeds per cell, 540 strict-valid runs).** Mean delay reduction of
`max_pressure` versus `fixed_time` (reduction of group means; synthetic demand, SUMO 1.28.0):

| Demand | Rush hour | Emergency | Road closure |
|---|---:|---:|---:|
| 75 % | 59.5 % | 58.2 % | 56.7 % |
| 100 % | 65.0 % | 66.4 % | 22.4 % |
| 125 % | 60.4 % | 58.4 % | **1.8 % (inconclusive)** |

At 125 % demand with the road closed, the paired 95 % interval of the benefit spans zero
(2.25 s/veh, [−3.14, 7.65]); max-pressure finishes more trips there but shows more confirmed
spillback. Intervals, unfinished trips and spillback for every cell are in the
[robustness review](docs/robustness-and-sensitivity-review.md). The data behind the table is
committed: [100 % study](docs/results/studies/baseline-180/README.md),
[75 % / 125 % study](docs/results/studies/robustness-360/README.md).

**A rejected improvement.** A spillback-aware max-pressure variant looked promising on three
calibration seeds, then was tested on 30 fresh seeds (360 runs). It cut 125 % closure delay
(120.8 → 107.0 s/veh) but raised heavy rush-hour delay by 14.0 % and heavy emergency delay by
11.7 %, failing the preregistered 5 % regression guard, so it was **rejected** and is not on `main`.
See the [confirmation decision](docs/independent-controller-confirmation-review.md) and its
[data](docs/results/studies/confirmation-360/README.md).

**First pilot** (3 paired seeds, all controllers; full tables in [`docs/results/`](docs/results/README.md)):

| Controller | Rush hour delay (s/veh) | vs fixed-time | Flood closure delay | Fake-data attack delay |
|---|---:|---:|---:|---:|
| fixed_time | 71.0 | — | 119.6 | 79.5 |
| coordinated | 48.4 | −31.8 % | | |
| ai_recommender | 37.6 | −47.0 % | | |
| actuated | 30.7 | −56.7 % | 83.8 | |
| rl | 30.6 | −56.7 % | 170.2 (unstable) | |
| max_pressure | 29.2 | −58.7 % | 94.7 | 29.4 |
| max_pressure_probe (navigation data only) | | | | 175.6 → 48.2 with the detector cross-check |

Two lessons for Report 3: the RL controller, trained only on rush hour, breaks down when a road
floods; and a controller that trusts navigation data alone can be steered by fake reports unless
it cross-checks the loop detectors. Emergency vehicles cross the corridor in ≈ 90 s instead of 110 s.

## Install

Python 3.10+ (CI and the Docker image use 3.11). The `eclipse-sumo` package brings the SUMO
binaries, so no separate SUMO install is needed, except a few system libraries on minimal Linux.

```bash
git clone https://github.com/SungHyunC/team-b-signal-optimization.git
cd team-b-signal-optimization
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"            # teamb + SUMO 1.28.0 + test tools
teamb doctor                       # checks Python, SUMO, the network and a 120 s smoke run
teamb twin                         # open http://127.0.0.1:8000
```

Optional extras, combinable as `pip install -e ".[dev,fast,cloud]"`:

| Extra | Adds | For |
|---|---|---|
| `dev` | pytest, httpx | running the tests |
| `fast` | `libsumo==1.28.0` | in-process SUMO instead of a TraCI socket (same numbers, about 2x faster). `teamb exp run` and `teamb sandbox run` use it automatically when it is installed; `--traci-backend libsumo\|auto\|traci` on `teamb run` or `teamb exp run`, or `TEAMB_TRACI_BACKEND=libsumo\|auto\|traci`, chooses it elsewhere or overrides it (`auto`: libsumo if installed, else TraCI). SimEnv, `teamb run` and the twin default to TraCI. |
| `cloud` | `modal` | `teamb exp run --backend modal` (run `modal setup` once) |

Per operating system:

- **Debian/Ubuntu, WSL, slim containers:** the pip-provided SUMO binary needs
  `sudo apt-get install -y libgl1 libglib2.0-0 libgomp1 libxrender1` (the same packages as the
  Dockerfile; a missing `libXrender.so.1` is what broke the first Render deploy). `teamb doctor` reports it.
- **macOS:** works as is on Apple Silicon and Intel. With a python.org installer, run its
  *Install Certificates* command once if `teamb vendor` fails with a certificate error.
- **Windows:** use the PowerShell venv above (or `py -3.11` instead of `python`). JSON options
  such as `--scenario-params` are easiest from a Scenario Sandbox file:
  `teamb sandbox run team-b-scenario.json`. See the [Windows walkthrough](docs/final-project-handoff.md#reproduce-on-windows-powershell).

`pip install -r requirements.txt` (runtime) or `-r requirements-dev.txt` (with test tools) still
works without installing the package; then use `python -m teamb ...`. `requirements.lock` pins
every package for the Docker image and CI (`pip install -e ".[dev]" -c requirements.lock`).
Use an editable (`-e`) install: results and models are read from and written to the checkout.

## Commands

Everything is one command, `teamb` (also `python -m teamb`). `teamb <command> --help` lists the options.

| Command | What it does |
|---|---|
| `teamb doctor [--skip-sim]` | Check the installation: Python, packages, SUMO binaries, network, smoke simulation, optional extras |
| `teamb twin [--port 8000]` | Live 3D digital twin at http://127.0.0.1:8000, Scenario Sandbox at `/static/sandbox.html`, signal-data API at `/api/v1/spat` |
| `teamb list` | Available controllers and scenarios |
| `teamb run --scenario emergency --controller max_pressure` | One headless run; summary printed, outputs in `results/runs/` |
| `teamb exp run --name demo ...` | Batch experiment over scenarios × controllers × seeds, then a paired report |
| `teamb exp report --name demo` / `teamb exp list` | Rewrite the report / list experiments in `results/experiments/` |
| `teamb impact results/experiments/demo` | Impact and cost-benefit table of an experiment |
| `teamb diagnose results/experiments/demo` | Read-only controller failure diagnosis of an experiment |
| `teamb sandbox validate FILE` / `teamb sandbox run FILE` | Check a Scenario Sandbox export and print its command / run it in SUMO with a report |
| `teamb train-rl` | Train the tabular Q-learning controller (writes `models/rl_qtable.json`); `--scenarios` and `--demand-range` mix scenarios and demand per episode, `--backend modal --workers N` runs the episodes on Modal |
| `teamb site build\|serve\|deploy` | Record the online demo, preview it, publish it to GitHub Pages |
| `teamb vendor` | Save three.js locally so the twin works offline (before a presentation) |
| `teamb build-net` | Regenerate the SUMO network (done automatically on first use) |

A paired experiment, its report and the impact table:

```bash
teamb exp run --name demo --scenarios rush_hour --controllers fixed_time,max_pressure --seeds 1-3 --workers 2
teamb exp report --name demo       # → results/experiments/demo/report.md
teamb impact results/experiments/demo
```

The same matrix on [Modal](https://modal.com) cloud containers, one SUMO per container (needs the
`cloud` extra and `modal setup`). Keep every run of one comparison on the same backend:

```bash
teamb exp run --name demo_cloud --scenarios rush_hour --controllers fixed_time,max_pressure --seeds 1-30 --backend modal --workers 32
```

In the twin, URL parameters jump straight to a demo moment, e.g.
`http://127.0.0.1:8000/?scenario=emergency&controller=max_pressure&start=1170&speed=2&camera=J1`.

The older module commands (`python -m teamb.experiments run ...`, `python -m teamb.analysis.impact`,
`python -m teamb.twin.site deploy`, …) still work and appear in some documents; they are the same
programs as the `teamb` subcommands.

## Tests and CI

```bash
pytest                            # whole suite, a few minutes (bare pytest works without installing)
pytest -m "not sumo"              # quick tier: skips tests that start a SUMO simulation
node --test tests/js/*.test.mjs   # browser-side unit tests (Node 20.6+, no npm install)
```

[CI](.github/workflows/ci.yml) runs on every pull request and push to `main`: install from the lock,
`teamb doctor`, the full test suite, `node --check` on all JavaScript, the Node tests, one
strict-valid SUMO run, and the production Docker image (non-root, health check, access gate, SUMO
inside the container). The 30-seed research studies are separate, manually dispatched workflows
in [.github/workflows/](.github/workflows/).

## What's inside

**Signal controllers** (`teamb/controllers/`), all behind the same safety supervisor:

| Name | Method | Role in the plan |
|---|---|---|
| `fixed_time` | same 90 s timing every cycle | baseline |
| `coordinated` | fixed-time with green-wave offsets | baseline |
| `actuated` | extends green while loop detectors see cars | baseline |
| `max_pressure` | green to the axis with the biggest queue imbalance | strong baseline |
| `max_pressure_probe` | max-pressure on navigation data only (security test) | security |
| `ai_recommender` | Optuna searches cycle/splits/offsets on a model built from navigation data → engineer approves → applied (Google Green Light style) | core |
| `rl` | Q-learning controller trained in SUMO (Busan-style real-time control) | stretch |

**Scenarios** (`teamb/scenarios/`, details in [`docs/scenarios.md`](docs/scenarios.md)):

| Name | What happens |
|---|---|
| `rush_hour` | morning peak, heavy eastbound arterial (ramps up, peaks 25 min, eases off) |
| `off_peak` | light night traffic with more trucks |
| `special_event` | a stadium north of J3 empties onto one cross street |
| `emergency` | 10 ambulances/fire trucks from every side during the peak |
| `road_closure` | a flash flood closes the arterial J2 → J3 for 30 min; detour over the back street |
| `sinkhole_cross` | a sinkhole closes the cross street north of J2 |
| `earthquake` | several closures plus emergency response |
| `fake_data_attack` | 99 fake "phones" report a jam on J2's north approach (2020 Berlin case) |

**How the prototype tests our three questions from Report 1**

| Question | Experiment |
|---|---|
| Sampling bias — is navigation data enough? | vary probe coverage 10/25/50/75/100 % (and biased sampling) and compare the AI recommender's plan and the metrics |
| Spillover — does fixing one junction clog the next? | four connected junctions; road-closure scenario measures how far and how long queues spread |
| Measuring impact fairly | same seeds for every controller → paired A/B comparison with 95 % confidence intervals; unfinished trips always reported |

**Safety first:** controllers only *propose* a green direction. The independent supervisor
(`teamb/safety/`) enforces minimum green, yellow and all-red, rejects invalid proposals, gives
emergency vehicles a green path, and falls back to fixed-time if a controller fails.

**Signal-data API** for navigation apps (like Busan's): `GET /api/v1/spat` and friends while the twin runs.

## Repository map

| Path | What | Owner |
|---|---|---|
| `teamb/network/`, `teamb/sim/`, `teamb/safety/`, `teamb/twin/` | SUMO network, simulation loop, safety supervisor, 3D digital twin | Seong Hyeon |
| `teamb/sensors/`, `teamb/evaluation/`, `teamb/experiments/` | loop detectors & navigation probes, metrics, batch experiments & statistics | Doyoung |
| `teamb/controllers/` | actuated, max-pressure, AI recommender, RL, fake-data defense | Yunseong |
| `teamb/scenarios/`, `teamb/demand/`, `teamb/api/`, `teamb/analysis/` | scenarios & demand, signal-data API, impact & cost-benefit | Aditya (with Doyoung) |
| [`docs/`](docs/README.md) | documentation hub: architecture, role guides, deployment, research reviews, study data, program documents | everyone |

## Limitations

- **Synthetic, not field-calibrated.** Network geometry, signal timings, demand and route choice
  are design assumptions. All numbers are SUMO simulation outcomes on that model, not measured
  road-network benefits.
- **Completed-trip delay can mislead on its own.** A controller can trade delay against finished
  trips; read delay together with unfinished share, throughput and spillback (the reports do).
- **The heavy-closure case is unresolved:** at 125 % demand with the closure, max-pressure's gain is
  inconclusive, and the spillback-aware fix was rejected for regressions elsewhere.
- **The pilot table uses 3 seeds** and the RL controller was trained on rush hour only; it is
  unstable under closures.
- **The cloud service is one shared session** with a single access password: visitors can
  interrupt each other, and it has had no load test. Simulation results on it are lost on redeploy.
- **Only editable installs are supported** (`pip install -e .`), because results, models and the
  generated network live in the checkout.

## License

No license has been chosen yet; the team will decide. Until then the default applies: the code
and documents may be read here, but reuse needs the authors' permission. Third-party software
keeps its own license: SUMO (`eclipse-sumo`, `traci`, `sumolib`, `libsumo`; EPL-2.0), three.js
(MIT; loaded from a CDN or saved by `teamb vendor`), FastAPI (MIT), Optuna (MIT).

## Team

| Member | Role |
|---|---|
| Joshua (Seong Hyeon) Kim | Software & integration, team lead |
| Doyoung Lee | Data & evaluation |
| Yunseong Lee | AI & security |
| Aditya Tirunagaru | Scenario design, impact & cost-benefit analysis |

Program documents (topic, activity reports, research report, prototype plan) and the trip
schedule are listed in the [documentation hub](docs/README.md#program-documents).
