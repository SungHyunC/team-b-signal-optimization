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
