"""Tests for the AI & security controllers (Yunseong): actuated, max-pressure, AI recommender, RL.

Unit tests feed synthetic observations (no SUMO). A few short SUMO runs (≤ 300 s) check
the controllers inside SimEnv, the fake-data attack, and both search modes of the AI
recommender. The whole file takes about a minute.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict

import pytest

from teamb.controllers import REGISTRY, available, make_controller
from teamb.controllers.demand_model import ProbeDemandModel, od_flows
from teamb.controllers.fixed_time import TimingPlan
from teamb.controllers.optimizer import SearchJob, SearchSpec, load_cache, save_cache, webster_plan
from teamb.controllers.rl import MODEL_PATH, N_STATES, QTable, encode_state
from teamb.network.topology import load_topology

MINE = ("actuated", "max_pressure", "max_pressure_probe", "ai_recommender", "rl")


@pytest.fixture(scope="module")
def topo():
    return load_topology()


def make_obs(topo, t, *, count=None, queue=None, gap=None, probe_n=None, untrusted=(), exit_count=None, coverage=1.0):
    """A synthetic observation in the sensors' contract. Keys are (junction, side)."""
    count, queue, gap = count or {}, queue or {}, gap or {}
    probe_n, exit_count = probe_n or {}, exit_count or {}
    junctions = {}
    for j in topo.tls_ids:
        approaches = {}
        for side in topo.approach_lanes[j]:
            k = (j, side)
            c = count.get(k, queue.get(k, 0))
            n = probe_n.get(k, c * coverage)
            approaches[side] = {
                "detector": {"queue": queue.get(k, 0), "count": c, "occupancy": 5.0, "speed": 5.0,
                             "flow_vph": 600.0, "gap_s": gap.get(k, 10.0)},
                "probe": {"queue_est": queue.get(k, 0) if k not in probe_n else n / coverage, "n": n,
                          "halted": n, "speed": 2.0, "flow_est_vph": 600.0, "trusted": k not in untrusted},
            }
        exits = {}
        for side, edge in topo.exit_edges[j].items():
            has = topo.downstream_junction(edge) is not None
            c = exit_count.get((j, side), 0)
            exits[side] = {"edge": edge, "detector": {"queue": c, "count": c} if has else None}
        junctions[j] = {"approaches": approaches, "exits": exits}
    return {"t": t, "coverage": coverage, "sampling": "uniform", "junctions": junctions, "alerts": []}


def make_state(topo, t, axis="EW", green_s=20.0):
    return {"t": t, "junctions": {j: {"signal": f"{axis}_G", "phase": axis, "green": True, "time_in_state": green_s,
                                      "can_switch": green_s >= 8} for j in topo.tls_ids}}


def ready(name, topo, **params):
    ctl = make_controller(name, **params)
    ctl.reset({}, 1, topo)
    return ctl


# --- registry -------------------------------------------------------------------------
def test_registry_lists_every_controller_with_metadata():
    names = {d["name"] for d in available()}  # also proves the constructors are cheap
    assert {"fixed_time", "coordinated", *MINE} <= names
    for name in MINE:
        cls = REGISTRY[name]
        assert cls.label and cls.description and "Yunseong" in cls.owner
        assert cls.observation_source in ("detector", "probe", "fused", "oracle")


# --- actuated ---------------------------------------------------------------------------
def test_actuated_extends_gaps_out_rests_and_maxes_out(topo):
    ctl = ready("actuated", topo)
    ctl.observe(make_obs(topo, 100, queue={("J1", "N"): 3}, gap={("J1", "W"): 1.0}))
    assert ctl.propose_action(make_state(topo, 100)) == {}, "cars still arriving: extend"
    ctl.observe(make_obs(topo, 101, queue={("J1", "N"): 3}, gap={("J1", "W"): 5.0, ("J1", "E"): 4.0}))
    assert ctl.propose_action(make_state(topo, 101)) == {"J1": "NS"}, "gap-out with cars waiting"
    ctl.observe(make_obs(topo, 102))
    assert ctl.propose_action(make_state(topo, 102)) == {}, "nobody waiting: rest in green"
    ctl.observe(make_obs(topo, 103, queue={("J2", "S"): 1}, gap={("J2", "W"): 0.5, ("J2", "E"): 0.5}))
    assert ctl.propose_action(make_state(topo, 103, green_s=51)) == {"J2": "NS"}, "max-out at 50 s"
    ctl.observe(make_obs(topo, 104, queue={("J3", "N"): 4}, gap={("J3", "W"): 9.0}))
    assert ctl.propose_action(make_state(topo, 104, green_s=9)) == {}, "never before min green"


