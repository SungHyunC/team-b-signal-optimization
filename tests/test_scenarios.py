"""Scenarios, demand, runtime events, the signal-data API and the impact analysis.

Owner: Scenarios & analysis (Aditya). Three short SUMO runs (closure, emergency vehicles,
API); everything else is pure Python. Runs in well under two minutes.
"""
from __future__ import annotations

import json
import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from teamb.analysis.assumptions import ImpactParams
from teamb.analysis.impact import analyze, main as impact_main, render_markdown, vot_per_vehicle_hour
from teamb.api.signal_data import build_router
from teamb.demand.profiles import combine, dip, integral, multiplier, peak
from teamb.demand.routes import Flow, generate_trips
from teamb.network.topology import load_topology
from teamb.scenarios import REGISTRY, Event, available, get_scenario
from teamb.scenarios import routing
from teamb.sim.env import SimEnv

ALL = sorted(REGISTRY)


@pytest.fixture(scope="module")
def topo():
    return load_topology()


# --- catalog and demand (no SUMO) -------------------------------------------------------
def test_catalog_has_the_required_scenarios_with_bilingual_titles(topo):
    required = {"rush_hour", "emergency", "road_closure", "fake_data_attack", "off_peak", "special_event", "earthquake", "sinkhole_cross"}
    assert required <= set(REGISTRY)
    for d in available():
        assert d["title"] and d["title_ko"] and d["description"] and d["owner"], d["name"]
        assert d["category"] in ("baseline", "demand", "emergency", "disaster", "security")
        assert get_scenario(d["name"]).validate(topo) == [], d["name"]


@pytest.mark.parametrize("name", ALL)
def test_routes_are_deterministic_per_seed(name, tmp_path):
    scenario = get_scenario(name)
    a = scenario.build_routes(tmp_path / "a.rou.xml", seed=3).read_text()
    departs_a = list(scenario.departs)
    b = get_scenario(name).build_routes(tmp_path / "b.rou.xml", seed=3).read_text()
    c = get_scenario(name).build_routes(tmp_path / "c.rou.xml", seed=4).read_text()
    assert a == b and a != c
    assert departs_a == sorted(departs_a) and len(departs_a) > 100


def test_rush_hour_follows_its_time_of_day_profile():
    scenario = get_scenario("rush_hour")
    trips = generate_trips(scenario.flows, seed=1, duration=scenario.duration)
    expected = scenario.expected_vehicles(0, scenario.duration)
    assert abs(len(trips) - expected) < 4 * math.sqrt(expected)  # Poisson: within 4 sigma
    per_10min = [sum(1 for t, *_ in trips if s <= t < s + 600) for s in (300, 2100, 3900)]
    assert per_10min[1] > per_10min[0] and per_10min[1] > per_10min[2]  # ramp up, peak, ramp down
    kinds = {vtype for _, _, vtype, _ in trips}
    assert {"car", "truck", "bus"} <= kinds


def test_profiles_and_flow_streams_are_independent():
    p = peak(start=100, ramp_up=100, hold=100, ramp_down=100, base=0.5)
    assert multiplier(p, 0) == 0.5 and multiplier(p, 150) == 0.75 and multiplier(p, 250) == 1.0 and multiplier(p, 999) == 0.5
    assert integral(p, 0, 400) == pytest.approx(0.5 * 100 + 0.75 * 100 + 1.0 * 100 + 0.75 * 100)
    assert multiplier(combine(p, dip(start=200, end=300, factor=0.5, ramp_in=0, ramp_out=0)), 250) == pytest.approx(0.5)
    # adding a flow does not change the vehicles of the others (one random stream per flow)
    eb = Flow("W0_J1", "J4_E5", 600, name="EB")
    alone = [t for t, vid, _, f in generate_trips([eb], seed=9, duration=3600)]
    extra = Flow("E5_J4", "J1_W0", 300, name="WB")
    together = [t for t, vid, _, f in generate_trips([extra, eb], seed=9, duration=3600) if f.name == "EB"]
    assert alone == together


def test_get_scenario_overrides():
    base = get_scenario("rush_hour")
    doubled = get_scenario("rush_hour", demand_scale=2.0)
    assert doubled.expected_vehicles() == pytest.approx(2 * base.expected_vehicles())
    custom = get_scenario("road_closure", events=[{"time": 100, "kind": "close_road", "params": {"edge": "J2_J3"}}], warmup=0)
    assert isinstance(custom.events[0], Event) and custom.warmup == 0
    with pytest.raises(ValueError):
        get_scenario("rush_hour", warmpu=10)
    with pytest.raises(KeyError):
        get_scenario("no_such_scenario")


