"""Experiment runner: run identity, matrix parsing, resume and failure semantics (no SUMO)."""
from __future__ import annotations

import pytest

from teamb.experiments.runner import (
    RunSpec, build_matrix, name_collisions, parse_coverages, parse_seeds, validate_matrix,
)


# --- run identity (contract 3) -------------------------------------------------------------
def test_default_run_names_are_unchanged():
    assert RunSpec("rush_hour", "fixed_time", 1, 1.0).name == "rush_hour__fixed_time__s1__c100__uniform"
    assert RunSpec("rush_hour", "max_pressure", 2, 0.10).name == "rush_hour__max_pressure__s2__c10__uniform"
    assert RunSpec("rush_hour", "max_pressure", 2, 0.07).name == "rush_hour__max_pressure__s2__c7__uniform"
    assert RunSpec("emergency", "coordinated", 3, 1.0, ev_preemption=False).name == "emergency__coordinated__s3__c100__uniform__nopre"
    assert RunSpec("rush_hour", "max_pressure", 1, 0.5, "approach_biased:2").name.endswith("__c50__approach_biased-2")


def test_end_time_and_fractional_coverage_are_part_of_the_name():
    a = RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=420)
    b = RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=600.0)
    assert a.name == "rush_hour__fixed_time__s1__c100__uniform__e420" and b.name.endswith("__e600")
    assert RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=420.5).name.endswith("__e420.5")
    assert RunSpec("rush_hour", "fixed_time", 1, 1.0, ev_preemption=False, end_time=420).name.endswith("__nopre__e420")
    assert RunSpec("rush_hour", "max_pressure", 1, 0.125).name == "rush_hour__max_pressure__s1__c12.5__uniform"
    assert RunSpec("rush_hour", "max_pressure", 1, 0.001).name.endswith("__c0.1__uniform")
    names = {s.name for s in build_matrix(["rush_hour"], ["fixed_time"], [1], [0.12, 0.125])}
    assert len(names) == 2


# --- duplicates and collisions (evaluation-13, ext-89, ext-94) --------------------------------
def test_build_matrix_drops_repeated_list_entries():
    specs = build_matrix(["rush_hour"], ["fixed_time", "max_pressure", "fixed_time"], [1], [1.0],
                         samplings=["uniform", "uniform"], preemption=[True, True])
    assert len(specs) == 2 and len({s.name for s in specs}) == 2
    specs = build_matrix(["rush_hour", "rush_hour"], ["fixed_time"], [1, 1, 2], [1.0, 1.0])
    assert [s.name for s in specs] == ["rush_hour__fixed_time__s1__c100__uniform", "rush_hour__fixed_time__s2__c100__uniform"]


def test_validate_matrix_reports_name_collisions(monkeypatch):
    a, b = RunSpec("rush_hour", "fixed_time", 1, 0.12), RunSpec("rush_hour", "fixed_time", 1, 0.121)
    monkeypatch.setattr(RunSpec, "name", property(lambda self: "same"))  # the old lossy rounding
    problems = validate_matrix([a, b])
    assert any("run name collision" in p for p in problems)
    assert name_collisions([a, a]) == ["duplicate run: same appears 2 times"]


def test_run_matrix_refuses_specs_that_share_a_directory(tmp_path):
    from teamb.experiments.runner import run_matrix

    spec = RunSpec("rush_hour", "fixed_time", 1, 1.0)
    with pytest.raises(ValueError, match="duplicate run"):
        run_matrix([spec, spec], tmp_path, workers=1, quiet=True)
    assert not (tmp_path / "runs").exists()


# --- parsing (ext-90, ext-91) ---------------------------------------------------------------
def test_parse_seeds_rejects_reversed_ranges():
    assert parse_seeds("1-3,10,2") == [1, 2, 3, 10]
    with pytest.raises(ValueError, match="invalid seed range"):
        parse_seeds("5-1")
    with pytest.raises(ValueError):
        parse_seeds("1-3,9-7")


