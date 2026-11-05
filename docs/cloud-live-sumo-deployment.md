# Cloud Live SUMO — Deployment and Sandbox Guide

**Status (2026-11-05):** The operator deployed the Docker service to [Render](https://team-b-signal-optimization.onrender.com/) and reported the sandbox works after the [libXrender startup fix](https://github.com/SungHyunC/team-b-signal-optimization/pull/10). [Docker-based SUMO/TraCI smoke verification](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/42074585084) passed on `main`. This does **not** establish sustained or concurrent performance in Render Free. The public GitHub Pages demo remains prerecorded.

## Architecture

- Public GitHub Pages: static scenario builder, existing prerecorded demo; **not** a simulation engine.
- Separate **live** FastAPI/TraCI/SUMO Docker web service: one Python process, one active SUMO simulation and a WebSocket broadcaster (`/ws`). Remote browsers get genuine vehicle positions and KPIs, not stored recordings.
- Authenticated visitors choose a preset scenario, controller, seed, demand factor and run duration. During a run they can use the existing live twin actions panel for closures, emergency vehicles and test-data events.
- The current prototype uses one **shared global session**; when someone restarts a run, all connected clients see that same run. **Do not market this as separate independent sandboxes for many users.** Implement per-user simulation sessions with isolation and job quotas before a public multi-user launch.

## Deployment (Render Blueprint option)

1. Cloud MVP [PR #9](https://github.com/SungHyunC/team-b-signal-optimization/pull/9) and startup fix [PR #10](https://github.com/SungHyunC/team-b-signal-optimization/pull/10) are already merged into `main`.
2. Log in to Render and choose **New → Blueprint**; connect the Team B GitHub repository. Render reads `render.yaml` and builds the Docker service using the repository `Dockerfile`.
3. Review the selected **Starter** compute plan and billing before deploying; SUMO is CPU-intensive and this cloud service can incur ongoing charges.
4. Let Render create the `TWIN_ACCESS_TOKEN` secret (random value). Retrieve the environment variable securely in your Render dashboard. Do **not** post it in GitHub, screenshots or chat.
5. Confirm `/healthz` and use the operator's deployed service URL: https://team-b-signal-optimization.onrender.com/ .
6. Open that HTTPS address on your phone; enter the access password from Render. If you visit with a scenario query link, the login redirects you back to that scenario.
7. On the existing static public sandbox, enter the cloud app HTTPS origin in **Cloud simulator address**, configure a scenario and select **Launch LIVE SUMO**. It will open the cloud simulator with the requested scenario, controller, seed, demand multiplier, preemption and duration. On the hosted sandbox page itself, the live URL defaults to its own origin.
8. Test the live three.js scene and event controls. Check Render logs for SUMO errors. Compare live KPIs against run summaries where applicable.

Note: publishing code to GitHub does **not** provision or pay for a Render service; the account owner must connect and deploy it.

### Cloud backend checks

```bash
python -m pytest tests/test_cloud_live.py tests/test_sandbox.py tests/test_sandbox_http.py -q
node --check teamb/twin/static/js/sandbox.js
node --check teamb/twin/static/js/main.js
node --check teamb/twin/static/js/ui/topbar.js
```

The CI workflow additionally runs a strict-valid SUMO simulation. These checks do not replace a deployed-browser/WebSocket end-to-end test.

## Important operating boundaries

- **Access required:** never deploy this computationally expensive API with `TWIN_ACCESS_TOKEN` unset. The application intentionally permits unauthenticated **local** use, so configure the secret in production.
- **One active simulation:** multiple visitors do not have isolated sessions; they can interrupt one another. Restrict the access password to a small group of trusted testers.
- **Preset scenarios only:** rush hour, off-peak, special event, emergency, road closure, sinkhole, earthquake, and fake-data events. Demand scale can vary from 0.1 to 3.0; hosted run duration 60–10,800 seconds; seeds 0–2,147,483,647. Users cannot yet upload arbitrary road maps, generate arbitrary networks, or write Python controller code in the browser.
- **Resource guardrails:** one Uvicorn worker only, capped run parameters, and a paid always-on-style instance preferred. For 24/7 availability and multiple independent users, add a scheduler, per-user isolated SUMO processes, quotas, persistence, rate limiting, monitoring, session timeouts and scalable job orchestration.
- **Security:** the first version includes login, HTTP and WebSocket access checks, secure session cookies, and limited cloud overrides. This is a **private research MVP**, not a security-audited public multi-tenant platform.
- **Data:** simulation results live on the service's ephemeral filesystem unless persistent storage is separately configured. Deploys and restarts can erase them. Export/archive important reports separately.
- **Browser:** three.js rendering happens on the phone; SUMO calculation happens on the cloud server. Older phones may need reduced graphical quality.
- **Real-world validity:** simulation outcomes are synthetic, not proven field improvements. The rejected exploratory spillback controller is not deployed in this feature.

## Future phases for unrestricted personal sandbox use

1. **Per-user isolated live simulations** with WebSocket multiplexing and one sandbox ID per person.
2. **Scenario authoring**: configurable traffic-flow schedules, road closures at arbitrary times, incident editor and input validators, then custom SUMO networks.
3. **Persistent comparisons**: run two controllers with matched seeds, save experiment jobs and download summary/vehicle output artifacts.
4. **Cloud operations**: queue, cancellation, CPU/memory limits, cost quotas, audit logs and user authentication; then open the service to more users.

Read the existing [final project handoff](final-project-handoff.md) for the validated baseline and the rejected experimental-controller findings.

## Presentation-day audience policy

For the planned event, use the [prerecorded GitHub Pages twin](https://sunghyunc.github.io/team-b-signal-optimization/) on the presentation screen. The [static sandbox editor](https://sunghyunc.github.io/team-b-signal-optimization/static/sandbox.html) is suitable for an attendee-facing QR because it does not start simulations and each visitor can independently edit configuration. The Render URL targets a **single shared live session**, and should be used by a restricted operator or supervised small group, not an unrestricted QR crowd. Read the [event runbook](presentation-day-demo-runbook.md) before finalizing QR posters.