def test_static_detours(topo):
    assert routing.detour(topo, "J2_J3") == ["J2_N2", "N2_N3", "N3_J3"]
    assert routing.is_inner_edge(topo, "J2_J3") and routing.is_inner_edge(topo, "N1_N2")
    assert not routing.is_inner_edge(topo, "W0_J1") and not routing.is_inner_edge(topo, "J2_S2")
    route = routing.fastest_route(topo, "W0_J1", "J4_E5", avoid={"J2_J3"})
    assert route and "J2_J3" not in route and route[0] == "W0_J1" and route[-1] == "J4_E5"


def test_stranded_pairs_and_closure_check(topo):
    # cutting both ways into J4 from the west strands the eastbound through trips
    assert routing.stranded_pairs(topo, [("W0_J1", "J4_E5")], {"J3_J4", "N3_N4"}) == [("W0_J1", "J4_E5")]
    assert routing.stranded_pairs(topo, [("W0_J1", "J4_E5")], {"J2_J3"}) == []
    # a closed origin or destination strands its trips, even if it is an inner edge
    assert routing.stranded_pairs(topo, [("N3_J3", "J3_S3"), ("N3_J3", "J3_S3")], {"N3_J3"}) == [("N3_J3", "J3_S3")]
    # all three roads into N2: nobody can reach the exit N2_NN2 any more
    assert routing.stranded_pairs(topo, [("W0_J1", "N2_NN2")], {"J2_N2", "N1_N2", "N3_N2"}) == [("W0_J1", "N2_NN2")]
    assert routing.stranded_pairs(topo, [("NOPE", "J4_E5")], set()) == []  # unknown edges are validate()'s job
    pairs = {("W0_J1", "J4_E5"): "EB through"}
    assert routing.closure_error(topo, ["J2_J3"], (), list(pairs), pairs) is None
    assert "entry/exit" in routing.closure_error(topo, ["W0_J1"], (), list(pairs), pairs)
    assert "unknown edge" in routing.closure_error(topo, ["NOPE"], (), list(pairs), pairs)
    msg = routing.closure_error(topo, ["N3_N4"], {"J3_J4"}, list(pairs), pairs)
    assert msg and "EB through" in msg and "no route" in msg
    # pairs that earlier closures already cut off do not block an unrelated closure
    assert routing.closure_error(topo, ["J1_J2"], {"J3_J4", "N3_N4"}, list(pairs), pairs) is None


def test_scenario_closure_check_and_validate_replay_events(topo):
    special = get_scenario("special_event")
    assert "Stadium" in special.closure_error(topo, ["N3_J3"])  # the stadium garage exit is a flow origin
    rush = get_scenario("rush_hour")
    assert rush.closure_error(topo, ["J2_N2", "N2_J2"]) is None  # the sinkhole closure is fine
    assert rush.closure_error(topo, ["N3_N2"], {"J2_N2", "N1_N2"})  # ... the third road into N2 is not
    events = [
        {"time": 50, "kind": "close_road", "params": {"edge": "J3_J4", "both_directions": True}},
        {"time": 51, "kind": "close_road", "params": {"edge": "N3_N4"}},  # cuts J4 off from the west
        {"time": 60, "kind": "reopen_road", "params": {"edge": "J3_J4", "both_directions": True}},
        {"time": 61, "kind": "close_road", "params": {"edge": "N3_N4"}},  # fine once the bridge is open again
        {"time": 70, "kind": "start_attack", "params": {"junction": "J2", "approach": "X"}},
        {"time": 71, "kind": "start_attack", "params": {"junction": "J2", "approach": "N", "n": 0}},
        {"time": 72, "kind": "start_attack", "params": {"junction": "J2", "approach": "N", "n": "many"}},
        {"time": 80, "kind": "close_road", "params": {"edge": "J2-J3"}},
    ]
    problems = get_scenario("rush_hour", events=events).validate(topo)
    assert len(problems) == 5, problems
    assert problems[0].startswith("event at 51:") and "no route" in problems[0]
    assert "no approach X" in problems[1] and "between 1 and 500" in problems[2] and "integer" in problems[3]
    assert "unknown edge J2-J3" in problems[4]
    ev = get_scenario("rush_hour", events=[
        {"time": 50, "kind": "close_road", "params": {"edge": "J3_J4"}},
        {"time": 50, "kind": "close_road", "params": {"edge": "N3_N4"}},
        {"time": 60, "kind": "dispatch_ev", "params": {"origin": "W0_J1", "destination": "J4_E5"}},
    ]).validate(topo)
    assert len(ev) == 1 and "event at 50" in ev[0]  # the second closure is refused, so the EV still has a route