# --- max-pressure -------------------------------------------------------------------------
def test_max_pressure_follows_pressure_with_margin(topo):
    ctl = ready("max_pressure", topo)
    ctl.observe(make_obs(topo, 100, count={("J2", "N"): 6, ("J2", "W"): 2}))
    assert ctl.pressure("J2", "NS") == 6 and ctl.pressure("J2", "EW") == 2
    assert ctl.propose_action(make_state(topo, 100)) == {"J2": "NS"}
    ctl.observe(make_obs(topo, 105, count={("J2", "N"): 3, ("J2", "W"): 2}))
    assert ctl.propose_action(make_state(topo, 105)) == {}, "inside the margin: keep"
    # J1 eastbound has 9 cars but its exit (J2's west approach) is full: pressure 9 - 8 = 1
    ctl.observe(make_obs(topo, 110, count={("J1", "N"): 5, ("J1", "W"): 9}, exit_count={("J1", "E"): 8}))
    assert ctl.pressure("J1", "EW") == 1
    assert ctl.propose_action(make_state(topo, 110)) == {"J1": "NS"}
    ctl.observe(make_obs(topo, 112, count={("J1", "N"): 9}))
    assert ctl.propose_action(make_state(topo, 112)) == {}, "decides only every 5 s"


def test_fake_probe_queue_fools_blind_controller_not_defended_one(topo):
    attack = dict(count={("J2", "W"): 8, ("J2", "E"): 4}, probe_n={("J2", "N"): 99 + 1}, untrusted=[("J2", "N")])
    blind = ready("max_pressure_probe", topo)
    blind.observe(make_obs(topo, 100, **attack))
    assert blind.propose_action(make_state(topo, 100)).get("J2") == "NS"
    defended = ready("max_pressure", topo, source="probe", defense=True)
    defended.observe(make_obs(topo, 100, **attack))
    assert "J2" not in defended.propose_action(make_state(topo, 100))
    assert defended.guard.rejected["untrusted_probe"] >= 1
    # even if the cross-check missed it, 100 cars cannot fit on a 232 m one-lane street
    sneaky = ready("max_pressure", topo, source="probe", defense=True)
    sneaky.observe(make_obs(topo, 100, **{**attack, "untrusted": []}))
    assert "J2" not in sneaky.propose_action(make_state(topo, 100))
    assert sneaky.guard.rejected["implausible_probe"] >= 1


def test_stale_or_replayed_observations_fall_back_to_fixed_time(topo):
    for name in ("actuated", "max_pressure", "rl" if MODEL_PATH.exists() else "actuated"):
        ctl = ready(name, topo)
        plan = TimingPlan(splits={j: 0.5 for j in topo.tls_ids})
        ctl.observe(make_obs(topo, 60))
        assert ctl.propose_action(make_state(topo, 100)) == {j: plan.axis_at(j, 100) for j in topo.tls_ids}
        ctl.observe(make_obs(topo, 200))
        ctl.propose_action(make_state(topo, 200))
        ctl.observe(make_obs(topo, 198))  # fresh enough, but older than the last accepted one: replay
        assert ctl.propose_action(make_state(topo, 205)) == {j: plan.axis_at(j, 205) for j in topo.tls_ids}
        assert ctl.guard.rejected["stale"] == 1 and ctl.guard.rejected["replayed"] == 1


# --- timing plans (fixed-time / coordinated / AI plans) ------------------------------------
def test_timing_plan_greens_always_fill_exactly_one_cycle():
    from teamb import config

    for cycle in range(60, 151, 5):
        for split in (0.15, 0.25, 0.5, 0.84, 0.85, 0.95):
            plan = TimingPlan(cycle=cycle, splits={"J1": split})
            ew, ns = plan.greens("J1")
            assert ew >= config.MIN_GREEN_S and ns >= config.MIN_GREEN_S, (cycle, split, ew, ns)
            assert ew + ns + 2 * config.LOST_TIME_PER_SWITCH_S == pytest.approx(cycle, abs=1e-9), (cycle, split)
    with pytest.raises(ValueError, match="cycle"):
        TimingPlan(cycle=20)


