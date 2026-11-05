# Independent Confirmation — Final Engineering Decision

**Decision: REJECT** the current fixed threshold spillback-aware controller as the general default. **Retain the original `max_pressure` benchmark**. All tests are simulations of a synthetic network, not field-calibrated deployment evidence.

## Evidence
- [Independent 360-run workflow #41968750840](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968750840): **SUCCESS**, 360/360 strict-valid simulations, independent paired seeds 31–60.
- [Full downloadable data artifact #13390656343](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968750840/artifacts/13390656343).
- Parameters fixed before confirmation: stopped downstream queue threshold **8 vehicles** and downstream penalty **1.25x**.
- All per-run `controller_errors`, `fallback_steps` and `rejected_actions` were checked as zero by the confirmation evaluator.

## Core outcomes

| Scenario | Original delay (s/veh) | Experimental delay (s/veh) | Experimental minus original; approximate paired 95% CI (s/veh) | 5% delay-regression screen |
|---|---:|---:|---|---|
| Road closure, 125% | 120.8060 | **107.0143** | −13.7917 [−18.6711, −8.9122] | PASS |
| Rush hour, 100% | **29.1937** | 29.6423 | +0.4487 [+0.1055, +0.7918] | PASS |
| Rush hour, 125% | **44.0230** | 50.1697 | +6.1467 [−0.0208, +12.3141] | **FAIL: +14.0%** |
| Emergency, 100% | **29.8767** | 30.6283 | +0.7517 [+0.4320, +1.0714] | PASS |
| Emergency, 125% | **46.5587** | 51.9877 | +5.4290 [+1.0774, +9.7806] | **FAIL: +11.7%** |
| Road closure, 75% | **44.6130** | 45.4327 | +0.8197 [−0.1589, +1.7983] | PASS |

The primary severe-closure result shows both reduced mean completed-trip delay and confirmed spillback: **307.5 → 94.3 s**, paired reduction **213.17 s**, 95% CI [123.41, 302.92] s. However, unfinished share worsens **7.38% → 8.14%** (difference +0.75 percentage points, 95% CI [−0.12, +1.62]), and completed trips decline **4435.53 → 4399.47** per simulation (paired difference −36.07, 95% CI [−77.60, +5.47]); those latter intervals span zero. Do not treat the delay metric in isolation.

For 125% emergency demand, queue p95 rises **6.83 → 8.17** vehicles. Emergency vehicle mean travel time rises **112.66 → 116.42 s**, paired difference +3.76 s, 95% CI [−0.58, +8.10] (inconclusive on EV travel time itself). The statistically supported general delay regression under heavy emergency demand and the heavy rush-hour mean-delay guardrail failure preclude promoting this controller as a general default.

## Limitations and next action

Approximate paired 95% CIs are *unadjusted for six comparisons*; screening pass is not formal equivalence. The controller code was held fixed across independent seeds 31–60, but model and network structural assumptions are synthetic and uncalibrated.

**Engineering disposition:** Keep experimental code and history in [draft PR #5](https://github.com/SungHyunC/team-b-signal-optimization/pull/5) for evaluation, not for merge into `main` as a validated improvement. Original `max_pressure` remains in `main`.

Possible subsequent research, *not yet implemented or validated*: event/closure-aware conditional penalty or downstream storage-aware pressure policy. This needs new pilot and fresh independent testing. The near-term final deliverable should explain this positive severe-closure result together with the generalization failure, rather than hide it.