# --- road closure (SUMO) --------------------------------------------------------------------
CLOSE_AT, REOPEN_AT, CLOSURE_END = 150, 420, 600


@pytest.fixture(scope="module")
def closure_run(tmp_path_factory):
    """road_closure with the closure moved early; observes every step."""
    events = [
        {"time": 100, "kind": "close_road", "params": {"edge": "NOT_AN_EDGE"}},  # must not stop the run
        {"time": CLOSE_AT, "kind": "close_road", "params": {"edge": "J2_J3", "cause": "flood"}},
        {"time": CLOSE_AT + 1, "kind": "close_road", "params": {"edge": "J2_J3", "cause": "flood"}},  # idempotent
        {"time": REOPEN_AT, "kind": "reopen_road", "params": {"edge": "J2_J3"}},
        {"time": REOPEN_AT + 1, "kind": "reopen_road", "params": {"edge": "J2_J3"}},  # idempotent
    ]
    env = SimEnv("road_closure", "fixed_time", seed=5, end_time=CLOSURE_END, output_dir=tmp_path_factory.mktemp("closure"),
                 scenario_params={"warmup": 0, "events": events})
    env.start()
    obs = {"allowed": set(), "violations": set(), "departed_through": [], "departed_during": 0, "detour_users": set(),
           "after_reopen_on_edge": set(), "ev": None, "ev_route": None, "lanes_before": env.conn.lane.getAllowed("J2_J3_0")}
    v = env.conn.vehicle
    while env.t < CLOSURE_END:
        env.step()
        t = env.t
        on_edge = set(env.conn.edge.getLastStepVehicleIDs("J2_J3"))
        if t == CLOSE_AT:
            blocked = {x for x in v.getIDList() if "J2_J3" in v.getRoute(x)[v.getRouteIndex(x) + 1 :]}
            obs["allowed"] = on_edge | blocked  # on the edge or already committed to it at the closure
            obs["on_edge_at_closure"] = on_edge
        if CLOSE_AT < t < REOPEN_AT:
            obs["violations"] |= on_edge - obs["allowed"]
            for vid in env.conn.simulation.getDepartedIDList():
                obs["departed_during"] += 1
                if "J2_J3" in v.getRoute(vid):
                    obs["departed_through"].append(vid)
            for e in ("J2_N2", "J1_N1", "N2_N3", "N3_N4"):
                obs["detour_users"] |= set(env.conn.edge.getLastStepVehicleIDs(e))
        if t == CLOSE_AT + 30:  # an ambulance dispatched during the closure must route around it
            obs["ev"] = env.handle_command({"type": "dispatch_ev", "origin": "W0_J1", "destination": "J4_E5", "kind": "ambulance"})["result"]
            obs["ev_route"] = env.runtime.evs[obs["ev"]]["route"]
        if t == REOPEN_AT + 5:
            obs["lanes_after"] = env.conn.lane.getAllowed("J2_J3_0")
            obs["closed_after_reopen"] = env.runtime.closed_edges()
        if t > REOPEN_AT + 10:
            obs["after_reopen_on_edge"] |= on_edge
    obs["left_edge"] = not (obs["on_edge_at_closure"] & set(v.getIDList()))
    obs["teleports"] = env.runtime.teleports
    obs["runtime"] = env.runtime
    obs["events"] = list(env.events)
    obs["in_network_at_end"] = len(v.getIDList())
    env.close()
    return obs


def test_closure_reroutes_everyone_and_reopening_restores_routing(closure_run):
    o = closure_run
    types = [e["type"] for e in o["events"]]
    assert types.count("road_closed") == 1 and types.count("road_reopened") == 1  # idempotent
    assert "event_failed" in types  # the bad edge was logged, the run went on
    assert o["violations"] == set()  # nobody drove onto the closed edge
    assert o["departed_during"] > 50 and o["departed_through"] == []  # trips inserted later avoid it
    assert len(o["detour_users"]) > 20  # traffic really uses the back street
    assert o["left_edge"]  # vehicles caught on the closed edge drove off it
    assert "J2_J3" not in o["ev_route"] and o["runtime"].evs[o["ev"]]["status"] == "arrived"
    assert o["lanes_after"] == o["lanes_before"] and o["closed_after_reopen"] == []
    assert len(o["after_reopen_on_edge"]) > 20  # the arterial is used again
    assert o["teleports"] == 0 and o["in_network_at_end"] < 400  # no deadlock
    closed = next(e for e in o["events"] if e["type"] == "road_closed")
    assert closed["rerouted"] > 0


