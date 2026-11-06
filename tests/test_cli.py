"""The unified `teamb` command: dispatch, argument validation and delegation."""
import json

import pytest

from teamb.__main__ import DELEGATES, main


def test_list_prints_controllers_and_scenarios(capsys):
    assert main(["list"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {"max_pressure", "rl", "ai_recommender"} <= {c["name"] for c in data["controllers"]}
    assert "road_closure" in {s["name"] for s in data["scenarios"]}


@pytest.mark.parametrize("bad", ["50", "0", "-0.1", "nan", "inf", "abc"])
def test_run_rejects_coverage_outside_unit_interval(bad, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["run", "--coverage", bad])
    assert exc.value.code == 2
    assert "coverage" in capsys.readouterr().err


def test_run_refuses_an_end_inside_the_warmup():
    with pytest.raises(SystemExit, match="warm-up"):
        main(["run", "--end", "300"])


def test_run_rejects_bad_json_params():
    with pytest.raises(SystemExit, match="--scenario-params"):
        main(["run", "--scenario-params", "{nope", "--end", "1200"])


@pytest.mark.parametrize("command", sorted(DELEGATES))
def test_every_delegate_answers_help(command, capsys):
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_top_level_help_lists_the_research_commands(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for command in ("twin", "run", "doctor", "exp", "sandbox", "train-rl", "site"):
        assert command in out


@pytest.fixture
def fake_env(monkeypatch):
    """`teamb run` without SUMO: the environment records what it was built with."""
    import teamb.sim.env as env_module

    seen = {}

    class FakeEnv:
        output_dir = "fake-output"

        def __init__(self, scenario, controller, **kwargs):
            seen.update(scenario=scenario, controller=controller, **kwargs)

        def run(self):
            return {"mean_delay_s": 1.0}

    monkeypatch.setattr(env_module, "SimEnv", FakeEnv)
    return seen


def test_headless_ai_recommender_run_auto_approves_by_default(fake_env, capsys):
    assert main(["run", "--controller", "ai_recommender", "--end", "1200"]) == 0
    assert fake_env["controller_params"] == {"auto_approve": True}
    assert "auto_approve=true" in capsys.readouterr().out


def test_an_explicit_auto_approve_false_is_kept(fake_env, capsys):
    assert main(["run", "--controller", "ai_recommender", "--controller-params", '{"auto_approve": false}',
                 "--end", "1200"]) == 0
    assert fake_env["controller_params"] == {"auto_approve": False}
    assert "starting plan" in capsys.readouterr().out


def test_run_rejects_a_misspelled_controller_parameter(fake_env):
    with pytest.raises(SystemExit, match="intervl"):
        main(["run", "--controller", "max_pressure", "--controller-params", '{"intervl": 5}', "--end", "1200"])
    assert not fake_env, "nothing ran"


def test_run_accepts_a_real_controller_parameter(fake_env):
    assert main(["run", "--controller", "max_pressure", "--controller-params", '{"interval": 5}', "--end", "1200"]) == 0
    assert fake_env["controller_params"] == {"interval": 5}


def test_run_rejects_an_unknown_controller(fake_env):
    with pytest.raises(SystemExit, match="unknown controller 'max_presure'"):
        main(["run", "--controller", "max_presure", "--end", "1200"])
    assert not fake_env