def test_parse_coverages_explicit_percent_is_always_percent():
    assert parse_coverages("1%,0.5%,50%,25%") == pytest.approx([0.01, 0.005, 0.5, 0.25])
    assert parse_coverages("0.1,0.25,1") == [0.1, 0.25, 1.0]
    assert parse_coverages("10,25,100") == [0.1, 0.25, 1.0]
    assert parse_coverages("default") == [None]
    names = {s.name for s in build_matrix(["rush_hour"], ["max_pressure_probe"], [1], parse_coverages("1%"))}
    assert names == {"rush_hour__max_pressure_probe__s1__c1__uniform"}


def test_cli_rejects_bad_matrices_before_running(capsys):
    from teamb.experiments.__main__ import main

    assert main(["run", "--name", "t", "--seeds", "5-1", "--dry-run"]) == 2
    assert "invalid seed range" in capsys.readouterr().err
    assert main(["run", "--name", "t", "--controllers", "fixed_time,fixed_time", "--seeds", "1", "--dry-run"]) == 0
    assert capsys.readouterr().out.strip().endswith("1 runs")


# --- run completeness and resume (evaluation-1, ext-94, contract 2) ---------------------------
import json  # noqa: E402
from dataclasses import asdict  # noqa: E402
from pathlib import Path  # noqa: E402

from teamb.experiments.runner import check_resume, run_one, run_status, spec_mismatch  # noqa: E402


class FakeEnv:
    """Stands in for SimEnv: writes a summary like SimEnv.close() does, then behaves as told."""

    behaviour = "ok"  # ok | raise | interrupt | truncate | legacy_ok
    calls = 0

    def __init__(self, scenario, controller, *, end_time=None, output_dir=None, **kwargs):
        self.end_time = float(end_time if end_time is not None else 4500.0)
        self.out = Path(output_dir)
        self.events = [{"t": 0.0, "type": "started"}]

    def run(self):
        FakeEnv.calls += 1
        partial = FakeEnv.behaviour in ("raise", "interrupt", "truncate")
        summary = {"mean_delay_s": 10.0, "sim_time_s": self.end_time / 2 if partial else self.end_time}
        if FakeEnv.behaviour == "ok":
            summary["complete"] = True
        (self.out / "summary.json").write_text(json.dumps(summary))
        if FakeEnv.behaviour == "raise":
            raise RuntimeError("boom at t=1000")
        if FakeEnv.behaviour == "interrupt":
            raise KeyboardInterrupt
        return summary


@pytest.fixture
def fake_env(monkeypatch):
    import teamb.sim.env

    monkeypatch.setattr(teamb.sim.env, "SimEnv", FakeEnv)
    FakeEnv.behaviour, FakeEnv.calls = "ok", 0
    return FakeEnv


SPEC = RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=600.0)


def test_failed_run_leaves_no_summary_and_is_rerun(tmp_path, fake_env):
    fake_env.behaviour = "raise"
    res = run_one(asdict(SPEC), str(tmp_path))
    out = tmp_path / SPEC.name
    assert res["status"] == "failed" and "boom" in res["error"]
    assert not (out / "summary.json").exists() and (out / "error.json").exists()
    assert run_status(out)[0] == "failed" and check_resume(SPEC, tmp_path) is None
    fake_env.behaviour = "ok"
    again = run_one(asdict(SPEC), str(tmp_path))
    assert again["status"] == "ok" and fake_env.calls == 2 and not (out / "error.json").exists()
    assert run_one(asdict(SPEC), str(tmp_path))["status"] == "skipped" and fake_env.calls == 2


def test_interrupted_run_writes_error_json_and_reraises(tmp_path, fake_env):
    fake_env.behaviour = "interrupt"
    with pytest.raises(KeyboardInterrupt):
        run_one(asdict(SPEC), str(tmp_path))
    out = tmp_path / SPEC.name
    err = json.loads((out / "error.json").read_text())
    assert err["interrupted"] is True and err["error"] == "KeyboardInterrupt"
    assert not (out / "summary.json").exists()
    fake_env.behaviour = "ok"
    assert run_one(asdict(SPEC), str(tmp_path))["status"] == "ok"