def _ew_request_starts(plan, junction, t_end, dt=0.5):
    """Times at which the plan starts asking for EW (= NS yellow begins)."""
    starts, prev = [], None
    for i in range(int(t_end / dt)):
        t = i * dt
        axis = plan.axis_at(junction, t)
        if axis == "EW" and prev == "NS":
            starts.append(t)
        prev = axis
    return starts


def test_timing_plan_greens_start_at_the_offset_without_drift():
    from teamb import config

    lost = config.LOST_TIME_PER_SWITCH_S
    # J2's 0.85 share at a 60 s cycle needs the NS minimum green: it used to stretch J2 to 60.5 s
    plan = TimingPlan(cycle=60, splits={"J1": 0.5, "J2": 0.85}, offsets={"J1": 0.0, "J2": 24.0})
    for j in ("J1", "J2"):
        starts = _ew_request_starts(plan, j, 3600)
        assert len(starts) >= 55
        assert all(b - a == pytest.approx(60.0) for a, b in zip(starts, starts[1:])), j
        # EW green starts `lost` seconds after the request, exactly at the offset (mod cycle)
        assert all((t + lost - plan.offsets[j]) % 60 == pytest.approx(0.0, abs=1e-6) or
                   (t + lost - plan.offsets[j]) % 60 == pytest.approx(60.0, abs=1e-6) for t in starts), j


def test_fixed_time_and_coordinated_record_every_parameter(topo):
    kw = {"cycle": 120, "split": 0.7, "offsets": {"J2": 10.0}}
    assert make_controller("fixed_time", **kw).params == kw
    coord = make_controller("coordinated", progression_speed=10.0, split=0.7)
    assert coord.params == {"cycle": 90, "split": 0.7, "offsets": {}, "progression_speed": 10.0}
    coord.reset({}, 1, topo)
    assert coord.plan.offsets["J1"] == 0.0 and coord.plan.offsets["J2"] == pytest.approx(30.0)  # 300 m / 10 m/s
    # an explicit offset wins over the computed green wave for that junction only
    mixed = ready("coordinated", topo, offsets={"J3": 5.0})
    assert mixed.plan.offsets["J3"] == 5.0 and mixed.plan.offsets["J2"] == pytest.approx(24.0)
    assert mixed.params["offsets"] == {"J3": 5.0}


# --- AI recommender: demand model, Webster, cache, commands -------------------------------
def _approach_volumes(topo, flows):
    by_edge = {e: (j, s) for j, sides in topo.approach_edges.items() for s, e in sides.items()}
    volumes = defaultdict(float)
    for f in flows:
        for edge in topo.shortest_path(f.origin, f.destination):
            if edge in by_edge:
                volumes[by_edge[edge]] += f.veh_per_hour
    return volumes


def test_od_flows_reproduce_the_approach_volumes(topo):
    from teamb.scenarios import get_scenario

    truth = _approach_volumes(topo, get_scenario("rush_hour").flows)
    model = _approach_volumes(topo, od_flows(dict(truth), topo.tls_ids))
    for key, volume in truth.items():
        assert model[key] == pytest.approx(volume, abs=1.0), key


def test_probe_demand_model_uses_probes_only_and_drops_untrusted(topo):
    model = ProbeDemandModel(topo, window_s=120, defense=True)
    for t in range(0, 130, 10):
        obs = make_obs(topo, t, untrusted=[("J2", "N")])
        obs["junctions"]["J1"]["approaches"]["W"]["detector"]["flow_vph"] = 99999.0  # must be ignored
        model.add(obs)
    demand = model.approach_demand(130)
    assert demand[("J1", "W")] == pytest.approx(600.0)  # the probe flow, not the detector
    assert model.ignored > 0 and demand[("J2", "N")] == pytest.approx(600.0)  # filled from other junctions


