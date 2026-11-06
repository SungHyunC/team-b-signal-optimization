"""Frontend logic tests and the Python halves of the browser <-> Python contracts.

The JavaScript tests live next to this file (tests/js/*.test.mjs) and run with plain Node 20,
no npm install:  node --test tests/js/
test_node_suite() runs them from pytest (skipped when node is not installed).

Shared fixtures, checked from both languages:
- fixtures/vehicles.json: frames encoded by teamb.twin.site.encode_vehicles. replay.test.mjs
  decodes them with replay.js decodeVehicles; here they must still match the encoder and the
  Python decoder. Regenerate after an intended encoder change:  python tests/js/test_frontend_js.py
- fixtures/sandbox_cases.json: Scenario Sandbox files and the verdict, plus `teamb exp run`
  commands. sandbox_schema.test.mjs checks the browser validator; here teamb.sandbox.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURES = HERE / "fixtures"

# Vehicles leave and enter, change order and kind, and cross the 359 -> 0 degree wrap.
VEHICLE_FRAMES = [
    [("car_0", 10.04, -3.56, 359.4, 12.34, "car"), ("probe_1", 0.0, 0.0, 90.0, 0.0, "probe")],
    [("car_0", 10.5, -3.0, 0.6, 13.0, "car"), ("ambulance_2", 100.0, 50.25, 180.0, 20.0, "ambulance")],
    [("ambulance_2", 98.7, 50.2, 179.5, 19.6, "ambulance"), ("car_0", 11.0, -2.5, 359.0, 0.0, "probe")],
    [("probe_1", -5.55, 7.07, 270.2, 4.4, "probe"), ("car_0", 11.0, -2.5, 1.0, 0.0, "probe")],
    [],
    [("car_0", 12.0, -2.0, 2.0, 1.0, "probe")],
]


def build_vehicle_fixture() -> dict:
    from teamb.twin.site import decode_vehicles, encode_vehicles

    ids: dict = {}
    kinds: dict = {}
    prev_enc: dict = {}
    flats = [encode_vehicles([list(v) for v in frame], ids, kinds, prev_enc) for frame in VEHICLE_FRAMES]
    id_list, kind_list = list(ids), list(kinds)
    prev_dec: dict = {}
    frames = [{"flat": flat, "vehicles": decode_vehicles(flat, id_list, kind_list, prev_dec)} for flat in flats]
    return {"ids": id_list, "kinds": kind_list, "frames": frames}


def test_vehicle_fixture_matches_the_python_encoder():
    fixture = json.loads((FIXTURES / "vehicles.json").read_text())
    assert fixture == build_vehicle_fixture(), "regenerate: python tests/js/test_frontend_js.py"
    # and the decoded frames are the inputs at the encoding's resolution (dm, whole degrees)
    for frame, decoded in zip(VEHICLE_FRAMES, fixture["frames"]):
        assert [v[0] for v in decoded["vehicles"]] == [v[0] for v in frame]
        for (vid, x, y, a, s, kind), (_, dx, dy, da, ds, dkind) in zip(frame, decoded["vehicles"]):
            assert (dx, dy, da, ds, dkind) == (round(x * 10) / 10, round(y * 10) / 10, round(a) % 360, round(s * 10) / 10, kind)


SANDBOX = json.loads((FIXTURES / "sandbox_cases.json").read_text())
STATIC_JS = ROOT / "teamb" / "twin" / "static" / "js"


def _python_accepts(text: str) -> bool:
    from teamb.sandbox import parse_sandbox_config

    try:
        parse_sandbox_config(text)
    except (ValueError, TypeError):
        return False
    return True


def _python_has_contract5() -> bool:
    """teamb/sandbox.py rejects durations under 1200 s (contract 5; stream E1 owns that file)."""
    return not _python_accepts('{"duration_s": 600}')


@pytest.mark.parametrize("case", SANDBOX["cases"], ids=lambda c: c["name"])
def test_sandbox_fixture_verdict_matches_python(case):
    if case.get("contract5") and not _python_has_contract5():
        pytest.skip("teamb/sandbox.py still allows durations under 1200 s (contract 5 pending)")
    assert _python_accepts(case["text"]) is case["ok"]


@pytest.mark.parametrize("item", SANDBOX["commands"], ids=lambda c: c["config"]["scenario"])
def test_sandbox_fixture_command_matches_python(item):
    from teamb.sandbox import experiment_command, parse_sandbox_config

    assert experiment_command(parse_sandbox_config(item["config"])) == item["exp_run"]


def _js_list(name: str) -> set[str]:
    text = (STATIC_JS / "sandbox_schema.js").read_text()
    body = re.search(rf"{name}: Object\.freeze\(\[([^\]]*)\]\)", text).group(1)
    return set(re.findall(r"'([^']+)'", body))


def test_sandbox_page_built_in_lists_match_python():
    """Static GitHub Pages has no /api/sandbox/schema: its built-in lists must be what teamb.sandbox accepts."""
    from teamb import sandbox

    assert _js_list("scenarios") == set(sandbox.SCENARIOS)
    assert _js_list("controllers") == set(sandbox.CONTROLLERS)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_node_suite():
    proc = subprocess.run(["node", "--test", "tests/js/"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-6000:] + proc.stderr[-3000:]


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    fx = build_vehicle_fixture()
    frames = ",\n  ".join(json.dumps(f) for f in fx["frames"])
    text = f'{{"ids": {json.dumps(fx["ids"])}, "kinds": {json.dumps(fx["kinds"])}, "frames": [\n  {frames}\n]}}\n'
    (FIXTURES / "vehicles.json").write_text(text)
    print(f"wrote {FIXTURES / 'vehicles.json'}")