def test_closure_rejects_bad_requests(closure_run):
    runtime = closure_run["runtime"]
    with pytest.raises(ValueError):
        runtime.close_road("W0_J1")  # entry edge: trips would have no way in
    with pytest.raises(ValueError):
        runtime.close_road("NOPE")
    with pytest.raises(ValueError):
        runtime.dispatch_ev("W0_J1", "J4_E5", kind="helicopter")


@pytest.fixture(scope="module")
def stranding_run(tmp_path_factory):
    """Closures that would strand trips are refused and the run goes on (SUMO would quit)."""
    events = [
        {"time": 50, "kind": "close_road", "params": {"edge": "J3_J4"}},
        {"time": 51, "kind": "close_road", "params": {"edge": "N3_N4"}},  # J4 cut off from the west
    ]
    env = SimEnv("rush_hour", "fixed_time", seed=1, end_time=200, output_dir=tmp_path_factory.mktemp("stranding"),
                 scenario_params={"warmup": 0, "events": events})
    env.start()
    out = {}
    while env.t < 200:
        env.step()
        if env.t == 60:
            out["first"] = env.runtime.close_road("J2_N2")
            out["second"] = env.runtime.close_road("N1_N2")
            with pytest.raises(ValueError, match="no route") as refused:
                env.runtime.close_road("N3_N2")  # the last road into N2: trips to N2_NN2 would be stranded
            out["refused"] = str(refused.value)
    out["t"], out["closed"], out["events"] = env.t, sorted(env.runtime.closed), list(env.events)
    out["report"] = env.runtime.report()
    env.close()

    special = SimEnv("special_event", "fixed_time", seed=1, end_time=20, output_dir=tmp_path_factory.mktemp("stadium"),
                     scenario_params={"warmup": 0})
    special.start()
    while special.t < 10:
        special.step()
    with pytest.raises(ValueError, match="Stadium") as stadium:
        special.handle_command({"type": "close_road", "edge": "N3_J3"})  # the garage exit is a flow origin
    out["stadium"] = str(stadium.value)
    while special.t < 20:
        special.step()
    out["stadium_closed"] = dict(special.runtime.closed)
    special.close()
    return out


def test_closures_that_strand_trips_are_refused(stranding_run):
    o = stranding_run
    assert o["t"] == 200  # SUMO did not quit
    assert o["first"]["closed"] and o["second"]["closed"] and "N2_NN2" in o["refused"]
    assert o["closed"] == ["J2_N2", "J3_J4", "N1_N2"]
    failed = [e for e in o["events"] if e["type"] == "event_failed"]
    assert len(failed) == 1 and failed[0]["params"]["edge"] == "N3_N4" and "no route" in failed[0]["error"]
    assert o["report"]["failed_events"] == 1
    assert o["stadium_closed"] == {}


# --- emergency vehicles from every side (SUMO) ----------------------------------------------------
EVS = [
    ("W0_J1", "J4_E5", "ambulance"),  # eastbound arterial
    ("E5_J4", "J1_W0", "firetruck"),  # westbound arterial
    ("NN2_N2", "J2_S2", "ambulance"),  # southbound cross street
    ("S3_J3", "N3_NN3", "firetruck"),  # northbound cross street
    ("S1_J1", "J4_E5", "firetruck"),  # north, right turn onto the arterial
    ("NN4_N4", "J1_W0", "ambulance"),  # south, right turn onto the arterial
    ("E5_J4", "J2_S2", "ambulance"),  # westbound, left turn across eastbound traffic
    ("S4_J4", "J1_W0", "firetruck"),  # north, left turn onto the arterial
]