def test_webster_plan_gives_the_heavy_axis_more_green():
    demand = {(j, s): v for j in ("J1", "J2", "J3", "J4") for s, v in (("W", 1300), ("E", 600), ("N", 180), ("S", 180))}
    lanes = {(j, s): (2 if s in "WE" else 1) for j, s in demand}
    plan = webster_plan(demand, lanes)
    assert 60 <= plan.cycle <= 150
    assert all(0.6 < share < 0.9 for share in plan.splits.values())
    assert plan.offsets["J1"] == 0 and plan.offsets["J2"] == pytest.approx(24.0)


def test_webster_seed_trial_keeps_relative_offsets_for_a_westbound_wave():
    import optuna

    from teamb.controllers.optimizer import plan_to_params, suggest_plan

    demand = {(j, s): v for j in ("J1", "J2", "J3", "J4") for s, v in (("W", 600), ("E", 900), ("N", 150), ("S", 150))}
    lanes = {(j, s): (2 if s in "WE" else 1) for j, s in demand}
    plan = webster_plan(demand, lanes)  # westbound heavier: the reference is J4, so J1's offset is not 0
    assert plan.offsets["J4"] == 0 and plan.offsets["J1"] != 0
    spec = SearchSpec(flows=[], current=TimingPlan().to_dict(), junctions=["J1", "J2", "J3", "J4"])
    again = suggest_plan(optuna.trial.FixedTrial(plan_to_params(plan, spec)), spec)
    assert again.cycle == plan.cycle and again.offsets["J1"] == 0.0
    for j in ("J2", "J3", "J4"):
        want = (plan.offsets[j] - plan.offsets["J1"]) % plan.cycle
        got = (again.offsets[j] - again.offsets["J1"]) % again.cycle
        assert min(abs(want - got), plan.cycle - abs(want - got)) < 0.1, (j, want, got)
    assert again.splits == pytest.approx({j: min(0.85, max(0.25, v)) for j, v in plan.splits.items()}, abs=1e-3)


def test_search_cache_round_trip(tmp_path):
    spec = SearchSpec(flows=[{"origin": "W0_J1", "destination": "J4_E5", "veh_per_hour": 900.0}],
                      current=TimingPlan(splits={"J1": 0.5}).to_dict(), trials=3)
    result = {"plan": {"cycle": 70.0, "splits": {}, "offsets": {}}, "expected": {"improvement_pct": 12.0}}
    save_cache(spec, result, tmp_path)
    assert load_cache(spec, tmp_path) == result
    other = SearchSpec(**{**spec.__dict__, "trials": 4})
    assert load_cache(other, tmp_path) is None


class _FakeProcess:
    def __init__(self, alive=True):
        self.alive, self.exitcode, self.joined = alive, None if alive else 1, 0

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.joined += 1


class _RacyQueue:
    """Empty on the first read; right after it the worker puts its result and exits."""

    def __init__(self, process, result=("result", {"plan": {"cycle": 70.0}})):
        self.items, self.process, self.result = [], process, result

    def get_nowait(self):
        import queue

        if self.items:
            return self.items.pop(0)
        if self.result is not None:
            self.items.append(self.result)
            self.result = None
            self.process.alive, self.process.exitcode = False, 0
        raise queue.Empty


def _fake_job(process, q):
    job = SearchJob.__new__(SearchJob)  # no real process
    job.process, job.queue = process, q
    return job


def test_search_job_poll_never_loses_a_result_put_just_before_exit():
    process = _FakeProcess()
    job = _fake_job(process, _RacyQueue(process))
    messages = job.poll() + job.poll()
    assert [m[0] for m in messages] == ["result"], messages
    assert process.joined >= 1, "a finished worker is reaped"
    dead = _FakeProcess(alive=False)
    lost = _fake_job(dead, _RacyQueue(dead, result=None)).poll()
    assert [m[0] for m in lost] == ["error"] and "without a result" in lost[0][1]


def test_run_search_with_zero_trials_keeps_the_current_plan(monkeypatch):
    from teamb.controllers import optimizer

    monkeypatch.setattr(optimizer, "evaluate_plan", lambda plan, spec: {
        "objective": 50.0, "mean_delay_s": 50.0, "p95_travel_time_s": 90.0, "completed": 100, "unfinished": 0})
    spec = SearchSpec(flows=[], current=TimingPlan(splits={"J1": 0.5}).to_dict(), trials=0)
    result = optimizer.run_search(spec)
    assert result["plan"] == spec.current and result["expected"]["improvement_pct"] == 0.0
    assert result["trials"] == 0 and "no search trials" in result["note"]


