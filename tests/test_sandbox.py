"""Fast, SUMO-independent checks for the scenario sandbox JSON contract."""
import pytest

from teamb.sandbox import SandboxConfig, parse_sandbox_config


def test_round_trip_and_runner_arguments():
    cfg = SandboxConfig(scenario="emergency", seed=7, demand_scale=1.25, ev_preemption=False)
    restored = parse_sandbox_config(cfg.to_json())
    assert restored == cfg
    args = restored.experiment_kwargs()
    assert args["scenarios"] == ["emergency"]
    assert args["seeds"] == [7]
    assert args["preemption"] == [False]
    assert args["scenario_params"] == {"demand_scale": 1.25}


@pytest.mark.parametrize("bad", [
    {"scenario": "unknown"}, {"controller": "arbitrary_python"},
    {"seed": -1}, {"seed": True}, {"demand_scale": 0},
    {"demand_scale": float("nan")}, {"ev_preemption": "off"},
    {"duration_s": 10}, {"schema_version": 2}, {"untrusted": "value"},
    # contract 5 / sim-core-10: ending inside the 900 s warm-up measures nothing
    {"duration_s": 600}, {"duration_s": 900}, {"duration_s": 1199}, {"duration_s": 10801},
    {"duration_s": 1800.0}, {"duration_s": True},
])
def test_rejects_invalid_or_untrusted_configuration(bad):
    with pytest.raises((ValueError, TypeError)):
        parse_sandbox_config(bad)


@pytest.mark.parametrize("duration", [None, 1200, 1800, 10800])
def test_accepts_durations_with_a_measurement_window(duration):
    assert parse_sandbox_config({"duration_s": duration}).duration_s == duration


def test_allow_lists_come_from_the_registries():
    from teamb.controllers import REGISTRY as CONTROLLERS
    from teamb.scenarios import REGISTRY as SCENARIOS, get_scenario
    from teamb import sandbox

    assert sandbox.SCENARIOS == set(SCENARIOS) and sandbox.CONTROLLERS == set(CONTROLLERS)
    assert sandbox.schema() == {
        "schema_version": 1,
        "scenarios": list(SCENARIOS),
        "controllers": list(CONTROLLERS),
        "limits": {"seed": [0, 2147483647], "demand_scale": [0.1, 3.0], "duration_s": [1200, 10800]},
    }
    # The shortest allowed duration still measures >= 300 s in every scenario.
    for name in SCENARIOS:
        assert get_scenario(name).warmup + sandbox.MIN_MEASURED_S <= sandbox.DURATION_RANGE[0], name
        parse_sandbox_config({"scenario": name, "duration_s": sandbox.DURATION_RANGE[0]})


def test_cli_validate(tmp_path, capsys):
    from teamb.sandbox import main

    good = tmp_path / "ok.json"
    good.write_text(SandboxConfig(scenario="fake_data_attack", duration_s=1800).to_json())
    assert main(["validate", str(good)]) == 0
    out = capsys.readouterr().out
    assert "teamb exp run" in out and "--end 1800" in out and "--coverages" not in out
    bad = tmp_path / "short.json"
    bad.write_text('{"duration_s": 600}')
    assert main(["validate", str(bad)]) == 2
    assert "duration_s" in capsys.readouterr().out


HEADLESS_AI = {"ai_recommender": {"auto_approve": True}}


def test_ai_recommender_exports_approve_the_plan_headless():
    """No engineer can approve in a sandbox run: like `teamb run`, the AI plan is auto-approved."""
    from teamb.experiments.runner import build_matrix

    cfg = parse_sandbox_config({"controller": "ai_recommender", "duration_s": 1200})
    assert cfg.experiment_kwargs()["controller_params"] == HEADLESS_AI
    (spec,) = build_matrix(**cfg.experiment_kwargs())
    assert spec.controller_params == {"auto_approve": True}
    assert "controller_params" not in parse_sandbox_config({"controller": "max_pressure"}).experiment_kwargs()


@pytest.mark.parametrize("controller", ["ai_recommender", "max_pressure"])
def test_the_equivalent_command_builds_the_same_spec(controller, monkeypatch, capsys):
    import shlex

    import teamb.experiments.__main__ as experiments_cli
    from teamb.experiments.runner import build_matrix
    from teamb.sandbox import experiment_command

    cfg = parse_sandbox_config({"controller": controller, "seed": 4, "duration_s": 1500})
    built = []
    monkeypatch.setattr(experiments_cli, "build_matrix", lambda *a, **k: built.append(build_matrix(*a, **k)) or built[-1])
    argv = shlex.split(experiment_command(cfg))
    assert experiments_cli.main(argv[2:] + ["--dry-run"]) == 0
    capsys.readouterr()
    assert built == [build_matrix(**cfg.experiment_kwargs())]
    assert ("--controller-params" in argv) is (controller == "ai_recommender")


def _stub_runner(monkeypatch, tmp_path, failed=()):
    """sandbox main()'s runner and report, without SUMO: records the specs it was given."""
    import teamb.experiments.analysis as analysis
    import teamb.experiments.runner as runner

    seen = {}

    def fake_run_matrix(specs, exp_dir, **kwargs):
        seen.update(specs=specs, exp_dir=exp_dir, **kwargs)
        for spec in specs:
            out = exp_dir / "runs" / spec.name
            out.mkdir(parents=True)
            (out / "summary.json").write_text('{"mean_delay_s": 12.5, "completed": 10}')
        return {"failed": list(failed)}

    monkeypatch.setattr(runner, "EXPERIMENTS_DIR", tmp_path / "experiments")
    monkeypatch.setattr(runner, "run_matrix", fake_run_matrix)
    monkeypatch.setattr(analysis, "write_report", lambda exp_dir, baseline: seen.update(report=baseline))
    return seen


def test_cli_run_passes_the_contract_specs_to_the_runner(tmp_path, monkeypatch, capsys):
    from teamb.sandbox import experiment_command, main

    cfg = SandboxConfig(controller="ai_recommender", seed=3, duration_s=1200)
    path = tmp_path / "trial.json"
    path.write_text(cfg.to_json())
    seen = _stub_runner(monkeypatch, tmp_path)
    assert main(["run", str(path), "--name", "trial"]) == 0
    (spec,) = seen["specs"]
    assert spec.controller == "ai_recommender" and spec.controller_params == {"auto_approve": True}
    assert seen["command"] == experiment_command(cfg, "trial") and seen["backend"] == "local"
    assert seen["report"] == "ai_recommender"
    assert "12.5" in capsys.readouterr().out


def test_cli_run_reports_a_failed_run(tmp_path, monkeypatch, capsys):
    from teamb.sandbox import main

    path = tmp_path / "trial.json"
    path.write_text(SandboxConfig(duration_s=1200).to_json())
    seen = _stub_runner(monkeypatch, tmp_path, failed=["x"])
    assert main(["run", str(path)]) == 1
    assert "run failed" in capsys.readouterr().out and "report" not in seen