@pytest.fixture(scope="module")
def ev_run(tmp_path_factory):
    events = [{"time": 20 + 60 * i, "kind": "dispatch_ev", "params": {"origin": o, "destination": d, "kind": k}} for i, (o, d, k) in enumerate(EVS)]
    events += [
        {"time": 30, "kind": "start_attack", "params": {"junction": "J2", "approach": "N", "n": 99}},
        {"time": 31, "kind": "start_attack", "params": {"junction": "J2", "approach": "N", "n": 99}},  # idempotent
        {"time": 200, "kind": "stop_attack", "params": {}},
        {"time": 201, "kind": "stop_attack", "params": {}},  # idempotent
    ]
    env = SimEnv("emergency", "fixed_time", seed=2, end_time=760, output_dir=tmp_path_factory.mktemp("evs"),
                 scenario_params={"warmup": 0, "events": events, "demand_scale": 0.6})
    env.start()
    fake_during = None
    while env.t < 760:
        env.step()
        if env.t == 100:
            fake_during = dict(env.sensors.fake), dict(env.runtime.attack)
    result = {"evs": env.runtime.evs, "preemptions": list(env.preemptions), "events": list(env.events),
              "fake_during": fake_during, "fake_after": dict(env.sensors.fake), "attack_after": env.runtime.attack}
    env.close()
    return result


def test_emergency_vehicles_from_every_side_arrive_with_preemption(ev_run):
    evs = ev_run["evs"]
    assert len(evs) == len(EVS)
    assert {e["kind"] for e in evs.values()} == {"ambulance", "firetruck"}
    preempted = {p["vehicle"] for p in ev_run["preemptions"]}
    for vid, ev in evs.items():
        assert ev["status"] == "arrived", (vid, ev["origin"], ev["destination"])
        assert ev["travel_time_s"] and ev["travel_time_s"] < 400
        assert vid in preempted, f"{vid} ({ev['origin']} -> {ev['destination']}) never got a preemption"
    eb = next(v for v, e in evs.items() if (e["origin"], e["destination"]) == ("W0_J1", "J4_E5"))
    assert {p["junction"] for p in ev_run["preemptions"] if p["vehicle"] == eb} == {"J1", "J2", "J3", "J4"}
    arrived = [e for e in ev_run["events"] if e["type"] == "ev_arrived"]
    assert len(arrived) == len(EVS)


def test_fake_data_attack_start_stop_is_idempotent(ev_run):
    fake, attack = ev_run["fake_during"]
    assert fake == {("J2", "N"): 99} and attack["junction"] == "J2"
    assert ev_run["fake_after"] == {} and ev_run["attack_after"] is None
    types = [e["type"] for e in ev_run["events"]]
    assert types.count("attack_started") == 1 and types.count("attack_stopped") == 1


# --- signal-data API (SUMO) ----------------------------------------------------------------------------
def test_signal_data_api(tmp_path):
    holder = {"env": None}
    app = FastAPI()
    app.include_router(build_router(lambda: holder["env"]))
    client = TestClient(app)

    assert client.get("/api/v1/spat").status_code == 503  # nothing running
    assert client.get("/api/v1/advisories").status_code == 503
    net = client.get("/api/v1/network")
    assert net.status_code == 200 and [j["id"] for j in net.json()["junctions"]] == ["J1", "J2", "J3", "J4"]
    j1 = net.json()["junctions"][0]
    assert set(j1["approaches"]) == {"W", "E", "N", "S"}
    turns = {m["turn"] for m in j1["approaches"]["W"]["movements"]}
    assert turns == {"through", "left", "right"}

    env = SimEnv("road_closure", "fixed_time", seed=3, end_time=500, output_dir=tmp_path,
                 scenario_params={"warmup": 0, "events": [], "demand_scale": 0.5})
    env.start()
    holder["env"] = env
    while env.t < 40:
        env.step()

    index = client.get("/api/v1")
    assert index.status_code == 200 and index.json()["running"] is True
    spat = client.get("/api/v1/spat")
    assert spat.status_code == 200 and spat.headers["cache-control"] == "no-store"
    body = spat.json()
    assert body["api_version"] == "1.0" and body["t"] == env.t and body["generated_at"].endswith("Z")
    assert body["units"]["distance"] == "m" and set(body["junctions"]) == {"J1", "J2", "J3", "J4"}
    for j, s in body["junctions"].items():
        assert s["signal"] == env.supervisor.junctions[j].signal
        assert set(s["approaches"]) == {"W", "E", "N", "S"}
        for a in s["approaches"].values():
            assert a["state"] in ("green", "yellow", "red") and a["next_change_in_s"]["min"] >= 0
    assert any(s["prediction"] in ("timing_plan", "exact") for s in body["junctions"].values())
    one = client.get("/api/v1/spat/j2")
    assert one.status_code == 200 and one.json()["junction"] == "J2"
    missing = client.get("/api/v1/spat/J9")
    assert missing.status_code == 404 and "J9" in missing.json()["detail"]
    quiet = client.get("/api/v1/advisories").json()
    assert quiet["counts"] == {"closures": 0, "preemptions": 0, "emergency_vehicles": 0}

    env.handle_command({"type": "close_road", "edge": "J2_J3", "cause": "flood"})
    vid = env.handle_command({"type": "dispatch_ev", "origin": "W0_J1", "destination": "J4_E5", "kind": "ambulance"})["result"]
    seen_warning = seen_preemption = False
    while env.t < 400 and not (seen_warning and seen_preemption):
        env.step()
        adv = client.get("/api/v1/advisories").json()
        seen_warning |= any(w["type"] == "emergency_vehicle_approaching" and w["vehicle"] == vid for w in adv["warnings"])
        seen_preemption |= any(p["vehicle"] == vid for p in adv["preemptions"])
    assert seen_warning and seen_preemption
    closure = adv["closures"][0]
    assert closure["edge"] == "J2_J3" and closure["detour"] == ["J2_N2", "N2_N3", "N3_J3"]
    assert any(w["type"] == "road_closed" for w in adv["warnings"])

    env.close()
    assert client.get("/api/v1/spat").status_code == 503  # finished