def test_ai_recommender_commands(topo):
    ctl = ready("ai_recommender", topo, approval_token="s3cret")
    assert ctl.pending_recommendation() is None
    assert ctl.handle_command({"type": "approve", "token": "s3cret"})["ok"] is False  # nothing pending
    plan = {"cycle": 70.0, "splits": {j: 0.7 for j in topo.tls_ids}, "offsets": {j: 0.0 for j in topo.tls_ids}}
    ctl.recommendation = {"id": "rec1-t600", "status": "pending", "plan": plan}
    assert ctl.handle_command({"type": "approve", "id": "rec1-t600"})["ok"] is False  # no token
    assert ctl.handle_command({"type": "approve", "id": "rec9", "token": "s3cret"})["ok"] is False  # wrong id
    assert ctl.handle_command({"type": "reject", "id": "rec1-t600", "token": "s3cret"})["status"] == "rejected"
    assert ctl.plan.cycle == 90.0, "a rejected plan is never applied"
    assert ctl.handle_command({"type": "optimize"}) == {"ok": True, "status": "searching",
                                                      "message": "the search starts at the next simulation step"}
    assert ctl.handle_command({"type": "something_else"}) is None
    assert [a["ok"] for a in ctl.audit] == [False, True, True]


def test_ai_recommender_rejects_stale_observations_against_the_sim_clock(topo):
    ctl = ready("ai_recommender", topo)
    ctl.propose_action(make_state(topo, 100))
    ctl.observe(make_obs(topo, 50))  # 50 s behind the simulation: a frozen / lagging feed
    assert ctl.guard.rejected["stale"] == 1 and not ctl.demand.samples
    assert ctl.t == 100, "an old observation must not rewind the controller's clock"
    ctl.observe(make_obs(topo, 100))
    assert len(ctl.demand.samples) == 1
    ctl.propose_action(make_state(topo, 115))
    ctl.observe(make_obs(topo, 100))  # the feed froze at t=100 while the simulation moved on
    assert ctl.guard.rejected["stale"] == 2 and ctl.t == 115


class _StubJob:
    def __init__(self):
        self.cancelled = 0

    def cancel(self):
        self.cancelled += 1

    def poll(self):
        return []


def test_ai_recommender_reports_a_search_cut_off_by_the_end_of_the_run(topo):
    ctl = ready("ai_recommender", topo)
    ctl.propose_action(make_state(topo, 600))
    rec = {"id": "rec1-t600", "status": "searching", "created_t": 600.0, "plan": None, "note": ""}
    ctl.recommendation = rec
    ctl.history.append(rec)
    ctl._job = job = _StubJob()
    summary = ctl.summary()  # SimEnv asks for the summary before close()
    row = summary["recommendations"][0]
    assert row["status"] == "cancelled" and "auto_approve" in row["note"] and row["decided_by"] == "system"
    assert summary["plan_applied"] is False
    ctl.close()
    assert ctl._job is None and job.cancelled == 1
    assert rec["status"] == "cancelled" and rec["decided_t"] == 600.0
    assert [e["type"] for e in ctl.drain_events()] == ["recommendation_cancelled"]


def test_ai_recommender_auto_approve_applies_the_plan(topo, monkeypatch):
    from teamb.controllers import optimizer

    plan = {"cycle": 70.0, "splits": {j: 0.6 for j in topo.tls_ids}, "offsets": {j: 0.0 for j in topo.tls_ids}}
    monkeypatch.setattr(optimizer, "run_search", lambda spec, progress=None: {
        "plan": plan, "expected": {"mean_delay_s": 30.0, "baseline_mean_delay_s": 40.0, "improvement_pct": 25.0},
        "note": "", "trials": spec.trials, "wall_s": 0.0})
    ctl = ready("ai_recommender", topo, auto_approve=True, search_at=10, cache=False)
    assert ctl.sync, "auto_approve searches synchronously by default"
    for t in range(0, 12):
        ctl.observe(make_obs(topo, t))
        ctl.propose_action(make_state(topo, t))
        ctl.log(t)
    assert ctl.recommendation["status"] == "approved" and ctl.plan.cycle == 70.0
    assert ctl.summary()["plan_applied"] is True


