"""CI workflows keep their contracts.

- ci.yml runs on every pull request and push to main: install, doctor, the whole pytest suite,
  JavaScript checks, a SUMO smoke run and the Docker image (non-root, no test tools).
- Research workflows run only on workflow_dispatch: no stale branch triggers, no expiring
  hard-coded artifact ids, 90-day artifact retention.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # YAML 1.1 reads the bare key `on` as boolean True
    data["on"] = data.pop(True, data.get("on"))
    return data


ALL = {p.name: _load(p) for p in sorted(WORKFLOWS.glob("*.yml"))}
RESEARCH = {name: wf for name, wf in ALL.items() if name != "ci.yml"}


def _triggers(wf: dict) -> dict:
    on = wf["on"]
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on


def _steps(wf: dict):
    for job in wf["jobs"].values():
        yield from job.get("steps", [])


def _runs(wf: dict) -> list[str]:
    return [s["run"] for s in _steps(wf) if "run" in s]


def test_expected_workflows_and_no_duplicates():
    assert set(ALL) == {"ci.yml", "lesson1-sumo-validation.yml", "robustness-sensitivity.yml",
                        "congestion-failure-analysis.yml"}
    names = [wf["name"] for wf in ALL.values()]
    assert len(names) == len(set(names))


def test_push_triggers_are_main_only_and_paired_with_pull_request():
    for name, wf in ALL.items():
        on = _triggers(wf)
        if "push" in on:
            assert (on["push"] or {}).get("branches") == ["main"], name
            assert "pull_request" in on, f"{name}: a push trigger without pull_request skips PRs"


def test_research_workflows_are_dispatch_only_with_long_retention():
    for name, wf in RESEARCH.items():
        assert set(_triggers(wf)) == {"workflow_dispatch"}, name
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "event_name == 'push'" not in text and "head_commit" not in text, name
        for step in _steps(wf):
            if str(step.get("uses", "")).startswith("actions/upload-artifact"):
                assert step["with"]["retention-days"] == 90, (name, step.get("name"))


def test_full_matrices_are_reachable_from_dispatch():
    for name in ("lesson1-sumo-validation.yml", "robustness-sensitivity.yml"):
        wf = RESEARCH[name]
        assert wf["on"]["workflow_dispatch"]["inputs"]["run_full_matrix"]["type"] == "boolean"
        full = [s for s in _steps(wf) if "--seeds 1-30" in s.get("run", "") and "--dry-run" not in s["run"]]
        assert full and all(s["if"] == "${{ inputs.run_full_matrix }}" for s in full), name


def test_no_hard_coded_artifact_run_ids():
    for name, wf in ALL.items():
        for step in _steps(wf):
            if str(step.get("uses", "")).startswith("actions/download-artifact"):
                run_id = str(step.get("with", {}).get("run-id", ""))
                assert not re.fullmatch(r"\d+", run_id), f"{name}: literal run-id {run_id} expires"


def test_ci_runs_on_every_pull_request_and_main():
    on = _triggers(ALL["ci.yml"])
    assert on["push"] == {"branches": ["main"]}
    assert "pull_request" in on and not (on["pull_request"] or {}).get("paths")


def test_ci_installs_doctors_and_runs_the_whole_suite():
    runs = _runs(ALL["ci.yml"])
    assert 'python -m pip install -e ".[dev,fast]" -c requirements.lock' in runs
    assert "teamb doctor --skip-sim" in runs
    assert any(r.strip() in ("pytest", "python -m pytest") for r in runs), "run the full suite, not a selection"
    assert any("git ls-files" in r and "node --check" in r for r in runs)
    node_tests = [s for s in _steps(ALL["ci.yml"]) if s.get("run", "").strip() == "node --test tests/js/"]
    assert node_tests and "hashFiles('tests/js/**')" in node_tests[0]["if"]
    assert any("--strict-validation" in r and "teamb exp run" in r for r in runs)


def test_ci_builds_and_probes_the_docker_image():
    runs = "\n".join(_runs(ALL["ci.yml"]))
    assert "docker build" in runs
    assert "--entrypoint id" in runs and 'test "$uid" != "0"' in runs
    assert "'pytest', 'httpx'" in runs
    assert "/healthz" in runs and "exc.code == 401" in runs
    assert "SimEnv(" in runs and "sim.step()" in runs
