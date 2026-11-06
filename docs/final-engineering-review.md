# Final Engineering Review — Team B Traffic Signal Optimization

> **Update, November 2026:** a later 3,780-run confirmation promoted `max_pressure_plus` (passes the same
> 5 % regression rule in all 21 conditions) and retrained the RL controller. See
> [what changed](whats-new-2026-11.md) and the [controller confirmation](results/studies/controller-confirmation-2026-11/README.md).

**Review state:** The independent 360-run confirmation completed successfully as a simulation audit, but the experimental controller **failed two prespecified high-demand regression screens** and is **not approved**. See [final confirmation review](independent-controller-confirmation-review.md).

## Executive summary

Team B implemented a synthetic four-junction SUMO traffic corridor with a digital twin, multiple safe signal-control strategies, emergency and flood scenarios, simulated navigation probe input, and reproducible evaluation.

The original max-pressure controller substantially reduced completed-trip mean delay relative to fixed-time across rush-hour and emergency demand levels in previously validated experiments. At **125% demand with a road closure**, its 1.8% average delay reduction over fixed-time was **inconclusive**, and it exhibited more confirmed network spillback despite completing more trips. This was used to formulate and test a separate spillback-aware *experimental* controller. The first, stronger penalty failed a throughput safeguard. A milder 1.25x downstream penalty, activated after an eight-vehicle stopped downstream queue, looked promising in three new calibration seeds; **that is preliminary evidence only**.

## Roadmap and evidence

The Actions runs are the provenance; their artifacts expire on Nov 18–19, 2026. The aggregate data of each study is committed under [results/studies/](results/studies/README.md).

