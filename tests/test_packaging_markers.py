"""The automatic ``sumo`` marker (tests/conftest.py) behind the quick tier ``pytest -m "not sumo"``."""
from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("teamb_tests_conftest", ROOT / "tests" / "conftest.py")
conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conftest)

SAMPLE = '''
from teamb.sim.env import SimEnv


def _helper(tmp):
    return run_matrix([], tmp)


def direct(tmp_path):
    SimEnv("rush_hour", "fixed_time", end_time=60, output_dir=tmp_path).run()


def via_helper(tmp_path):
    assert _helper(tmp_path)


def only_mentions():
    """Follows the SimEnv.frame() contract."""
    # traci would be started by SimEnv, but not here
    assert "SimEnv(" != "traci"


def live_session(client):
    client.post("/api/session?wait=1", json={"scenario": "rush_hour"})


def rejected_session(client):
    assert client.post("/api/session", json={"controller": "nope"}).status_code == 400


def pure():
    assert 1 + 1 == 2
'''


@pytest.fixture()
def sample_module(tmp_path, monkeypatch):
    path = tmp_path / "sample_sumo_tests.py"
    path.write_text(textwrap.dedent(SAMPLE))
    spec = importlib.util.spec_from_file_location("sample_sumo_tests", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "sample_sumo_tests", module)
    # a stand-in simulator module (spelled as a string so this test itself is not marked sumo)
    monkeypatch.setitem(sys.modules, "teamb.sim.env", SimpleNamespace(**{"SimEnv": object}))
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name,expected", [
    ("direct", True), ("via_helper", True), ("live_session", True),
    ("only_mentions", False), ("rejected_session", False), ("pure", False),
])
def test_starts_sumo_heuristic(sample_module, name, expected):
    item = SimpleNamespace(function=getattr(sample_module, name), module=sample_module, _fixtureinfo=None)
    assert conftest.starts_sumo(item) is expected


def test_marker_is_registered_and_applied(request):
    registered = [line.split(":", 1)[0] for line in request.config.getini("markers")]
    assert "sumo" in registered and "slow" in registered
    by_id = {it.nodeid: it for it in request.session.items}
    known = "tests/test_core.py::test_rep01_same_seed_same_result_and_perf01_fields"
    if known not in by_id:
        pytest.skip("run together with tests/test_core.py to check a real SUMO test")
    assert by_id[known].get_closest_marker("sumo") is not None
    assert by_id["tests/test_core.py::test_net01_four_junctions_with_all_movements"].get_closest_marker("sumo") is None
    assert request.node.get_closest_marker("sumo") is None
