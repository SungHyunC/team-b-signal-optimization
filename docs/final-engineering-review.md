# Final Engineering Review — Team B Traffic Signal Optimization

**Review state:** Ready for repository review; **independent 360-run confirmation is in progress as of the document's preparation**. This page intentionally separates verified work from experimental claims. Do not describe the experimental controller as validated until the final Actions run and report have been inspected.

## Executive summary

Team B implemented a synthetic four-junction SUMO traffic corridor with a digital twin, multiple safe signal-control strategies, emergency and flood scenarios, simulated navigation probe input, and reproducible evaluation.

The original max-pressure controller substantially reduced completed-trip mean delay relative to fixed-time across rush-hour and emergency demand levels in previously validated experiments. At **125% demand with a road closure**, its 1.8% average delay reduction over fixed-time was **inconclusive**, and it exhibited more confirmed network spillback despite completing more trips. This was used to formulate and test a separate spillback-aware *experimental* controller. The first, stronger penalty failed a throughput safeguard. A milder 1.25x downstream penalty, activated after an eight-vehicle stopped downstream queue, looked promising in three new calibration seeds; **that is preliminary evidence only**.

## Roadmap and evidence

| Checkpoint | State | Evidence / next action |
|---|---|---|
| Research & scope | Complete | [Research documents](research/) and [architecture](ARCHITECTURE.md) |
| Four-junction SUMO prototype | Implemented | [Repository README](../README.md), [live demo](https://sunghyunc.github.io/team-b-signal-optimization/) |
| Statistical validation | Complete | [180-run baseline Actions](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41929708299) |
| Demand robustness review | Complete with exception | [360-run sensitivity Actions](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41946810451), [review](robustness-and-sensitivity-review.md) |
| Congestion analysis | Complete, root cause not proven | [Diagnostics](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41958378469), [pilot review](congestion-controller-pilot-review.md) |
| Penalty calibration | Three-seed exploratory screen complete | [24-run calibration Actions](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968041524), [review](spillback-penalty-calibration-review.md) |
| Independent experimental confirmation | **Running, not yet reviewed** | [360-run independent confirmation](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968750840); 30 new seeds, six conditions |
| Engineering sign-off | **Blocked on confirmation** | Inspect strict audits, seed-level results, confidence intervals, safety diagnostics, throughput and completion tradeoffs |
| Production merge of experimental controller | **Blocked on sign-off** | Draft PR only; original `max_pressure` remains benchmark |
| Final results presentation | Review outline ready | Replace pending fields with confirmed results; explain synthetic-model limitations |

## Validated results worth presenting

For 30 paired seeds per demand/scenario/controller condition, the original max-pressure versus fixed-time mean delay reductions were approximately:

| Demand | Rush hour | Emergency | Road closure |
|---|---:|---:|---:|
| 75% | 59.5% | 58.2% | 56.7% |
| 100% | 65.0% | 66.4% | 22.4% |
| 125% | 60.4% | 58.4% | **1.8% (inconclusive)** |

The 125% road-closure comparison was fixed-time 126.02 s/vehicle vs original max-pressure 123.77 s/vehicle. Its 95% paired CI for fixed-minus-max benefit was approximately [-3.14, 7.65] s/vehicle (spans zero); unfinished share was 14.54% vs 8.16%, and confirmed spillback was 136.3 vs 309.0 s. A controller can trade completed-trip delay against number of completed trips, so these must be interpreted together. See [complete robustness review](robustness-and-sensitivity-review.md) for caveats.

The selected experimental configuration (threshold 8 stopped vehicles, downstream penalty 1.25x) improved *three-seed calibration* mean delay from 132.07 to 105.48 s/vehicle, unfinished share from 8.83% to 7.91%, and confirmed spillback from 531.7 to 56.7 s. **Do not quote these exploratory improvements as independent confirmation.** Independent seeds 31–60 have not yet been scored in this document.

## Independent confirmation: pre-review checklist

- [ ] GitHub Actions [run #41968750840](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968750840) completes successfully.
- [ ] Strict matrix audit yields **360/360** valid, with 30 paired seeds for each of six conditions.
- [ ] Confirm that the proposed controller parameters are frozen (threshold=8, multiplier=1.25), matching the same controller software, traffic demand, SUMO version and network for each pair.
- [ ] Inspect mean delay benefit and paired 95% interval for **125% road closure**, including whether interval excludes zero.
- [ ] Inspect unfinished share, completed throughput, 95th percentile queue, and confirmed link-level spillback; no throughput suppression disguised as delay reduction.
- [ ] Inspect rush-hour (100%, 125%), emergency (100%, 125%), and lower-demand closure (75%) regressions. Pay particular attention to actual emergency-vehicle travel time, not general delay only.
- [ ] Check every run's `controller_errors`, `fallback_steps`, `rejected_actions`, and manifest provenance.
- [ ] Explain uncertainty from selecting the penalty after exploratory tuning, multiple comparisons, and synthetic, uncalibrated assumptions.
- [ ] Approve or reject the experimental controller explicitly in the PR. A green workflow alone is not algorithm approval.
- [ ] Only after engineering sign-off should experimental controller code be merged into `main` and (separately) any updated online demo be published.

## Reproduce locally

```bash
python -m pytest
python -m teamb twin
python -m teamb.experiments run --name confirmation_demo --scenarios road_closure --controllers max_pressure,max_pressure_spillback --seeds 31-32 --workers 2 --scenario-params '{"demand_scale":1.25}' --controller-params '{"max_pressure_spillback":{"congestion_threshold":8,"downstream_penalty":1.25}}' --baseline max_pressure --strict-validation
```

The two-seed example above is an integration test, not a statistical replication. For the full 30-seed design, see [the workflow](../.github/workflows/independent-controller-confirmation.yml).

## Limitations and honesty in reporting

All reported results are **synthetic SUMO simulation outcomes**, not measured road-network benefits, and none establish field-calibrated performance. Results depend on assumed routes, signal timings, detector coverage, and road-closure diversion. A small number of seeds from pilot tuning is not confirmation. The 360-run study must pass its own independent review before a production-grade or real-world claim can be made.

## Repository integration status

- Pull request [#4](https://github.com/SungHyunC/team-b-signal-optimization/pull/4) has been merged into `main` by account **Burtogr**, containing the validated study infrastructure and robustness review.
- Experimental work is intentionally isolated on `feature/validation-sandbox-explainability` for review, while the 360-run confirmation is running.
- Final decision: **PENDING** until the full independent confirmation artifacts are available.