def test_truncated_or_unfinished_summaries_are_not_done(tmp_path, fake_env):
    out = tmp_path / SPEC.name
    out.mkdir(parents=True)
    (out / "run_spec.json").write_text(json.dumps(asdict(SPEC)))
    # a legacy summary (no "complete" key) from a run killed at t = 300 of 600
    (out / "summary.json").write_text(json.dumps({"mean_delay_s": 5.0, "sim_time_s": 300.0}))
    status, _, reason = run_status(out, expected_end=600.0)
    assert status == "incomplete" and "300" in reason
    assert check_resume(SPEC, tmp_path) is None
    (out / "summary.json").write_text(json.dumps({"mean_delay_s": 5.0, "sim_time_s": 600.0, "complete": False}))
    assert run_status(out)[0] == "incomplete"
    (out / "summary.json").write_text("")  # a worker killed mid-write
    assert run_status(out)[0] == "incomplete"
    assert run_one(asdict(SPEC), str(tmp_path))["status"] == "ok" and fake_env.calls == 1
    # the end time comes from the manifest when the spec has none
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "summary.json").write_text(json.dumps({"mean_delay_s": 5.0, "sim_time_s": 2411.0}))
    (legacy / "manifest.json").write_text(json.dumps({"config": {"end_time": 4500.0}}))
    assert run_status(legacy)[0] == "incomplete"
    (legacy / "summary.json").write_text(json.dumps({"mean_delay_s": 5.0, "sim_time_s": 4500.0}))
    assert run_status(legacy)[0] == "ok"


def test_resume_refuses_a_directory_that_holds_another_spec(tmp_path, fake_env):
    run_one(asdict(SPEC), str(tmp_path))
    out = tmp_path / SPEC.name
    saved = json.loads((out / "run_spec.json").read_text())
    saved["coverage"] = 0.125  # e.g. written under the old lossy name by another coverage
    (out / "run_spec.json").write_text(json.dumps(saved))
    res = run_one(asdict(SPEC), str(tmp_path))
    assert res["status"] == "failed" and res["error"].startswith("spec mismatch: coverage")
    assert fake_env.calls == 1 and (out / "summary.json").exists()  # the other run is kept
    assert run_one(asdict(SPEC), str(tmp_path), force=True)["status"] == "ok"


def _legacy_run(root, spec: RunSpec, *, sim_time: float, **saved):
    from teamb.experiments.runner import legacy_run_name

    old = root / legacy_run_name(spec)
    old.mkdir()
    (old / "run_spec.json").write_text(json.dumps({**asdict(spec), "name": old.name, **saved}))
    (old / "summary.json").write_text(json.dumps({"mean_delay_s": 5.0, "sim_time_s": sim_time}))
    return old


def test_resume_adopts_a_finished_run_from_its_legacy_folder_name(tmp_path, fake_env):
    from teamb.experiments.runner import _progress_line

    spec = RunSpec("rush_hour", "fixed_time", 1, 0.125, end_time=600.0)
    old = _legacy_run(tmp_path, spec, sim_time=600.0)
    assert old.name == "rush_hour__fixed_time__s1__c12__uniform" and spec.name.endswith("__c12.5__uniform__e600")
    res = run_one(asdict(spec), str(tmp_path))
    assert res["status"] == "skipped" and res["renamed_from"] == old.name and fake_env.calls == 0
    new = tmp_path / spec.name
    assert not old.exists() and (new / "summary.json").exists()
    assert json.loads((new / "run_spec.json").read_text())["name"] == spec.name
    assert "renamed from rush_hour__fixed_time__s1__c12__uniform" in _progress_line(1, 1, res)
    assert run_one(asdict(spec), str(tmp_path))["status"] == "skipped" and fake_env.calls == 0


