"""Sandbox launch readiness checks: web route, static JS, and JSON contract."""
import json
import shlex

import pytest
from fastapi.testclient import TestClient

import teamb.experiments.__main__ as experiments_cli
from teamb.experiments.runner import build_matrix
from teamb.sandbox import SCENARIO_NAMES, experiment_command, parse_sandbox_config
from teamb.twin.server import create_app


def test_sandbox_page_and_twin_navigation():
    app = create_app()
    # A plain client does not enter FastAPI lifespan, so no SUMO process starts.
    client = TestClient(app)
    home = client.get("/")
    page = client.get("/static/sandbox.html")
    script = client.get("/static/js/sandbox.js")
    assert home.status_code == page.status_code == script.status_code == 200
    assert 'href="./static/sandbox.html"' in home.text
    assert 'href="/"' in page.text
    assert 'id="preview"' in page.text
    assert 'id="command"' in page.text
    assert "function validate(v)" in script.text
    assert 'schema_version:1' in script.text


def test_sandbox_schema_endpoint(monkeypatch):
    """Contract 5: the builder's allowed values, straight from the registries."""
    from teamb.controllers import REGISTRY as CONTROLLERS
    from teamb.scenarios import REGISTRY as SCENARIOS

    monkeypatch.delenv("TWIN_ACCESS_TOKEN", raising=False)
    r = TestClient(create_app()).get("/api/sandbox/schema")
    assert r.status_code == 200
    assert r.json() == {
        "schema_version": 1,
        "scenarios": list(SCENARIOS),
        "controllers": list(CONTROLLERS),
        "limits": {"seed": [0, 2147483647], "demand_scale": [0.1, 3.0], "duration_s": [1200, 10800]},
    }
    assert "fake_data_attack" in r.json()["scenarios"]


def test_sandbox_exports_reproduce_experiment_spec():
    from teamb.experiments.runner import validate_matrix
    cfg = parse_sandbox_config({
        "scenario": "road_closure",
        "controller": "max_pressure",
        "seed": 33,
        "demand_scale": 1.25,
        "ev_preemption": True,
        "duration_s": None,
        "schema_version": 1,
    })
    specs = build_matrix(**cfg.experiment_kwargs())
    assert len(specs) == 1 and not validate_matrix(specs)
    spec = specs[0]
    assert spec.seed == 33 and spec.controller == "max_pressure"
    assert spec.scenario_params == {"demand_scale": 1.25}
    assert parse_sandbox_config(cfg.to_json()) == cfg


# --- the displayed command gives exactly the runs of the JSON contract (integration-6) --------
def _cli_specs(argv: list[str], monkeypatch, capsys) -> list:
    """Run `python -m teamb.experiments <argv> --dry-run` and return the specs it built."""
    built = []

    def capture(*args, **kwargs):
        specs = build_matrix(*args, **kwargs)
        built.append(specs)
        return specs

    monkeypatch.setattr(experiments_cli, "build_matrix", capture)
    assert experiments_cli.main(argv + ["--dry-run"]) == 0
    capsys.readouterr()
    assert len(built) == 1
    return built[0]


def _js_argv(cfg) -> list[str]:
    """The command teamb/twin/static/js/sandbox.js shows (JSON.stringify writes 1, not 1.0)."""
    demand = cfg.demand_scale
    demand = int(demand) if float(demand).is_integer() else demand
    params = json.dumps({"demand_scale": demand}, separators=(",", ":"))
    argv = ["run", "--name", "sandbox_trial", "--scenarios", cfg.scenario, "--controllers", cfg.controller,
            "--seeds", str(cfg.seed), "--ev-preemption", "on" if cfg.ev_preemption else "off", "--scenario-params", params]
    return argv + ([] if cfg.duration_s is None else ["--end", str(cfg.duration_s)])


@pytest.mark.parametrize("scenario", SCENARIO_NAMES)
@pytest.mark.parametrize("demand,duration,ev", [(1, None, True), (1.0, 1800, False), (1.25, 10800, True)])
def test_displayed_commands_build_the_contract_specs(scenario, demand, duration, ev, monkeypatch, capsys):
    cfg = parse_sandbox_config({"scenario": scenario, "controller": "max_pressure_probe", "seed": 1,
                                "demand_scale": demand, "ev_preemption": ev, "duration_s": duration})
    expected = build_matrix(**cfg.experiment_kwargs())
    assert len(expected) == 1

    argv = shlex.split(experiment_command(cfg))
    assert argv[:3] == ["teamb", "exp", "run"]
    python_specs = _cli_specs(argv[2:], monkeypatch, capsys)
    assert python_specs == expected and [s.name for s in python_specs] == [s.name for s in expected]

    js_specs = _cli_specs(_js_argv(cfg), monkeypatch, capsys)
    assert js_specs == expected and [s.name for s in js_specs] == [s.name for s in expected]
    if scenario == "fake_data_attack":
        assert expected[0].coverage == 0.25  # the scenario's own probe coverage, as designed


def test_js_command_template_matches_the_tested_flags():
    """If the page's command builder changes, _js_argv (and this contract) must change with it.

    The builder lives in sandbox_schema.js (a DOM-free module the sandbox page imports)."""
    client = TestClient(create_app())
    script = client.get("/static/js/sandbox_schema.js").text
    for flag in ("--scenarios", "--controllers", "--seeds", "--ev-preemption", "--scenario-params", "--end"):
        assert f"'{flag}'" in script, flag
    assert "--coverages" not in script  # coverage = the scenario default on both sides