# --- RL ------------------------------------------------------------------------------------
def test_qtable_file_is_checked(tmp_path):
    table = QTable()
    table.q[encode_state("EW", 0, 9, 20), 1] = -1.0
    table.q[encode_state("EW", 0, 9, 20), 0] = -2.0
    path = table.save(tmp_path / "q.json")
    loaded = QTable.load(path)
    assert loaded.best(encode_state("EW", 0, 9, 20)) == 1
    data = json.loads(path.read_text())
    data["q"][0][0] = 99.0  # tampering
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="checksum"):
        QTable.load(path)
    with pytest.raises(FileNotFoundError, match="rl_train"):
        QTable.load(tmp_path / "missing.json")


def test_rl_masks_and_trained_table(topo):
    if not MODEL_PATH.exists():
        pytest.skip("models/rl_qtable.json not trained yet: python -m teamb.controllers.rl_train")
    table = QTable.load(MODEL_PATH)
    assert table.q.shape == (N_STATES, 2) and table.meta.get("episodes", 0) > 0
    assert len({table.best(s) for s in range(N_STATES) if table.visits[s].sum() > 0}) == 2, "learned both actions"
    ctl = ready("rl", topo)
    ctl.observe(make_obs(topo, 100, count={("J1", "W"): 3}))
    assert ctl.propose_action(make_state(topo, 100)) == {}, "never switches to an empty street"
    ctl.observe(make_obs(topo, 105, count={("J1", "W"): 20, ("J1", "N"): 2}, queue={("J1", "N"): 2}))
    assert ctl.propose_action(make_state(topo, 105, green_s=61)).get("J1") == "NS", "max green"


# --- inside SimEnv (short SUMO runs) -----------------------------------------------------------
def run_env(name, tmp_path, *, end=240.0, coverage=0.25, params=None, on_step=None, seed=3):
    from teamb.sim.env import SimEnv

    env = SimEnv("rush_hour", name, seed=seed, coverage=coverage, end_time=end, controller_params=params or {},
                 output_dir=tmp_path / f"{name}_{seed}")
    tls = set()
    original = env.controller.propose_action

    def checked(state):  # the supervisor must only ever see well-formed proposals
        action = original(state)
        assert isinstance(action, dict) and set(action) <= tls, action
        assert all(v in ("EW", "NS", None) for v in action.values()), action
        return action

    env.controller.propose_action = checked
    env.start()
    tls.update(env.topology.tls_ids)
    try:
        while env.t < env.end_time:
            env.step()
            if on_step:
                on_step(env)
    except BaseException:
        env.close()  # never leave a SUMO process behind when a step fails
        raise
    return env, env.close()


def green_share(env, junction, axis, t0, t1):
    """Share of [t0, t1) in which `junction` showed `axis` green, from the supervisor's events."""
    changes = [(e.t, e.executed) for e in env.supervisor.events if e.junction == junction and e.executed]
    shown, since, total = "EW_G", 0.0, 0.0  # every junction starts in EW green
    for t, signal in changes + [(t1, None)]:
        a, b = max(since, t0), min(t, t1)
        if b > a and shown == f"{axis}_G":
            total += b - a
        since, shown = t, signal or shown
    return total / (t1 - t0)


def green_lengths(env, axis):
    """Durations of the completed greens of one axis, all junctions (green start → yellow start)."""
    lengths, started = [], {}
    for e in env.supervisor.events:
        if e.executed and e.executed.endswith("_G"):
            started[e.junction] = (e.executed, e.t)
        elif e.executed and e.executed.endswith("_Y") and e.junction in started:
            signal, t0 = started.pop(e.junction)
            if signal == f"{axis}_G":
                lengths.append(e.t - t0)
    return lengths


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_every_controller_runs_in_simenv(name, tmp_path):
    if name == "rl" and not MODEL_PATH.exists():
        pytest.skip("RL model not trained yet")
    env, summary = run_env(name, tmp_path)
    assert summary["controller_errors"] == 0 and summary["fallback_steps"] == 0
    assert summary["rejected_actions"] == 0
    assert summary["signal_switches"] > 0
    if name in ("actuated", "max_pressure", "rl"):  # they react to demand: the busy arterial gets longer greens
        ew, ns = green_lengths(env, "EW"), green_lengths(env, "NS")
        assert ew and ns and sum(ew) / len(ew) > 1.4 * sum(ns) / len(ns), (ew, ns)


