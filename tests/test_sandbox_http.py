"""Sandbox launch readiness checks: web route, static JS, and JSON contract."""
from pathlib import Path

from fastapi.testclient import TestClient
from teamb.sandbox import parse_sandbox_config
from teamb.twin.server import create_app, STATIC_DIR


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


def test_sandbox_exports_reproduce_experiment_spec():
    from teamb.experiments.runner import build_matrix, validate_matrix
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