def test_resume_leaves_other_legacy_folders_alone(tmp_path, fake_env):
    # a default run (no end_time) is not adopted by an explicit --end of the same length: its
    # folder is the default spec's own current name
    spec = RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=4500.0)
    old = _legacy_run(tmp_path, spec, sim_time=4500.0, end_time=None)
    assert run_one(asdict(spec), str(tmp_path))["status"] == "ok" and fake_env.calls == 1 and old.exists()
    # another coverage in the rounded folder, an unfinished run and a failed run are not adopted
    for i, (saved, sim, error) in enumerate((({"coverage": 0.12}, 600.0, False), ({}, 300.0, False), ({}, 600.0, True))):
        root = tmp_path / str(i)
        root.mkdir()
        spec = RunSpec("rush_hour", "fixed_time", 1, 0.125, end_time=600.0)
        old = _legacy_run(root, spec, sim_time=sim, **saved)
        if error:
            (old / "error.json").write_text(json.dumps({"error": "boom"}))
        assert check_resume(spec, root) is None and old.exists() and not (root / spec.name).exists()


def test_spec_mismatch_treats_default_end_as_the_scenario_duration():
    spec = RunSpec("rush_hour", "fixed_time", 1, 1.0)
    from teamb.experiments.runner import scenario_end

    duration = scenario_end(spec)
    assert duration and spec_mismatch({**asdict(spec), "end_time": duration}, spec) == []
    assert spec_mismatch({**asdict(spec), "end_time": 1200.0}, spec) == ["end_time (saved 1200.0, requested None)"]
    assert spec_mismatch({"seed": 1, "ev_preemption": True}, spec) == []


def test_report_keeps_failed_and_truncated_runs_out_of_the_statistics(tmp_path, fake_env):
    from teamb.experiments.analysis import build_report, load_runs, render_markdown
    from teamb.experiments.runner import run_matrix

    specs = [RunSpec("rush_hour", c, s, 1.0, end_time=600.0) for c in ("fixed_time", "coordinated") for s in (1, 2)]
    run_matrix(specs, tmp_path, workers=1, quiet=True)
    bad = tmp_path / "runs" / specs[3].name  # coordinated seed 2: truncated legacy summary
    (bad / "summary.json").write_text(json.dumps({"mean_delay_s": 1.0, "sim_time_s": 300.0}))
    fake_env.behaviour = "raise"
    failed = specs[2]
    run_one(asdict(failed), str(tmp_path / "runs"), force=True)
    status = {r["name"]: r["status"] for r in load_runs(tmp_path)}
    assert status[failed.name] == "failed" and status[specs[3].name] == "incomplete"
    report = build_report(tmp_path)
    assert [f["name"] for f in report["failed_runs"]] == [failed.name]
    assert [f["name"] for f in report["incomplete_runs"]] == [specs[3].name]
    assert all(r["controller"] != "coordinated" for r in report["rows"])
    assert "## Incomplete runs" in render_markdown(report)


def test_audit_rejects_a_truncated_run(tmp_path):
    from teamb.experiments.accuracy import audit_specs

    for spec in (SPEC, RunSpec("rush_hour", "max_pressure", 1, 1.0, end_time=600.0)):
        d = tmp_path / "runs" / spec.name
        d.mkdir(parents=True)
        (d / "run_spec.json").write_text(json.dumps(asdict(spec)))
        sim = 300.0 if spec.controller == "fixed_time" else 600.0
        (d / "summary.json").write_text(json.dumps({"mean_delay_s": 12.0, "sim_time_s": sim}))
        (d / "manifest.json").write_text(json.dumps({"seed": 1, "code_revision": "a", "sumo_version": "1", "network_hash": "n"}))
    audit = audit_specs(tmp_path, [SPEC, RunSpec("rush_hour", "max_pressure", 1, 1.0, end_time=600.0)])
    assert not audit["complete"] and audit["valid_runs"] == 1
    assert any("did not finish" in p for p in audit["problems"])


# --- workers and pool handling (opportunities: default workers, robust pool handling) -------------
def test_default_workers_uses_all_cores_but_one(monkeypatch):
    import teamb.experiments.runner as runner

    monkeypatch.setattr(runner.os, "cpu_count", lambda: 8)
    assert runner.default_workers(100) == 7 and runner.default_workers(3) == 3 and runner.default_workers(0) == 1
    assert runner.default_workers(100, "modal") == 2
    monkeypatch.setattr(runner.os, "cpu_count", lambda: None)
    assert runner.default_workers(100) == 1


