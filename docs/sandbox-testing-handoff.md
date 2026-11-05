# Sandbox Testing & Final Project Handoff

**Status:** [Development sandbox smoke run #41973343687](https://github.com/SungHyunC/team-b-signal-optimization/actions/runs/41973343687) passed all steps. [Sandbox-only release PR #6](https://github.com/SungHyunC/team-b-signal-optimization/pull/6) is prepared for integration; the public GitHub Pages demo is a prerecorded replay, **not** a server-backed custom SUMO run service.

## What is available today

- **Scenario Sandbox:** Visit `http://127.0.0.1:8000/static/sandbox.html` after launching the local twin. It builds, validates, exports, imports, and displays reproducible scenario JSON. It does **not** execute SUMO simulations inside the browser.
- **Digital twin:** `http://127.0.0.1:8000/` runs SUMO with available built-in scenarios and controllers.
- **Online prerecorded demo:** https://sunghyunc.github.io/team-b-signal-optimization/ — view existing recorded runs, not custom simulation execution. Availability of the sandbox on this Pages deployment is **not** asserted.
- **Experiment runner:** Run the exported config by copying the command shown under “How to reproduce the experiment” in the sandbox. Requires local Python dependencies and SUMO.

## Local test walkthrough

```bash
git clone https://github.com/SungHyunC/team-b-signal-optimization.git
cd team-b-signal-optimization
git checkout feature/validation-sandbox-explainability
python -m pip install -r requirements.txt
python -m pytest tests/test_sandbox.py tests/test_sandbox_http.py -q
python -m teamb twin
```

Then open **http://127.0.0.1:8000/static/sandbox.html** and test:

1. Keep preset `rush_hour` and controller `max_pressure`; verify “Configuration valid”.
2. Change scenario to `road_closure`, demand multiplier to `1.25`, seed to `33`; confirm JSON preview and reproduce command update.
3. Click **Download JSON**; re-import it using **Import saved configuration**, confirm the values match.
4. Set multiplier to `0` or seed to `-1`: validate that export is blocked and the page gives an error. Reset to defaults afterward.
5. Click **Back to Signal Twin** to return to the running local twin.
6. Copy the reproduced command and run it locally to generate real outputs. The browser alone does not run SUMO.

## Automated smoke gate

The [Sandbox Readiness Smoke Test](../.github/workflows/sandbox-readiness.yml) checks static HTTP routes, JSON schema/runner mapping, JavaScript syntax, and a deterministic short road-closure run with strict provenance validation. It additionally verifies zero controller errors, fallbacks and rejected actions. **A passing smoke gate is necessary but does not substitute for a manual browser interaction test.**

## Scientific decision and final handoff

- [PR #4](https://github.com/SungHyunC/team-b-signal-optimization/pull/4) merged the validated research and simulation evaluation foundation into `main`.
- [Independent 360-run review](independent-controller-confirmation-review.md): the exploratory spillback controller reduced 125%-demand road-closure delay and spillback, but worsened 125% rush-hour and emergency general delay beyond the predeclared limit. **Do not deploy or merge as a general controller.**
- [PR #5](https://github.com/SungHyunC/team-b-signal-optimization/pull/5) remains a draft research-only review.
- [Engineering roadmap](final-engineering-review.md) holds the broader results, evidence and limitations.
- All performance outcomes refer to synthetic SUMO simulations, not measured real-world intersections.

## Sign-off checklist

- [x] Core synthetic four-junction SUMO twin and prerecorded browser demo exist
- [x] Reproducible statistical, robustness and sensitivity validation completed
- [x] Experimental controller evaluated independently and rejected for general use
- [x] Review documents and research PR published
- [x] Sandbox page route/navigation and README markup repaired on development branch
- [x] Automated sandbox smoke workflow passed on the development commit (run #41973343687)
- [ ] Manual browser interaction test (export/import, invalid inputs, back navigation)
- [ ] Review and merge [sandbox-only PR #6](https://github.com/SungHyunC/team-b-signal-optimization/pull/6) after its release-branch smoke check passes; rejected controller is excluded
- [ ] If desired, publish/update static GitHub Pages deployment separately after review

The sandbox UI is **phase one**: configuration generation only. Building a true browser-to-SUMO execution service is a distinct backend and security project, not a capability we should imply is complete.
