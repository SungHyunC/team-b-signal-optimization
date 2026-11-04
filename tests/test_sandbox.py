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
])
def test_rejects_invalid_or_untrusted_configuration(bad):
    with pytest.raises((ValueError, TypeError)):
        parse_sandbox_config(bad)
