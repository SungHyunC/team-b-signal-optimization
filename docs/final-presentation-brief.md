# Final Presentation Brief — Team B (7–9 minutes)

**Title:** AI, Mobility and Smart Cities — Optimizing Four Coordinated Traffic Signals with Reproducible SUMO Experiments

**Core claim:** A controllable synthetic four-intersection digital twin demonstrates how algorithm selection, demand intensity, emergencies and network spillback change operational performance. The study evaluates rather than assumes AI benefits. The evidence is **simulation only**, not field measurements.

## Slide 1 — Problem and research questions (~45 seconds)
Urban corridors are linked networks: minimizing delay at one junction can push queues downstream. Navigation-app coverage may be biased, and adaptive control needs safety and credible counterfactuals. Research questions: (1) Does smart control outperform fixed timing? (2) Does the advantage survive severe events and demand changes? (3) Can we trust navigation-based observations and safe controller decisions?

## Slide 2 — System architecture (~60 seconds)
Show four contiguous signalized junctions, demand generation, SUMO engine + TraCI, detectors and probes, controller candidate, independent signal safety supervisor, evaluation, live browser twin and static sandbox configuration builder. Emphasize that the safety supervisor enforces the independent signal-transition constraints.

## Slide 3 — Scenarios and comparison design (~60 seconds)
Scenario types include rush-hour, emergency and flood/road-closure, with additional disaster, special-event and fake-navigation-data scenarios for demonstrations. Compare fixed-time and original max-pressure using 30 **paired random seeds** per scenario and demand level (75%, 100%, 125%); report completed-trip delay, trip completion/unfinished share and spillback rather than one KPI.

## Slide 4 — Verified baseline results (~75 seconds)

| Demand | Rush-hour delay reduction | Emergency delay reduction | Road-closure delay reduction |
|---|---:|---:|---:|
| 75% | 59.5% | 58.2% | 56.7% |
| 100% | 65.0% | 66.4% | 22.4% |
| 125% | 60.4% | 58.4% | **1.8% inconclusive** |

All values are max-pressure vs fixed-time, synthetic simulations. 125% closure was an important exception, not an inconvenient outlier.

## Slide 5 — Scientific failure analysis (~65 seconds)
At heavy 125% road-closure demand, original max-pressure vs fixed-time delay was 123.77 vs 126.02 s/vehicle, statistically inconclusive. It completed a higher proportion of trips but had more downstream spillback. Interpret congestion in the connected network instead of declaring a universal winner.

## Slide 6 — Proposed spillback policy and independent confirmation (~90 seconds)
Experimental controller: apply 1.25× downstream pressure penalty after eight stopped downstream vehicles. Calibrated on three exploratory seeds, then evaluated on **30 fresh independent paired seeds** for six conditions (360 runs). Heavy 125% closure: general delay **120.81 → 107.01 s/veh**, confirmed spillback **307.5 → 94.3 s**. BUT heavy rush-hour delay **44.02 → 50.17 s** (+14.0%) and heavy emergency delay **46.56 → 51.99 s** (+11.7%); both fail the predetermined 5% delay regression guard. Declare experimental controller **rejected as a general default**. Preserve the original max-pressure implementation.

## Slide 7 — Recorded demos + attendee QR interaction (~60 seconds)
Team projects the **13 prerecorded GitHub Pages runs** at https://sunghyunc.github.io/team-b-signal-optimization/ and narrates emergency, rush-hour and road-closure examples. Attendees can use the QR to independently explore the **static configuration sandbox** at https://sunghyunc.github.io/team-b-signal-optimization/static/sandbox.html (scenario, controller, seed, demand, JSON export). The separate Render cloud site https://team-b-signal-optimization.onrender.com/ executes real SUMO and shows live frames over WebSocket, but supports **only one shared session**; audience members must not be told they each receive a private instance. Do not expose the operator's `TWIN_ACCESS_TOKEN`; see [event demo runbook](presentation-day-demo-runbook.md) for QR choice, role assignments and preflight.

## Slide 8 — Conclusions, limitations and next steps (~60 seconds)
Strong synthetic evidence for max-pressure compared with fixed-time in typical scenarios, but heavy closures reveal operational tradeoffs. Independent testing caught a seemingly promising optimization that did not generalize. No field calibration or verified city-wide gains. Future research: conditional scenario-aware spillback control, more complex networks, real traffic calibration, multi-objective guardrails and independent follow-up.

## Suggested questions and evidence

**Q: Is the AI controller guaranteed to reduce traffic?** No; the robust baseline improved selected simulated conditions; the experimental policy failed in high-demand emergencies.

**Q: How was evaluation made credible?** Fixed scenario parameters and paired seeds, independent holdout seed range, strict run audits, reported intervals and completion/spillback metrics.

**Q: Does the public website run SUMO?** GitHub Pages does not: its twin replays recorded runs and its sandbox only generates configurations. The separately deployed Render backend runs real SUMO in one shared, access-controlled session.

**Q: Why reject a controller that lowered road closure delay?** It violates high-demand regression safeguards; maximizing one event's performance is not a safe general default.

## Evidence links

- [Full engineering review](final-engineering-review.md)
- [Independent 360-run decision and outcome table](independent-controller-confirmation-review.md)
- [Final handoff and Windows reproduction](final-project-handoff.md)
- [Baseline statistical study](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41929708299)
- [Demand robustness study](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41946810451)
- [Independent holdout study](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41968750840)
- [Sandbox CI after release branch](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41973492051)

- [Presentation-day runbook and attendee safety checklist](presentation-day-demo-runbook.md)