# --- impact & cost-benefit (no SUMO) -------------------------------------------------------------------
def _summary(**kw):
    base = dict(scenario="rush_hour", controller="fixed_time", coverage=1.0, sampling="uniform", ev_preemption=True,
                sim_time_s=4500.0, completed=3600, unfinished=0, unfinished_pct=0.0, mean_delay_s=60.0, stops_per_veh=1.5,
                ev_mean_travel_time_s=None)
    return {**base, **kw}


def test_impact_math_on_toy_summaries():
    runs = []
    for seed in (1, 2, 3):
        runs.append(_summary(seed=seed, mean_delay_s=60.0 + seed))
        runs.append(_summary(seed=seed, controller="max_pressure", mean_delay_s=50.0 + seed, stops_per_veh=1.2))
        runs.append(_summary(seed=seed, controller="stranding", mean_delay_s=30.0, completed=3200, unfinished=400, unfinished_pct=10.0))
    p = ImpactParams()
    result = analyze(runs, params=p)
    mp = next(r for r in result["rows"] if r["controller"] == "max_pressure")
    s = {k: v["mean"] for k, v in mp["stats"].items()}
    # 10 s less delay for 3,600 trips in a 1-hour window = 10 vehicle-hours saved per hour
    assert s["delay_saved_veh_h_per_h"] == pytest.approx(10.0)
    assert s["time_value_usd_per_h"] == pytest.approx(10.0 * vot_per_vehicle_hour(p))
    fuel = 10.0 * p.idle_fuel_gal_per_h + 0.3 * 3600 * p.fuel_per_stop_gal
    assert s["fuel_saved_gal_per_h"] == pytest.approx(fuel)
    assert s["co2_avoided_kg_per_h"] == pytest.approx(fuel * p.co2_kg_per_gal)
    assert mp["stats"]["delay_saved_veh_h_per_h"]["ci95"] == pytest.approx(0.0, abs=1e-9)
    annual = {a["controller"]: a for a in result["annual"]}
    hours = p.annual_hours["rush_hour"]
    assert annual["max_pressure"]["annual_benefit_usd"] == pytest.approx(s["total_value_usd_per_h"] * hours)
    capex = 4 * p.adaptive_capex_per_intersection_usd
    assert annual["max_pressure"]["capex_usd"] == capex and annual["max_pressure"]["benefit_cost_ratio"] > 1
    # stranding vehicles is never rewarded (PERF-01)
    stranding = next(r for r in result["rows"] if r["controller"] == "stranding")
    assert not stranding["claimed"] and any("PERF-01" in f for f in stranding["flags"])
    assert annual["stranding"]["annual_benefit_usd"] == 0
    text = render_markdown(result)
    assert "| rush_hour | max_pressure | 3 |" in text and "## Assumptions" in text


def test_impact_preemption_effect_and_overrides():
    runs = []
    for seed in (1, 2):
        runs.append(_summary(scenario="emergency", seed=seed, ev_mean_travel_time_s=120.0, mean_delay_s=61.0))
        runs.append(_summary(scenario="emergency", seed=seed, ev_preemption=False, ev_mean_travel_time_s=160.0, mean_delay_s=60.0))
    result = analyze(runs, params={"ev_trips_per_year": 3600})
    eff = result["preemption"][0]
    assert eff["ev_time_saved_s"]["mean"] == pytest.approx(40.0)
    assert eff["others_extra_delay_s"]["mean"] == pytest.approx(1.0)
    assert eff["ev_hours_saved_per_year"] == pytest.approx(40.0)
    with pytest.raises(KeyError):
        ImpactParams.with_overrides({"not_a_parameter": 1})