def test_a_dead_worker_becomes_a_failed_run(tmp_path, monkeypatch):
    from concurrent.futures import Future
    from concurrent.futures.process import BrokenProcessPool

    import teamb.experiments.runner as runner

    class DeadPool:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def submit(self, fn, spec_dict, *args):
            fut = Future()
            if spec_dict["seed"] == 2:
                fut.set_exception(BrokenProcessPool("a child process terminated abruptly"))
            else:
                fut.set_result({"run": RunSpec(**spec_dict).name, "status": "ok", "summary": {}})
            return fut

    monkeypatch.setattr(runner, "ProcessPoolExecutor", DeadPool)
    specs = [RunSpec("rush_hour", "fixed_time", s, 1.0) for s in (1, 2, 3)]
    record = runner.run_matrix(specs, tmp_path, workers=3, quiet=True)
    assert record["ok"] == 2 and record["failed"] == [specs[1].name]
    meta = json.loads((tmp_path / "experiment.json").read_text())
    assert meta["invocations"][-1]["failed"] == [specs[1].name] and meta["invocations"][-1]["workers"] == 3


def test_interrupted_matrix_still_records_the_invocation(tmp_path, fake_env):
    from teamb.experiments.runner import run_matrix

    specs = [RunSpec("rush_hour", "fixed_time", s, 1.0, end_time=600.0) for s in (1, 2, 3)]
    run_matrix(specs[:1], tmp_path, workers=1, quiet=True)
    fake_env.behaviour = "interrupt"
    with pytest.raises(KeyboardInterrupt):
        run_matrix(specs, tmp_path, workers=1, quiet=True)
    inv = json.loads((tmp_path / "experiment.json").read_text())["invocations"]
    assert len(inv) == 2 and inv[-1]["interrupted"] is True
    assert inv[-1]["skipped"] == 1 and inv[-1]["not_run"] == 2


# --- --controller-params (ext-92) -----------------------------------------------------------
def test_controller_params_forms(capsys):
    from teamb.experiments.runner import split_controller_params

    with pytest.raises(ValueError, match="mixes per-controller keys"):
        split_controller_params({"max_pressure": {"margin": 4}, "min_green": 5}, ["max_pressure", "fixed_time"])
    with pytest.raises(ValueError, match="must be an object"):
        split_controller_params({"max_pressure": 4}, ["max_pressure"])
    assert split_controller_params({"offsets": {"J1": 10}}, ["fixed_time"]) == {"fixed_time": {"offsets": {"J1": 10}}}
    assert split_controller_params({"min_green": 5}, ["fixed_time", "max_pressure"]) == {
        "fixed_time": {"min_green": 5}, "max_pressure": {"min_green": 5}}
    # a registered controller that is not selected (added by a later invocation) is ignored
    per = split_controller_params({"ai_recommender": {"auto_approve": True}}, ["fixed_time"])
    assert per == {"fixed_time": {}} and "ignored" in capsys.readouterr().err
    specs = build_matrix(["rush_hour"], ["fixed_time"], [1], [1.0], controller_params={"ai_recommender": {"auto_approve": True}})
    assert specs[0].name == "rush_hour__fixed_time__s1__c100__uniform"


def test_validate_matrix_catches_unknown_controller_parameters():
    def problems(params, controllers=("max_pressure",)):
        return validate_matrix(build_matrix(["rush_hour"], list(controllers), [1], [1.0], controller_params=params))

    assert any("max_presure" in p for p in problems({"max_presure": {"margin": 4}}))  # typo'd controller name
    assert any("'margn'" in p for p in problems({"margn": 4}))
    assert any("'margn'" in p for p in problems({"max_pressure": {"margn": 4}}))
    assert not problems({"max_pressure": {"margin": 4}})
    assert not problems({"min_green": 5}, ("fixed_time", "max_pressure"))  # global key used by one of them
    assert not problems({"ai_recommender": {"auto_approve": True}}, ("fixed_time", "coordinated", "ai_recommender"))
    assert not problems({"max_pressure_probe": {"defense": True}}, ("fixed_time", "max_pressure_probe"))
