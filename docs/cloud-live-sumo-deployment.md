# Cloud Live SUMO — Deployment and Sandbox Guide

**Status (2026-11-05):** The operator deployed the Docker service to [Render](https://team-b-signal-optimization.onrender.com/) and reported the sandbox works after the [libXrender startup fix](https://github.com/SungHyunC/team-b-signal-optimization/pull/10). [Docker-based SUMO/TraCI smoke verification](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/42074585084) passed on `main`. This does **not** establish sustained or concurrent performance in Render Free. The public GitHub Pages demo remains prerecorded.

**Deployed service vs. `render.yaml`:** the live instance is called `team-b-signal-optimization` and, per the operator, runs on Render's **Free** plan. The Blueprint in `render.yaml` declares a different service, `team-b-live-sumo`, on the **Starter** plan. The live instance was therefore not created from this Blueprint (or was renamed afterwards), and syncing the Blueprint would create a second, paid Starter service next to it. Check the Render dashboard before applying the Blueprint, and either keep deploying the existing service from the repository's `Dockerfile` or change `render.yaml` to the real name and plan first.

## Architecture

- Public GitHub Pages: static scenario builder, existing prerecorded demo; **not** a simulation engine.
- Separate **live** FastAPI/TraCI/SUMO Docker web service: one Python process, one active SUMO simulation and a WebSocket broadcaster (`/ws`). Remote browsers get genuine vehicle positions and KPIs, not stored recordings.
- Authenticated visitors choose a preset scenario, controller, seed, demand factor and run duration. During a run they can use the existing live twin actions panel for closures, emergency vehicles and test-data events.
- The current prototype uses one **shared global session**; when someone restarts a run, all connected clients see that same run. **Do not market this as separate independent sandboxes for many users.** Implement per-user simulation sessions with isolation and job quotas before a public multi-user launch.

## Deployment (Render Blueprint option)

1. Cloud MVP [PR #9](https://github.com/SungHyunC/team-b-signal-optimization/pull/9) and startup fix [PR #10](https://github.com/SungHyunC/team-b-signal-optimization/pull/10) are already merged into `main`.
2. Log in to Render and choose **New → Blueprint**; connect the Team B GitHub repository. Render reads `render.yaml` and builds the Docker service using the repository `Dockerfile`.
3. Review the selected **Starter** compute plan (`plan: starter` in `render.yaml`) and billing before deploying; SUMO is CPU-intensive and this cloud service can incur ongoing charges. The current live instance uses the Free plan instead (see the status note above), which sleeps when idle and wakes slowly.
4. Let Render create the `TWIN_ACCESS_TOKEN` secret (random value). Retrieve the environment variable securely in your Render dashboard. Do **not** post it in GitHub, screenshots or chat.
5. Confirm `/healthz` and use the operator's deployed service URL: https://team-b-signal-optimization.onrender.com/ .
6. Open that HTTPS address on your phone; enter the access password from Render. If you visit with a scenario query link, the login redirects you back to that scenario.
7. On the existing static public sandbox, enter the cloud app HTTPS origin in **Cloud simulator address**, configure a scenario and select **Launch LIVE SUMO**. It will open the cloud simulator with the requested scenario, controller, seed, demand multiplier, preemption and duration. On the hosted sandbox page itself, the live URL defaults to its own origin.
8. Test the live three.js scene and event controls. Check Render logs for SUMO errors. Compare live KPIs against run summaries where applicable.

Note: publishing code to GitHub does **not** provision or pay for a Render service; the account owner must connect and deploy it.

### Cloud backend checks

```bash
python -m pytest tests/test_cloud_live.py tests/test_twin.py tests/test_sandbox.py tests/test_sandbox_http.py -q
docker build -t team-b-live-sumo .        # also runs `teamb doctor` with a SUMO smoke run inside the image
docker run --rm -p 10000:10000 -e TWIN_ACCESS_TOKEN=change-me team-b-live-sumo
```

[CI](../.github/workflows/ci.yml) runs these on every pull request and push to `main`, together with the whole test suite, a strict-valid SUMO simulation and, in the Docker job, a check that the container runs as a non-root user, a `/healthz` probe, the 401 access gate and a SUMO + TraCI step inside the running container. These checks do not replace a deployed-browser/WebSocket end-to-end test.

### The production image

- Built from a digest-pinned `python:3.11-slim` with only the runtime dependencies (`requirements.txt` constrained by `requirements.lock`); pytest and httpx are not installed.
- Runs as the non-root user `app` (uid 10001) under `tini`. The code is read-only for that user; only `results/` and `teamb/network/generated/` are writable. Results are lost on redeploy (see *Data* below).
- `docker build` runs `teamb doctor`, which builds the SUMO network and runs a 120 s smoke simulation. A missing shared library (the `libXrender.so.1` failure fixed in PR #10) now fails the build instead of the first visitor.
- The container declares a `HEALTHCHECK` on `/healthz`; Render uses `healthCheckPath: /healthz` from `render.yaml`.

## Important operating boundaries

- **Access required:** never deploy this computationally expensive API with `TWIN_ACCESS_TOKEN` unset. The application intentionally permits unauthenticated **local** use, so configure the secret in production.
- **Session cookie:** a successful login sets an HttpOnly, SameSite-restricted cookie that lasts **12 hours** (`max_age` in `teamb/twin/server.py`); after that, visitors log in again.
- **`TWIN_COOKIE_INSECURE=1` (local testing only):** the cookie is marked `Secure` by default, so browsers send it only over HTTPS. Setting `TWIN_COOKIE_INSECURE=1` drops the `Secure` flag, which is only for testing the login locally over plain `http://` with `TWIN_ACCESS_TOKEN` set (Safari and other browsers drop `Secure` cookies on http). **Never set it in production.**
- **`TWIN_ALLOWED_ORIGINS`:** WebSocket handshakes are accepted from the twin's own pages, from clients that send no `Origin` (scripts, tests) and from the origins listed here, comma-separated (for example `https://sunghyunc.github.io`). Browsers let any web page open a WebSocket to the twin, and CORS does not apply to WebSockets, so keep the list short; `*` allows every origin and does not belong in production.
- **`TWIN_KEEP_RUNS`:** how many twin run folders are kept under `results/twin/` (default 10, `0` keeps all). Older runs are deleted when a new one starts, so the ephemeral disk does not fill up.
- **One active simulation:** multiple visitors do not have isolated sessions; they can interrupt one another. Restrict the access password to a small group of trusted testers.
- **Preset scenarios only:** rush hour, off-peak, special event, emergency, road closure, sinkhole, earthquake, and fake-data events. Demand scale can vary from 0.1 to 3.0; seeds 0–2,147,483,647; a Scenario Sandbox duration is blank (scenario default) or 1,200–10,800 seconds (900 s warm-up plus at least 300 s measured), and a live run ends by 10,800 simulated seconds at the latest. The sandbox reads these limits from `GET /api/sandbox/schema`. Users cannot yet upload arbitrary road maps, generate arbitrary networks, or write Python controller code in the browser.
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