def test_impact_cli_reads_an_experiment_folder(tmp_path):
    exp = tmp_path / "exp"
    for controller in ("fixed_time", "actuated"):
        for seed in (1, 2):
            run = exp / "runs" / f"rush_hour__{controller}__s{seed}"
            run.mkdir(parents=True)
            delay = 60.0 if controller == "fixed_time" else 45.0
            (run / "summary.json").write_text(json.dumps(_summary(controller=controller, seed=seed, mean_delay_s=delay + seed)))
            (run / "run_spec.json").write_text(json.dumps({"variant": controller, "scenario_params": {}}))
            (run / "manifest.json").write_text(json.dumps({"config": {"warmup": 900}}))
    assert impact_main([str(exp)]) == 0
    md = (exp / "impact.md").read_text()
    assert "actuated" in md and "B/C" in md
    data = json.loads((exp / "impact.json").read_text())
    assert data["rows"][0]["stats"]["delta_mean_delay_s"]["mean"] == pytest.approx(-15.0)


# --- runtime bookkeeping with a fake TraCI connection (no SUMO) ------------------------------
class _FakeVehicles:
    def __init__(self, routes):
        self.routes = {vid: list(r) for vid, r in routes.items()}
        self.calls = 0

    def getIDList(self):
        return list(self.routes)

    def getRoute(self, vid):
        return tuple(self.routes[vid])

    def getRouteIndex(self, vid):
        return 0

    def rerouteTraveltime(self, vid, current=False):
        self.calls += 1  # the fastest route is the one it already has: nothing changes


class _FakeEdges:
    def adaptTraveltime(self, eid, value):
        pass


class _FakeEnv:
    def __init__(self, topo, routes):
        from types import SimpleNamespace

        self.topology, self.t, self.events = topo, 1600.0, []
        self.conn = SimpleNamespace(vehicle=_FakeVehicles(routes), edge=_FakeEdges())
        self.sensors = SimpleNamespace(is_probe=lambda vid: True)

    def log_event(self, event_type, /, **data):
        self.events.append({"t": self.t, "type": event_type, **data})


def test_rerouted_counts_vehicles_whose_route_changed_not_calls(topo):
    from teamb.scenarios.events import ScenarioRuntime

    env = _FakeEnv(topo, {"p1": ["J1_J2", "J2_N2", "N2_N3", "N3_J3", "J3_J4"]})
    runtime = ScenarioRuntime(env, get_scenario("road_closure"))
    runtime.closed = {"J2_J3": {"edge": "J2_J3", "cause": "flood", "since": 1500.0}}
    runtime._refresh_detours()
    for _ in range(3):  # three navigation updates, the route never changes
        runtime._navigation_reroute()
    report = runtime.report()
    assert env.conn.vehicle.calls == 3 and report["reroute_calls"] == 3
    assert report["rerouted"] == 0
    env.conn.vehicle.rerouteTraveltime = lambda vid, current=False: env.conn.vehicle.routes.__setitem__(vid, ["J1_J2", "J2_N2", "N2_N3", "N3_J3", "J3_J4", "J4_E5"])
    runtime._navigation_reroute()
    runtime._navigation_reroute()
    assert runtime.report()["rerouted"] == 1  # one vehicle, however often it is asked


def test_failed_scheduled_events_are_reported_with_details(topo):
    from teamb.scenarios.events import ScenarioRuntime

    env = _FakeEnv(topo, {})
    scenario = get_scenario("rush_hour", events=[{"time": 10, "kind": "close_road", "params": {"edge": "J2-J3"}},
                                                 {"time": 20, "kind": "no_such_kind", "params": {}}])
    runtime = ScenarioRuntime(env, scenario)
    runtime._dispatch_pending(25.0)
    report = runtime.report()
    assert report["failed_events"] == 2
    first, second = report["failed_event_details"]
    assert first["kind"] == "close_road" and first["params"] == {"edge": "J2-J3"} and "unknown edge" in first["error"]
    assert second["kind"] == "no_such_kind" and second["scheduled_at"] == 20
    assert [e["type"] for e in env.events] == ["event_failed", "event_failed"]


