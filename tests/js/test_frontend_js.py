"""Frontend logic tests and the Python halves of the browser <-> Python contracts.

The JavaScript tests live next to this file (tests/js/*.test.mjs) and run with plain Node 20.6
or later, no npm install:  node --test tests/js/*.test.mjs
(Name the files: Node 21+ reads each argument as a glob, so a bare directory runs as one failing
"test".) test_node_suite() runs them from pytest; it is skipped when node is missing or older
than 20.6, which the suite needs for module.register().

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


@pytest.mark.parametrize("item", SANDBOX["commands"], ids=lambda c: f'{c["config"]["scenario"]}-{c["config"]["controller"]}')
def test_sandbox_fixture_command_matches_python(item):
    from teamb.sandbox import experiment_command, parse_sandbox_config

    assert experiment_command(parse_sandbox_config(item["config"])) == item["exp_run"]


def test_sandbox_fixture_has_a_command_for_every_headless_controller():
    """A controller that gets --controller-params in a sandbox run needs a shared command case, or
    the page's experimentCommand() can drop the parameters without either contract test noticing."""
    from teamb.sandbox import HEADLESS_CONTROLLER_PARAMS

    covered = {c["config"].get("controller") for c in SANDBOX["commands"]}
    assert set(HEADLESS_CONTROLLER_PARAMS) <= covered


def _js_list(name: str) -> set[str]:
    text = (STATIC_JS / "sandbox_schema.js").read_text()
    body = re.search(rf"{name}: Object\.freeze\(\[([^\]]*)\]\)", text).group(1)
    return set(re.findall(r"'([^']+)'", body))


def test_sandbox_page_built_in_lists_match_python():
    """Static GitHub Pages has no /api/sandbox/schema: its built-in lists must be what teamb.sandbox accepts."""
    from teamb import sandbox

    assert _js_list("scenarios") == set(sandbox.SCENARIOS)
    assert _js_list("controllers") == set(sandbox.CONTROLLERS)


NODE_MIN = (20, 6)  # module.register(), used by the tests that stub three.js


def parse_node_version(text: str) -> tuple[int, int] | None:
    """(major, minor) from `node --version` output such as 'v24.19.0'; None if it is not one."""
    m = re.match(r"\s*v?(\d+)\.(\d+)", text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def node_test_files() -> list[str]:
    """The suite's files, relative to the repo root, for `node --test <files>`."""
    return sorted(p.relative_to(ROOT).as_posix() for p in HERE.glob("*.test.mjs"))


def test_parse_node_version():
    assert parse_node_version("v24.19.0\n") == (24, 19)
    assert parse_node_version("v20.6.0") == (20, 6)
    assert parse_node_version("20.20.2") == (20, 20)
    assert parse_node_version("") is None
    assert parse_node_version("node: command not found") is None


def test_node_test_files_names_every_test_file():
    files = node_test_files()
    assert files and all(f.startswith("tests/js/") and f.endswith(".test.mjs") for f in files)
    assert len(files) == len(list(HERE.glob("*.test.mjs")))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_node_suite():
    version = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=30).stdout
    found = parse_node_version(version)
    if found is not None and found < NODE_MIN:
        pytest.skip(f"node {version.strip()} is older than {NODE_MIN[0]}.{NODE_MIN[1]} (module.register)")
    # Explicit files, not the directory: Node 21+ treats a directory argument as a single test file.
    proc = subprocess.run(["node", "--test", *node_test_files()], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-6000:] + proc.stderr[-3000:]


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    fx = build_vehicle_fixture()
    frames = ",\n  ".join(json.dumps(f) for f in fx["frames"])
    text = f'{{"ids": {json.dumps(fx["ids"])}, "kinds": {json.dumps(fx["kinds"])}, "frames": [\n  {frames}\n]}}\n'
    (FIXTURES / "vehicles.json").write_text(text)
    print(f"wrote {FIXTURES / 'vehicles.json'}")
