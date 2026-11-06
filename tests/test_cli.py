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