| Checkpoint | State | Evidence / next action |
|---|---|---|
| Research & scope | Complete | [Research documents](research/) and [architecture](ARCHITECTURE.md) |
| Four-junction SUMO prototype | Implemented | [Repository README](../README.md), [live demo](https://sunghyunc.github.io/team-b-signal-optimization/) |
| Statistical validation | Complete | [180-run baseline Actions](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41929708299), [data](results/studies/baseline-180/README.md) |
| Demand robustness review | Complete with exception | [360-run sensitivity Actions](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41946810451), [data](results/studies/robustness-360/README.md), [review](robustness-and-sensitivity-review.md) |
| Congestion analysis | Complete, root cause not proven | [Diagnostics](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41958378469), [data](results/studies/congestion-diagnosis/README.md), [pilot review](congestion-controller-pilot-review.md) ([pilot data](results/studies/controller-pilot-15/README.md)) |
| Penalty calibration | Three-seed exploratory screen complete | [24-run calibration Actions](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968041524), [data](results/studies/calibration-24/README.md), [review](spillback-penalty-calibration-review.md) |
| Independent experimental confirmation | **360/360 runs valid; experimental controller rejected** | [360-run independent confirmation](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968750840), [data](results/studies/confirmation-360/README.md); [decision](independent-controller-confirmation-review.md) |
| Engineering sign-off | **Review decision recorded: do not promote candidate** | Severe road-closure gain but high-demand rush-hour and emergency delay regressions |
| Production merge of experimental controller | **Not approved** | Keep [draft PR #5](https://github.com/SungHyunC/team-b-signal-optimization/pull/5) for research review; original `max_pressure` remains benchmark |
| Final results presentation | Handoff brief complete | [Presentation brief](final-presentation-brief.md); disclose synthetic-model limitations |

## Validated results worth presenting

For 30 paired seeds per demand/scenario/controller condition, the original max-pressure versus fixed-time mean delay reductions were approximately:

| Demand | Rush hour | Emergency | Road closure |
|---|---:|---:|---:|
| 75% | 59.5% | 58.2% | 56.7% |
| 100% | 65.0% | 66.4% | 22.4% |
| 125% | 60.4% | 58.4% | **1.8% (inconclusive)** |

The 125% road-closure comparison was fixed-time 126.02 s/vehicle vs original max-pressure 123.77 s/vehicle. Its 95% paired CI for fixed-minus-max benefit was approximately [-3.14, 7.65] s/vehicle (spans zero); unfinished share was 14.54% vs 8.16%, and confirmed spillback was 136.3 vs 309.0 s. A controller can trade completed-trip delay against number of completed trips, so these must be interpreted together. See [complete robustness review](robustness-and-sensitivity-review.md) for caveats.

The selected experimental configuration (threshold 8 stopped vehicles, downstream penalty 1.25x) improved *three-seed calibration* mean delay from 132.07 to 105.48 s/vehicle, unfinished share from 8.83% to 7.91%, and confirmed spillback from 531.7 to 56.7 s. **Do not quote these exploratory improvements as independent confirmation.** Independent seeds 31–60 have been independently scored: see the [final confirmation review](independent-controller-confirmation-review.md).

## Independent confirmation: completed review checklist

- [x] GitHub Actions [run #41968750840](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968750840) completes successfully.
- [x] Strict matrix audit yields **360/360** valid, with 30 paired seeds for each of six conditions.
- [x] Confirm that the proposed controller parameters are frozen (threshold=8, multiplier=1.25), matching the same controller software, traffic demand, SUMO version and network for each pair.
- [x] Inspect mean delay benefit and paired 95% interval for **125% road closure**, including whether interval excludes zero.
- [x] Inspect unfinished share, completed throughput, 95th percentile queue, and confirmed link-level spillback; no throughput suppression disguised as delay reduction.
- [x] Inspect rush-hour (100%, 125%), emergency (100%, 125%), and lower-demand closure (75%) regressions. Pay particular attention to actual emergency-vehicle travel time, not general delay only.
- [x] Check every run's `controller_errors`, `fallback_steps`, `rejected_actions`, and manifest provenance.
- [x] Explain uncertainty from selecting the penalty after exploratory tuning, multiple comparisons, and synthetic, uncalibrated assumptions.
- [x] Approve or reject the experimental controller explicitly in the PR. A green workflow alone is not algorithm approval.
- [x] Engineering sign-off explicitly rejected the experimental general-purpose controller; do **not** merge it into `main`.

## Reproduce locally

On `main` (the original controllers only):

```bash
python -m pytest
python -m teamb twin
python -m teamb.experiments run --name closure_demo --scenarios road_closure --controllers fixed_time,max_pressure --seeds 31-32 --workers 2 --scenario-params '{"demand_scale":1.25}' --baseline fixed_time --strict-validation
```

The rejected `max_pressure_spillback` controller is **not on `main`**. Its confirmation run needs the research commit, e.g. `git checkout 77ca85d` (branch `feature/validation-sandbox-explainability`, [draft PR #5](https://github.com/SungHyunC/team-b-signal-optimization/pull/5)):

<!-- docs-check: skip (needs commit 77ca85d) -->
```bash
python -m teamb.experiments run --name confirmation_demo --scenarios road_closure --controllers max_pressure,max_pressure_spillback --seeds 31-32 --workers 2 --scenario-params '{"demand_scale":1.25}' --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.25}}' --baseline max_pressure --strict-validation
```

The two-seed examples above are integration tests, not statistical replications. For the full 30-seed design, see [the confirmation workflow at 77ca85d](https://github.com/SungHyunC/team-b-signal-optimization/blob/77ca85d/.github/workflows/independent-controller-confirmation.yml).

## Limitations and honesty in reporting

All reported results are **synthetic SUMO simulation outcomes**, not measured road-network benefits, and none establish field-calibrated performance. Results depend on assumed routes, signal timings, detector coverage, and road-closure diversion. A small number of seeds from pilot tuning is not confirmation. The 360-run study was reviewed and the experimental variant was rejected for general use; this is neither production-grade nor real-world proof.

## Repository integration status

- Pull request [#4](https://github.com/SungHyunC/team-b-signal-optimization/pull/4) has been merged into `main` by account **Burtogr**, containing the validated study infrastructure and robustness review.
- Experimental work is intentionally isolated on `feature/validation-sandbox-explainability` for review, after the 360-run confirmation was completed and reviewed.
- Final decision: **REJECT the candidate as a general-purpose improvement**. [Details](independent-controller-confirmation-review.md).

- Sandbox-only [PR #6](https://github.com/SungHyunC/team-b-signal-optimization/pull/6) passed CI and merged into `main` without the experimental controller.
- [Final project handoff](final-project-handoff.md) records local Windows testing and remaining boundaries.
