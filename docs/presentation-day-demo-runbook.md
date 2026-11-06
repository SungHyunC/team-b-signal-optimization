# Team B — Presentation Day Demo Runbook (November 2026)

**Audience format:** Team narrates and projects the **13 prerecorded GitHub Pages twin runs** for a deterministic presentation; a QR code lets attendees try a sandbox on their phones. The shared cloud SUMO instance is for controlled live demonstrations only, not unrestricted concurrent experiments.

## Verified technical foundations
- [Main repository](https://github.com/SungHyunC/team-b-signal-optimization) and [cloud Docker CI](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/42074585084) contain a successful **SUMO + TraCI step inside the Docker image** following the libXrender repair, merged in [PR #10](https://github.com/SungHyunC/team-b-signal-optimization/pull/10).
- Render cloud address supplied and tested by the operator: https://team-b-signal-optimization.onrender.com/ . The user reported the sandbox works after redeploy. **No independent load test or multi-user isolation has been verified.**
- Public prerecorded twin: https://sunghyunc.github.io/team-b-signal-optimization/
- Public phase-one sandbox (configuration editor, no SUMO execution): https://sunghyunc.github.io/team-b-signal-optimization/static/sandbox.html
- Original max-pressure reference remains validated in synthetic SUMO; the experimental spillback-aware controller failed independent high-demand regressions and must not be portrayed as an approved improvement.

## Choice of attendee experience — decide before printing the QR
**Recommended for general audience:** QR links to the **GitHub Pages configuration sandbox**. Each attendee can select a scenario/controller, change demand, validate and export/import JSON without touching the shared live simulation. This is reliable, parallel and does not need a login or always-on compute. Clearly label it *Build your scenario — configuration preview only*.

**If the QR instead links to Render:** https://team-b-signal-optimization.onrender.com/ . That is a **single global shared live SUMO session**; starting a simulation can interrupt every connected attendee and the presenter. The service's login gate requires `TWIN_ACCESS_TOKEN` to be set; attendees cannot access a protected server without credentials. **Do not distribute the owner/admin access token in a public QR, slide, URL or chat**, and do not unset it to bypass access control. Use controlled small-group access only until per-user isolation, queues, quotas and attendee permissions exist.

**Show two clearly distinguished links if practical:** *Watch recorded demonstration* (GitHub Pages); *Build a scenario on your phone* (GitHub Pages sandbox). Separately, the operator may open the Render cloud simulation during a short supervised demo.

## Timeline / run of show

| Segment | Presenter action | Audience action | Risk control |
|---|---|---|---|
| Opening (0–1 min) | Define four-junction SUMO research question and limits | Scan optional QR to static editor | Preload recorded website |
| Architecture (1–2 min) | Explain controller, supervisor, SUMO and probe data | Select scenario and controller | Avoid claiming live backend has per-user sessions |
| Recorded demonstrations (2–5 min) | Replay emergency, rush hour and road closure with pauses | Change sandbox demand/seed; export JSON | Keep screen-sharing on GitHub Pages, independent of Render |
| Validated outcomes (5–7 min) | Compare fixed-time vs max-pressure; disclose 125% closure exception | Read example config | Only quote synthetic simulation evidence |
| Scientific limitations (7–8 min) | Show rejected controller holdout tradeoff | — | No claims of field-calibrated improvements |
| Q&A (8–9 min) | Answer experimental method and deployment questions | Continue exploring static editor | Do not promise independent live runs |

## Pre-event checklist (operator verifies; NOT yet claimed complete)
- [ ] On venue Wi-Fi and cellular, open public prerecorded twin and play/pause two runs on the presentation laptop and a phone.
- [ ] In a private/incognito phone browser, scan **the exact printed QR** from intended audience distance and confirm it opens the intended link without authentication surprises.
- [ ] If QR points to static sandbox, change scenario, demand and seed; download/import JSON on iOS/Android; confirm no SUMO processing is promised on the page.
- [ ] If the cloud demo is used, verify Render is **Live**, `/healthz` responds, an authenticated start steps the simulation and KPIs advance; assess wake delay after idle on Free tier.
- [ ] Verify `TWIN_ACCESS_TOKEN` is configured in Render Environment; never project or distribute its value.
- [ ] Do not give many attendees the ability to start the **shared** live simulation during the narrated presentation. No concurrent-run stress test has passed.
- [ ] Test HDMI/projector, fonts, browser zoom, audio, camera perspective and 2-minute backup screen recording.
- [ ] Cache or locally save demonstration video/screen recording (with permission) if venue Internet fails; prerecorded GitHub Pages still requires a network unless files are available offline.
- [ ] Have one presenter explain the results and one operator manage browser tabs, recording playback and any controlled Render demo.
- [ ] Verify the QR's destination after printing; QR created for the Render URL is **not** the recommended static sandbox QR.
- [ ] Refresh final slide sources and do not overstate synthetic results, notably the 125% road-closure 1.8% inconclusive improvement and the rejected general-purpose spillback candidate.

## Honest scope statement for presenters

> “Our team built a four-intersection traffic-signal digital twin and independently tested several signal-control strategies in SUMO. The large screen shows recorded experiment examples so our explanation stays synchronized. You can scan the QR code to explore scenario settings on your own phone. Our cloud simulator also demonstrates live SUMO, but today it runs as one shared research session, not one simulator per audience member. These findings are from a synthetic network and are not field-deployment claims.”

## What to build only if unrestricted cloud access becomes a requirement

- Per-attendee isolated simulation process/job ID and cancellation
- Queue, concurrency caps, rate limits and compute-cost guardrails
- Attendee-scoped authentication separate from owner/admin access
- Persisted experiment results and downloadable comparisons
- Load testing on the selected Render instance tier

Until these features exist, the static configuration sandbox is the safer attendee-facing option.
