"""Online demo (teamb/twin/site.py): vehicle encoding, a short recorded run, the static page.

One test records a 7-minute SUMO run, so this file takes a few seconds.
"""
from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from teamb.controllers import REGISTRY as CONTROLLERS
from teamb.scenarios import REGISTRY as SCENARIOS
from teamb.twin import site


def test_vehicle_encoding_roundtrip():
    frames = [
        [["a", 10.04, -4.8, 359.6, 13.33, "car"], ["b", 0.0, 0.0, 90.0, 0.0, "probe"]],
        [["a", 23.41, -4.8, 0.4, 13.4, "car"], ["c", -300.0, 4.8, 270.0, 8.0, "ambulance"]],  # b left, c new, a wraps 360 -> 0
        [["c", -290.0, 4.8, 270.0, 9.0, "ambulance"], ["a", 36.0, -4.8, 1.0, 12.0, "probe"]],  # a changed kind, order changed
    ]
    ids, kinds, enc_prev, dec_prev = {}, {}, {}, {}
    for vehicles in frames:
        flat = site.encode_vehicles(vehicles, ids, kinds, enc_prev)
        assert all(isinstance(n, int) for n in flat)
        decoded = site.decode_vehicles(flat, list(ids), list(kinds), dec_prev)
        assert [v[0] for v in decoded] == [v[0] for v in vehicles]
        for (vid, x, y, a, s, k), (did, dx, dy, da, ds, dk) in zip(vehicles, decoded):
            assert (dx, dy, ds) == pytest.approx((x, y, s), abs=0.051)
            assert min(abs(da - a) % 360, 360 - abs(da - a) % 360) <= 0.5
            assert dk == k
    # a vehicle seen in the previous frame costs 5 numbers, a new one 6
    assert len(site.encode_vehicles([["c", -280.0, 4.8, 270.0, 9.0, "ambulance"]], ids, kinds, enc_prev)) == 5


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    out = tmp_path_factory.mktemp("runs")
    run = site.DemoRun("emergency", "max_pressure", "test run")
    res = site.record_run(asdict(run), str(out), end_time=420)
    return out / run.id, res


def test_recorded_run_is_complete(recorded):
    folder, res = recorded
    info = json.loads((folder / "run.json").read_text())
    assert info["end_t"] == 420 and res["frames"] == 421  # t = 0 .. 420, one frame per second
    assert [c["t0"] for c in info["chunks"]] == [0, 300]
    assert info["status"]["config"]["scenario"] == "emergency" and info["frame_controller"] == "max_pressure"
    assert "mean_delay_s" in info["status"]["summary"]  # what the "Run finished" overlay shows
    assert info["events"] and info["events"][0]["type"] == "started"
    kpi_t = [k["t"] for k in info["kpi_history"]]
    assert kpi_t == sorted(kpi_t) and len(kpi_t) > 50


def test_every_chunk_starts_complete_and_decodes(recorded):
    folder, _ = recorded
    info = json.loads((folder / "run.json").read_text())
    seen = 0
    for meta_chunk in info["chunks"]:
        chunk = json.loads((folder / meta_chunk["file"]).read_text())
        first = chunk["frames"][0]
        assert first["t"] == meta_chunk["t0"]
        assert {"signals", "kpi", "closures", "coverage"} <= set(first), "a chunk must not depend on the previous one"
        assert not set(site.PER_FRAME[3:]) & set(first)  # scenario and controller live in run.json
        prev: dict = {}
        for raw in chunk["frames"]:
            vehicles = site.decode_vehicles(raw["v"], info["ids"], info["kinds"], prev)
            assert all(isinstance(v[0], str) and v[5] in info["kinds"] for v in vehicles)
            seen = max(seen, len(vehicles))
        assert len(chunk["frames"]) == meta_chunk["frames"]
    assert seen > 20  # rush-hour demand: the network fills up in 7 minutes


def test_index_html_is_relative_and_static():
    html = site.index_html("https://github.com/Owner/repo", "https://owner.github.io/repo/")
    assert 'href="/static/' not in html and 'src="/static/' not in html and '"/vendor/three/' not in html
    assert 'src="static/js/main.js"' in html and "cdn.jsdelivr.net/npm/three@" in html
    assert "window.TWIN_STATIC" in html and 'content="https://owner.github.io/repo/preview.jpg"' in html


def test_github_urls():
    assert site.github_urls("https://github.com/SungHyunC/team-b-signal-optimization.git") == (
        "https://github.com/SungHyunC/team-b-signal-optimization",
        "https://sunghyunc.github.io/team-b-signal-optimization/",
    )
    assert site.github_urls("git@github.com:Owner/repo.git") == ("https://github.com/Owner/repo", "https://owner.github.io/repo/")
    assert site.github_urls("https://gitlab.com/x/y.git") is None


def test_demo_runs_exist_and_variants_get_their_own_entry():
    for run in site.DEMO_RUNS:
        assert run.scenario in SCENARIOS and run.controller in CONTROLLERS
        assert run.note_ko and (not run.key or run.label_ko), f"{run.id}: the page also switches to Korean"
    assert len({r.id for r in site.DEMO_RUNS}) == len(site.DEMO_RUNS)
    recorded = {r.id: {"frames": 1, "mb": 0.1} for r in site.DEMO_RUNS}
    data = site.demo_meta(site.DEMO_RUNS, recorded)
    names = {c["name"] for c in data["controllers"]}
    assert {r.ui_controller for r in site.DEMO_RUNS} <= names
    assert data["demo"]["default"]["scenario"] == "emergency"
    assert len(data["demo"]["runs"]) == len(site.DEMO_RUNS)


def test_build_never_wipes_a_foreign_directory(tmp_path):
    (tmp_path / "notes.txt").write_text("keep me")
    with pytest.raises(SystemExit):
        site._clean(tmp_path)
    assert (tmp_path / "notes.txt").exists()