def test_runtime_reuses_step_data_instead_of_traci_round_trips(tmp_path, monkeypatch):
    """EV tracking, departures, teleports and live travel times come from data the env, the
    sensor feed and subscriptions already have (runtime-perf-3, ext-119/120/122)."""
    import sys
    from collections import Counter

    import traci.connection

    calls: Counter = Counter()
    original = traci.connection.Connection._sendCmd

    def counting(self, *args, **kwargs):
        frame, getter = sys._getframe(1), None
        while frame is not None:
            name = frame.f_code.co_filename
            if "traci" in name and getter is None and frame.f_code.co_name.startswith("get"):
                getter = frame.f_code.co_name
            if name.endswith("scenarios/events.py"):
                calls[getter] += 1
                break
            frame = frame.f_back
        return original(self, *args, **kwargs)

    events = [
        {"time": 5, "kind": "dispatch_ev", "params": {"origin": "W0_J1", "destination": "J4_E5", "kind": "ambulance"}},
        {"time": 10, "kind": "close_road", "params": {"edge": "J2_J3"}},
    ]
    env = SimEnv("emergency", "fixed_time", seed=1, end_time=120, output_dir=tmp_path,
                 scenario_params={"warmup": 0, "events": events, "demand_scale": 0.5})
    env.start()
    monkeypatch.setattr(traci.connection.Connection, "_sendCmd", counting)
    lives = []
    while env.t < 120:
        env.step()
        lives += [ev["live"] for ev in env.runtime.active_evs() if ev["live"]]
    monkeypatch.undo()
    summary = env.close()
    for getter in ("getDepartedIDList", "getArrivedIDList", "getStartingTeleportNumber", "getRoadID", "getPosition",
                   "getSpeed", "getAngle", "getTraveltime"):
        assert calls[getter] == 0, (getter, calls)
    assert calls["getNextTLS"] <= 2, calls  # only right after the EV was re-routed around the closure
    assert lives and any(live["next_junction"] for live in lives)
    assert env.runtime.teleports == summary.get("teleports", env.runtime.teleports)


def _departures_after_reopening(tmp_path) -> list:
    """Trips that departed within 300 s after a reopening on a route slower (free flow) than
    the fastest open one. The closure makes the detour (J3 -> N3 -> N4 -> J4) jam."""
    events = [
        {"time": 300, "kind": "close_road", "params": {"edge": "J3_J4", "cause": "earthquake", "both_directions": True}},
        {"time": 1000, "kind": "reopen_road", "params": {"edge": "J3_J4", "both_directions": True}},
    ]
    env = SimEnv("earthquake", "fixed_time", seed=1, end_time=1300, output_dir=tmp_path,
                 scenario_params={"warmup": 0, "events": events, "demand_scale": 1.6})
    env.start()
    worse, topo, v = [], env.topology, env.conn.vehicle
    while env.t < 1300:
        env.step()
        if env.t > 1000:
            for vid in env.sensors.step_departed:
                route = v.getRoute(vid)
                best = routing.fastest_route(topo, route[0], route[-1], avoid=env.runtime.closed)
                cost = sum(routing.free_flow_time(topo, e) for e in route)
                if cost > sum(routing.free_flow_time(topo, e) for e in best) + 1.0:
                    worse.append((env.t, vid, route))
    env.close()
    return worse


def test_trips_departing_after_a_reopening_take_free_flow_routes(tmp_path):
    """SUMO's insertion routing still remembers the jammed detour after a reopening; the
    runtime routes those departures on the static weights (scenarios-sensors-5)."""
    assert _departures_after_reopening(tmp_path) == []


def test_corridor_demand_for_a_subset_of_junctions_uses_their_own_edges(topo):
    from teamb.demand.corridor import CorridorDemand

    edges = {e.getID() for e in topo.net.getEdges()}
    full = CorridorDemand().flows()
    subset = CorridorDemand(junctions=("J2", "J4")).flows()
    for f in subset:
        assert f.origin in edges and f.destination in edges, f
    by_name = {f.name: f for f in subset}
    assert (by_name["SB through at J2"].origin, by_name["SB through at J2"].destination) == ("NN2_N2", "J2_S2")
    assert (by_name["NB right at J4"].origin, by_name["NB right at J4"].destination) == ("S4_J4", "J4_E5")
    assert {f.name for f in subset} <= {f.name for f in full} and not any("J1" in f.name or "J3" in f.name for f in subset)
    with pytest.raises(ValueError):
        CorridorDemand(junctions=("J9",)).flows()
