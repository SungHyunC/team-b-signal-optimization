# Final Project Handoff — Team B Traffic Signal Optimization

> **Update, November 2026:** a later 3,780-run confirmation promoted `max_pressure_plus` (passes the same
> 5 % regression rule in all 21 conditions) and retrained the RL controller. See
> [what changed](whats-new-2026-11.md) and the [controller confirmation](results/studies/controller-confirmation-2026-11/README.md).

**Status:** Research prototype and local sandbox **implemented and tested**. [Sandbox integration PR #6](https://github.com/SungHyunC/team-b-signal-optimization/pull/6) is merged into `main`. Experimental general-purpose spillback-aware controller **rejected** and retained only in [draft research PR #5](https://github.com/SungHyunC/team-b-signal-optimization/pull/5).

## Deliverables and readiness

| Deliverable | Final status |
|---|---|
| Four-junction SUMO corridor, controllers, events, safety supervisor | Implemented |
| Live local digital twin at `http://127.0.0.1:8000/` | Implemented; local Windows launch observed by project reviewer |
| Scenario sandbox at `http://127.0.0.1:8000/static/sandbox.html` | Implemented; local page opened and inspected |
| Scenario JSON validation/export/import and reproducibility command | Implemented; automated contract tests passed, full user interaction matrix not independently recorded |
| GitHub Pages prerecorded demo | Available at https://sunghyunc.github.io/team-b-signal-optimization/; **not** a hosted SUMO execution backend |
| 180-run nominal baseline, 360-run robustness, 360-run independent controller confirmation | Completed; inspect run artifacts and reports |
| Sandbox CI for release branch | [Success #41973492051](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41973492051); includes real strict-valid short SUMO smoke |
| Independent experiment findings | [Engineering review](final-engineering-review.md); [rejected controller decision](independent-controller-confirmation-review.md) |
| Presentation-ready study narrative | [Final presentation brief](final-presentation-brief.md) |

## Reproduce on Windows PowerShell

These commands work around machines that have Python 3.11 installed with the `py` launcher but no `python` executable on PATH. Skip `git clone` if the folder already exists.

```powershell
git clone https://github.com/SungHyunC/team-b-signal-optimization.git
cd team-b-signal-optimization
py -3.11 -m pip install -e ".[dev]"   # teamb, SUMO 1.28.0 and the test tools
# Make SUMO command-line executables visible for this PowerShell session if necessary:
$env:Path += ";$env:LOCALAPPDATA\Programs\Python\Python311\Scripts"
py -3.11 -m pytest tests/test_sandbox.py tests/test_sandbox_http.py -q
py -3.11 -m teamb twin
```

Open `http://127.0.0.1:8000/static/sandbox.html` **on the same computer**. In the sandbox, choose `road_closure`, controller `max_pressure`, demand `1.25`, seed `33`, preemption enabled; export JSON and re-import it to verify round-tripping. Use the reproduced experiment command to execute SUMO separately. Stop the local server by returning to the server's terminal and pressing **Ctrl+C**.

### Automated short SUMO smoke (known working)

The CI covers: page and JS routes, JSON-to-experiment contract, JS syntax, strict-valid 1-run SUMO simulation, zero controller errors, zero fallbacks and zero rejected actions. [Release smoke CI](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41973492051) passed all steps before merge. Since then the same smoke run, the whole test suite and the Docker image checks run in [CI](../.github/workflows/ci.yml) on every pull request and push to `main`.

## Research findings (synthetic network only)

Original `max_pressure` mean delay reductions versus fixed-time, each based on 30 paired seeds:

| Demand | Rush hour | Emergency | Road closure |
|---|---:|---:|---:|
| 75% | 59.5% | 58.2% | 56.7% |
| 100% | 65.0% | 66.4% | 22.4% |
| 125% | 60.4% | 58.4% | **1.8% — inconclusive** |

A tuned experimental spillback controller was independently tested with **360 simulations (six conditions × 30 paired seeds × 2 controllers)**. For the heavy 125% road closure, mean completed-trip delay decreased from 120.81 to 107.01 s and confirmed spillback from 307.5 to 94.3 s. However, it worsened general delay by **14.0%** in heavy rush hour and **11.7%** in heavy emergency demand, failing preset regression guards. **Original `max_pressure` remains the accepted reference; experimental code is not promoted.**

**Limitations:** no calibration against observed real intersections or traffic volumes, synthetic route choices and closures, model-based safety not field deployment authorization. Finished-trip mean delay alone can hide vehicle completion and unfinished-trip tradeoffs. See linked reports for intervals and complete outcomes.

## Cloud MVP and event status (post-handoff update)

A later project phase added a Docker-hosted live SUMO service on Render (operator-reported functional after the shared-library fix). [Cloud guide](cloud-live-sumo-deployment.md) explains login, one-session boundaries and deployment. [Presentation-day runbook](presentation-day-demo-runbook.md) covers the audience QR and prerecorded-demo plan. The static GitHub Pages sandbox remains the appropriate **independent attendee activity**, because concurrent cloud viewers share one SUMO process. An attendee-scale live backend has not been implemented or load tested.

## Original research handoff / next research directions

**Original scope completed:** a reproducible research and demonstration prototype with a tested phase-one sandbox. The subsequent Render cloud MVP added authenticated live SUMO streaming but **not independent concurrent sandbox sessions**; see the cloud/event sections above.

**Optional future work:** pilot a scenario-aware congestion controller; preregister balanced delay, completed trips, unfinished share, spillback, queue, emergency response and safety guardrails; independently test on fresh random seeds; then consider field-data calibration and integration.

**Version / ownership:** The repository itself is the source of truth. Verify the latest `main` commit and GitHub Actions results before presenting. Do not present these percentages as real-world emissions, travel-time or accident reductions.