def test_probe_attack_fools_max_pressure_probe_but_not_the_defense(tmp_path):
    def attack(env):
        if env.t == 100:
            env.handle_command({"type": "start_attack", "junction": "J2", "approach": "N", "n": 99})

    blind, _ = run_env("max_pressure_probe", tmp_path, end=300, on_step=attack)
    guarded, _ = run_env("max_pressure", tmp_path, end=300, on_step=attack, params={"source": "probe", "defense": True})
    before = green_share(blind, "J2", "NS", 30, 100)
    after_blind = green_share(blind, "J2", "NS", 110, 300)
    after_guarded = green_share(guarded, "J2", "NS", 110, 300)
    assert after_blind > 0.7 > before, (before, after_blind)  # fooled: J2 serves phantom cars
    assert after_guarded < 0.45, after_guarded  # the defense keeps J2 normal
    assert guarded.controller.guard.rejected["untrusted_probe"] + guarded.controller.guard.rejected["implausible_probe"] > 0


def test_ai_recommender_sync_search_then_approve(tmp_path):
    from teamb.sim.env import SimEnv

    params = {"sync": True, "search_at": 120, "trials": 3, "eval_warmup": 120, "eval_horizon": 240, "cache": str(tmp_path / "cache")}
    env = SimEnv("rush_hour", "ai_recommender", seed=3, coverage=0.5, end_time=200, controller_params=params,
                 output_dir=tmp_path / "ai")
    env.start()
    try:
        _sync_search_then_approve(env)
    finally:
        summary = env.close()  # never leave SUMO running if an assertion fails
    assert summary["controller_errors"] == 0 and summary["fallback_steps"] == 0
    assert any(p.suffix == ".json" for p in (tmp_path / "cache").iterdir())


def _sync_search_then_approve(env):
    ctl = env.controller
    while env.t < 125:
        env.step()
    rec = env.frame()["recommendation"]
    assert rec["status"] == "pending" and rec["progress"]["done"] == rec["progress"]["total"] == 4
    plan = rec["plan"]
    assert 60 <= plan["cycle"] <= 150 and set(plan["splits"]) == set(env.topology.tls_ids)
    assert all(0.25 <= s <= 0.85 for s in plan["splits"].values())
    assert all(0 <= o < plan["cycle"] for o in plan["offsets"].values())
    assert {"mean_delay_s", "baseline_mean_delay_s", "improvement_pct"} <= set(rec["expected"])
    assert rec["based_on"]["estimated_flows"]["J1"]["W"] > 0 and rec["based_on"]["source"].startswith("navigation")
    assert ctl.plan.cycle == 90.0, "nothing is applied before approval"
    reply = env.handle_command({"type": "approve", "id": rec["id"]})
    assert reply["ok"] and reply["status"] == "approved"
    assert ctl.plan.to_dict() == TimingPlan(plan["cycle"], plan["splits"], plan["offsets"]).to_dict()
    while env.t < 200:
        env.step()
        state = env.supervisor.state(env.t)
        assert ctl.propose_action(state) == {j: ctl.plan.axis_at(j, env.t) for j in state["junctions"]}


def test_search_job_runs_in_a_background_process():
    flows = [{"origin": "W0_J1", "destination": "J4_E5", "veh_per_hour": 800.0},
             {"origin": "NN2_N2", "destination": "J2_S2", "veh_per_hour": 150.0}]
    spec = SearchSpec(flows=flows, current=TimingPlan(splits={j: 0.5 for j in ("J1", "J2", "J3", "J4")}).to_dict(),
                      trials=1, eval_warmup=60, eval_horizon=120, cooldown=60)
    job = SearchJob(spec)
    messages, deadline = [], time.time() + 180
    while time.time() < deadline and not any(m[0] in ("result", "error") for m in messages):
        messages += job.poll()  # never blocks
        time.sleep(0.2)
    job.cancel()
    kinds = [m[0] for m in messages]
    assert "progress" in kinds and kinds[-1] == "result", messages[-1:]
    assert 60 <= messages[-1][1]["plan"]["cycle"] <= 150
