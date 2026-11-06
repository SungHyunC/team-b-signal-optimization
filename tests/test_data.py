"""Tests for the data & evaluation area: sensors, metrics, statistics and the experiment runner.

Fast unit tests first; two short SUMO runs at the end (about 30 s in total).
"""
from __future__ import annotations

import csv
import json
import math
import random

import pytest

from teamb.evaluation.recovery import event_windows, recovery_time
from teamb.evaluation.spillback import SpillbackMonitor, entrance_blocked
from teamb.evaluation.stats import holm, improvement_pct, mean_ci, paired, t_critical, t_sf, t_two_sided_p
from teamb.sensors.crosscheck import PERSIST_BAD_S, PERSIST_GOOD_S, CrossCheck
from teamb.sensors.logs import ESTIMATION_COLUMNS, RollingCount
from teamb.sensors.sampling import ProbeSelector, SamplingSpec, group_probabilities, parse_sampling, report_probability

COVERAGES = (0.1, 0.25, 0.5, 0.75, 1.0)


# --- sampling -------------------------------------------------------------------------
def _departures(n=20000, arterial_share=0.57, seed=3):
    rng = random.Random(seed)
    return ["arterial" if rng.random() < arterial_share else "cross" for _ in range(n)]


@pytest.mark.parametrize("coverage", COVERAGES)
def test_uniform_share_matches_coverage(coverage):
    sel = ProbeSelector(SamplingSpec("uniform"), random.Random(1))
    groups = _departures()
    picked = sum(sel.select(g, coverage) for g in groups)
    sigma = math.sqrt(coverage * (1 - coverage) / len(groups))
    assert abs(picked / len(groups) - coverage) <= 4 * sigma + 1e-9


@pytest.mark.parametrize("coverage", COVERAGES)
def test_approach_biased_keeps_overall_share_but_favours_arterial(coverage):
    sel = ProbeSelector(parse_sampling("approach_biased"), random.Random(2))
    for g in _departures():
        sel.select(g, coverage)
    shares = sel.shares()
    assert abs(shares["overall"] - coverage) < 0.015
    if coverage < 0.6:  # below the cap the arterial share is ~2x the cross-street share
        assert 1.7 < shares["arterial"] / shares["cross"] < 2.3
    elif coverage < 1.0:
        assert shares["arterial"] > shares["cross"]
    else:
        assert shares["arterial"] == shares["cross"] == 1.0


def test_group_probabilities_water_filling():
    p = group_probabilities(0.25, {"arterial": 0.57, "cross": 0.43}, {"arterial": 2.0, "cross": 1.0})
    assert p["arterial"] == pytest.approx(2 * p["cross"], rel=1e-6)
    assert 0.57 * p["arterial"] + 0.43 * p["cross"] == pytest.approx(0.25, abs=1e-9)
    capped = group_probabilities(0.9, {"arterial": 0.57, "cross": 0.43}, {"arterial": 2.0, "cross": 1.0})
    assert capped["arterial"] == pytest.approx(1.0)
    assert capped["cross"] == pytest.approx((0.9 - 0.57) / 0.43, abs=1e-6)


def test_speed_biased_reporting_and_parsing():
    spec = parse_sampling("speed_biased")
    assert report_probability(spec, 0.0) == pytest.approx(0.3)
    assert report_probability(spec, 8.0) == 1.0
    assert report_probability(parse_sampling("uniform"), 0.0) == 1.0
    assert parse_sampling("speed_biased:0.2").stopped_report_prob == 0.2
    assert parse_sampling("approach_biased:3").arterial_ratio == 3.0
    assert parse_sampling("approach_biased:3").label == "approach_biased:3"
    rng = random.Random(5)
    sent = sum(rng.random() < report_probability(spec, 0.0) for _ in range(10000))
    assert abs(sent / 10000 - 0.3) < 0.02
    for bad in ("nonsense", "uniform:2", "speed_biased:1.5"):
        with pytest.raises(ValueError):
            parse_sampling(bad)


def test_rolling_count_window():
    rc = RollingCount(300.0)
    for t in range(0, 600):
        rc.add(float(t), 1 if t % 10 == 0 else 0)
    assert rc.total == 30  # one vehicle every 10 s over the last 300 s
    assert rc.rate_vph(599.0) == pytest.approx(360.0)


# --- fake-data cross-check ------------------------------------------------------------
def _check():
    zone = {"l0": 99.0 / 7.0}
    storage = {("J2", "N"): 232.0 / 7.0}
    return CrossCheck(zone, storage)


def test_crosscheck_tests():
    cc, key = _check(), ("J2", "N")
    assert cc.suspicious(key, 99 + 1, 2, False, 0.25) == "storage"  # 99 phones cannot fit on a 232 m lane
    assert cc.suspicious(key, 99, 30, True, 0.25) == "storage"  # ... not even when the detector is full
    assert cc.suspicious(key, 10, 3, False, 0.25) == "detector"
    assert cc.suspicious(key, 5, 2, False, 0.25) == "statistical"
    assert cc.suspicious(key, 3, 10, False, 0.25) == ""  # plausible
    assert cc.suspicious(key, 12, 3, True, 0.25) == ""  # full zone: queue may be longer than seen
    assert cc.zone_full([("l0", 11, 20.0)]) and cc.zone_full([("l0", 0, 45.0)]) and not cc.zone_full([("l0", 2, 10.0)])


def test_crosscheck_detector_cannot_verify_right_after_its_zone_was_full():
    cc, key = _check(), ("J2", "N")
    assert cc.unverifiable(100.0, key, [("l0", 12, 60.0)])  # full now
    assert cc.unverifiable(130.0, key, [("l0", 1, 5.0)])  # queue discharging: its tail may still stand
    assert not cc.unverifiable(170.0, key, [("l0", 1, 5.0)])  # a minute later the detector is trusted again


def test_crosscheck_hysteresis_and_episodes():
    cc, key = _check(), ("J2", "N")
    for i in range(PERSIST_BAD_S - 1):
        assert cc.update(float(i), key, "storage", 99) is True
    assert cc.update(10.0, key, "storage", 99) is False  # flagged after PERSIST_BAD_S bad seconds
    for i in range(PERSIST_GOOD_S - 1):
        assert cc.update(11.0 + i, key, "", 0) is False
    assert cc.update(30.0, key, "", 0) is True
    assert len(cc.episodes) == 1 and cc.episodes[0].start == 10.0 and cc.episodes[0].end == 30.0


# --- statistics ----------------------------------------------------------------------
def test_t_table_and_distribution():
    assert t_critical(1) == 12.706 and t_critical(30) == 2.042
    assert 2.021 < t_critical(35) < 2.042
    assert t_critical(10_000) == pytest.approx(1.96, abs=0.002)
    for df in (1, 2, 5, 10, 30, 120):  # the table and the CDF agree
        assert t_sf(t_critical(df), df) == pytest.approx(0.025, abs=5e-4)
    assert t_two_sided_p(0.0, 5) == pytest.approx(1.0)


def test_mean_ci_and_paired_toy_numbers():
    s = mean_ci([1.0, 2.0, 3.0])
    assert s["mean"] == 2.0 and s["sd"] == pytest.approx(1.0)
    assert s["ci95"] == pytest.approx(4.303 / math.sqrt(3))
    assert mean_ci([5.0])["ci95"] is None and mean_ci([None])["mean"] is None
    pr = paired({1: 10.0, 2: 12.0, 3: 14.0, 9: 50.0}, {1: 9.0, 2: 10.0, 3: 12.0, 4: 1.0})
    assert pr["seeds"] == [1, 2, 3] and pr["n"] == 3  # only matched seeds
    assert pr["diff"]["mean"] == pytest.approx(-5 / 3)
    assert pr["diff"]["ci95"] == pytest.approx(4.303 * math.sqrt(1 / 3) / math.sqrt(3))
    assert pr["improvement_pct"]["mean"] == pytest.approx((10 + 100 / 6 + 100 / 7) / 3)
    assert pr["t"] == pytest.approx(-5.0)
    assert pr["p_value"] == pytest.approx(0.0377, abs=5e-4)
    assert improvement_pct(0.0, 5.0) is None and improvement_pct(100.0, 80.0) == pytest.approx(20.0)


def test_holm_adjustment():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([None, 0.2]) == [None, 0.2]


# --- recovery and spillback (pure functions) -----------------------------------------------
def test_recovery_time_on_synthetic_series():
    times = [float(t) for t in range(0, 3000, 5)]

    def level(t):
        if 1000 <= t < 1500:
            return 30.0
        if 1500 <= t < 1800:
            return 30.0 - 20.0 * (t - 1500) / 300.0
        return 10.0

    vals = [level(t) for t in times]
    res = recovery_time(times, vals, start=1000.0, end=1500.0)
    assert res["pre_level"] == pytest.approx(10.0)
    assert not res["censored"] and 230 <= res["recovery_s"] <= 300
    assert res["excess_veh_h"] > 0
    censored = recovery_time(times, vals, start=1000.0, end=None)
    assert censored["censored"] and censored["recovery_s"] is None


def test_recovery_against_a_no_event_counterfactual():
    from teamb.evaluation.recovery import recovery_vs_reference

    times = [float(t) for t in range(1, 4500, 5)]
    reference = [10.0 + 20.0 * t / 4500 for t in times]  # demand (and delay) grows during the run
    bump = [30.0 if 1500 <= t < 3300 else (30.0 * (3600 - t) / 300 if 3300 <= t < 3600 else 0.0) for t in times]
    disrupted = [r + b for r, b in zip(reference, bump)]
    pre = recovery_time(times, disrupted, start=1500.0, end=3300.0)
    assert pre["censored"]  # the pre-event level (lower demand) is never reached again
    cf = recovery_vs_reference(times, disrupted, times, reference, start=1500.0, end=3300.0)
    assert not cf["censored"] and 200 <= cf["recovery_s"] <= 320
    assert cf["excess_veh_h"] == pytest.approx((30 * 1800 + 15 * 300) / 3600, rel=0.02)


def test_event_windows_pairs_and_merges():
    events = [
        {"t": 100.0, "type": "road_closed", "edge": "J2_N2"},
        {"t": 100.0, "type": "road_closed", "edge": "N2_J2"},
        {"t": 300.0, "type": "road_reopened", "edge": "J2_N2"},
        {"t": 300.0, "type": "road_reopened", "edge": "N2_J2"},
        {"t": 400.0, "type": "attack_started", "junction": "J2", "approach": "N"},
        {"t": 500.0, "type": "attack_stopped"},  # the env's form: no junction given
    ]
    w = event_windows(events, run_end=900.0)
    assert [(x["kind"], x["start"], x["end"]) for x in w] == [("closure", 100.0, 300.0), ("attack", 400.0, 500.0)]
    assert w[0]["what"] == "J2_N2+N2_J2"


def test_event_windows_merges_overlapping_disruptions():
    # the earthquake: two closures at 1200 s, reopened at 3000 s and 3600 s (evaluation-3)
    events = [{"t": 1200.0, "type": "road_closed", "edge": e} for e in ("J3_J4", "J4_J3", "J1_N1", "N1_J1")]
    events += [{"t": 3000.0, "type": "road_reopened", "edge": e} for e in ("J3_J4", "J4_J3")]
    events += [{"t": 3600.0, "type": "road_reopened", "edge": e} for e in ("J1_N1", "N1_J1")]
    w = event_windows(events, run_end=4500.0)
    assert [(x["kind"], x["start"], x["end"]) for x in w] == [("closure", 1200.0, 3600.0)]
    assert set(w[0]["what"].split("+")) == {"J3_J4", "J4_J3", "J1_N1", "N1_J1"} and len(w[0]["parts"]) == 4
    # touching windows merge, separate ones stay apart, an open window stays open
    events = [
        {"t": 100.0, "type": "road_closed", "edge": "A"}, {"t": 300.0, "type": "road_reopened", "edge": "A"},
        {"t": 300.0, "type": "attack_started", "junction": "J2", "approach": "N"},
        {"t": 400.0, "type": "attack_stopped"},
        {"t": 900.0, "type": "road_closed", "edge": "B"},
        {"t": 950.0, "type": "road_closed", "edge": "C"}, {"t": 990.0, "type": "road_reopened", "edge": "C"},
    ]
    w = event_windows(events, run_end=1200.0)
    assert [(x["kind"], x["start"], x["end"]) for x in w] == [("mixed", 100.0, 400.0), ("closure", 900.0, None)]


def _metrics_stub(times, rates, end_time):
    from teamb.evaluation.metrics import MetricsCollector

    m = object.__new__(MetricsCollector)  # _recovery only needs the timeseries and the end time
    m.timeseries = [(t, 1, 0, 0, 0.0, r) for t, r in zip(times, rates)]
    m.end_time = end_time
    return m


def test_recovery_excess_is_not_double_counted_for_overlapping_windows():
    times = [float(t) for t in range(0, 4500, 5)]
    rates = [30.0 if 1200 <= t < 3600 else 10.0 for t in times]
    events = [
        {"t": 1200.0, "type": "road_closed", "edge": "J3_J4"}, {"t": 1200.0, "type": "road_closed", "edge": "J1_N1"},
        {"t": 3000.0, "type": "road_reopened", "edge": "J3_J4"}, {"t": 3600.0, "type": "road_reopened", "edge": "J1_N1"},
    ]
    rec = _metrics_stub(times, rates, 4500.0)._recovery(events)
    single = recovery_time(times, rates, start=1200.0, end=3600.0)
    assert rec["headline"]["disruptions"] == 1
    assert rec["headline"]["excess_delay_veh_h"] == pytest.approx(single["excess_veh_h"])
    assert single["excess_veh_h"] == pytest.approx(20 * 2400 / 3600, rel=0.01)
    assert rec["detail"][0]["recovered_at"] >= 3600.0  # measured after the last closure ended


def test_recovery_excess_of_separate_disruptions_counts_each_second_once():
    from teamb.evaluation.recovery import union_excess

    # the first disruption has not recovered when the second starts (rate 30 from 1000 to 2600)
    times = [float(t) for t in range(0, 4500, 5)]
    rates = [30.0 if 1000 <= t < 2600 else 10.0 for t in times]
    events = [
        {"t": 1000.0, "type": "road_closed", "edge": "A"}, {"t": 1200.0, "type": "road_reopened", "edge": "A"},
        {"t": 1250.0, "type": "attack_started", "junction": "J2", "approach": "N"},
        {"t": 1500.0, "type": "attack_stopped"},
    ]
    rec = _metrics_stub(times, rates, 4500.0)._recovery(events)
    first, second = rec["detail"]
    assert rec["headline"]["disruptions"] == 2 and first["recovered_at"] >= 2600 and second["recovered_at"] >= 2550
    assert second["excess_veh_h"] > 1.0  # its seconds are also in the first window: a plain sum double-counts
    assert rec["headline"]["excess_delay_veh_h"] == pytest.approx(first["excess_veh_h"], abs=0.01)
    assert first["excess_veh_h"] == pytest.approx(20 * 1600 / 3600, rel=0.01)
    # with one window the union is that window's excess; a reference series works the same way
    one = recovery_time(times, rates, start=1000.0, end=1200.0)
    assert union_excess(times, rates, [(1000.0, one["recovered_at"], one["pre_level"])]) == one["excess_veh_h"]
    ref = {t: 10.0 for t in times}
    assert union_excess(times, rates, [(1000.0, 3000.0, ref), (1500.0, 2000.0, ref)]) == pytest.approx(20 * 1600 / 3600, rel=0.01)
    assert union_excess(times, rates, []) is None


def test_recovery_vs_reference_without_matched_samples_is_unknown():
    from teamb.evaluation.recovery import recovery_vs_reference

    times = [float(t) for t in range(1, 1500, 5)]
    vals = [10.0] * len(times)
    res = recovery_vs_reference(times, vals, times, vals, start=2000.0, end=2500.0)  # event after the last sample
    assert res["excess_veh_h"] is None and res["censored"]


def test_depart_delay_metrics_leave_the_primary_endpoint_unchanged(tmp_path):
    # evaluation-5: timeLoss excludes departDelay; the total is reported next to mean_delay_s
    from types import SimpleNamespace

    from teamb.evaluation.metrics import MetricsCollector

    (tmp_path / "tripinfo.xml").write_text(
        '<tripinfos>'
        '<tripinfo id="a" depart="1000" arrival="1400" duration="400" timeLoss="100" departDelay="400" waitingCount="2"/>'
        '<tripinfo id="b" depart="1100" arrival="1300" duration="200" timeLoss="50" departDelay="0" waitingCount="1"/>'
        '<tripinfo id="c" depart="1500" arrival="-1" duration="100" timeLoss="20" departDelay="30"/>'
        '</tripinfos>'
    )
    m = object.__new__(MetricsCollector)
    m.warmup, m.end_time, m._t_last = 900.0, 1600.0, 1600.0
    m.queue_samples, m.spillback_steps, m.queue_warning_seconds, m.teleports = [], 0, 0.0, 0
    m._approaches, m.timeseries = [], []
    m.feed = SimpleNamespace(sensors=None, events=[])
    m.spill = SimpleNamespace(summary=lambda: {})
    s = m.finalize(tmp_path / "tripinfo.xml", planned_in_window=4, events=[])
    assert s["mean_delay_s"] == 75.0  # unchanged definition: timeLoss of finished trips
    assert s["mean_delay_incl_depart_s"] == 275.0  # (100 + 400 + 50 + 0) / 2
    assert s["mean_depart_delay_s"] == pytest.approx(430 / 3, abs=0.01)  # all inserted window trips
    assert s["mean_delay_incl_unfinished_s"] == pytest.approx(170 / 3, abs=0.01)  # accrued: a lower bound
    assert s["completed"] == 2 and s["in_network_at_end"] == 1 and s["never_inserted"] == 1


def test_spillback_needs_upstream_blocking_evidence():
    from teamb.network.topology import load_topology

    mon = SpillbackMonitor(load_topology())
    link = mon.links["J1_J2"]
    (lane, length), feeder = link["lanes"][0], next(f for f in link["feeders"] if f[0].startswith("W0_J1"))
    queue = [(f"q{i}", 0.0) for i in range(30)]
    positions = {f"q{i}": (5.0 + 9.0 * i, 0.0) for i in range(30)}  # stopped from the entrance to the stop line
    positions["front"] = (feeder[1] - 2.0, 0.0)
    by_lane = {lane: queue, feeder[0]: [("front", 0.0)]}
    assert entrance_blocked(queue, positions, length)
    assert mon.is_spillback("J1_J2", by_lane, positions, lambda vid: (lane, "G"))
    assert not mon.is_spillback("J1_J2", by_lane, positions, lambda vid: (lane, "r"))  # red: no evidence
    short = {k: (v[0] + 40.0, 0.0) for k, v in positions.items() if k != "front"} | {"front": positions["front"]}
    assert not mon.is_spillback("J1_J2", by_lane, short, lambda vid: (lane, "G"))  # entrance free
    assert mon.check(by_lane, positions, lambda vid: (lane, "G"), 5.0, True) == []  # needs 2 samples in a row
    assert "J1_J2" in mon.check(by_lane, positions, lambda vid: (lane, "G"), 5.0, True)
    assert mon.summary()["spillback_duration_s"] == 5.0 and mon.summary()["spillback_events"] == 1


# --- SUMO: one short attack run --------------------------------------------------------------
ATTACK_AT, ATTACK_END, END = 400.0, 500.0, 620.0


@pytest.fixture(scope="module")
def attack_run(tmp_path_factory):
    from teamb.sim.env import SimEnv

    out = tmp_path_factory.mktemp("attack_run")
    env = SimEnv(
        "fake_data_attack", "fixed_time", seed=1, coverage=0.25, end_time=END, output_dir=out,
        scenario_params={
            "warmup": 200.0,
            "events": [
                {"time": ATTACK_AT, "kind": "start_attack", "params": {"junction": "J2", "approach": "N", "n": 99}},
                {"time": ATTACK_END, "kind": "stop_attack", "params": {}},
            ],
        },
    )
    seen = {}

    def grab(e):
        if e.t in (300.0, ATTACK_AT + 10):
            seen[e.t] = {"obs": e.sensors._last_obs, "alerts": e.sensors.alerts(), "kpi": e.metrics.live()}

    summary = env.run(callback=grab)
    return {"env": env, "summary": summary, "seen": seen, "out": out}


def test_observation_contract(attack_run):
    obs = attack_run["seen"][300.0]["obs"]
    assert {"t", "coverage", "sampling", "junctions", "alerts"} <= set(obs)
    entry = obs["junctions"]["J1"]["approaches"]["W"]
    assert {"queue", "count", "occupancy", "speed", "flow_vph", "gap_s"} <= set(entry["detector"])
    assert {"queue_est", "n", "halted", "speed", "flow_est_vph", "trusted"} <= set(entry["probe"])
    assert "oracle" not in entry  # fixed_time is not an oracle benchmark: no ground truth
    assert obs["junctions"]["J1"]["exits"]["E"]["detector"] is not None
    assert {"vehicles", "halting", "mean_delay", "queues", "spillback"} <= set(attack_run["seen"][300.0]["kpi"])


def test_fake_reports_raise_alerts(attack_run):
    assert attack_run["seen"][300.0]["alerts"] == []  # no false alarm before the attack
    alerts = attack_run["seen"][ATTACK_AT + 10]["alerts"]
    assert any(a["junction"] == "J2" and a["approach"] == "N" and a["type"] == "probe_detector_mismatch" for a in alerts)
    obs = attack_run["seen"][ATTACK_AT + 10]["obs"]
    assert obs["junctions"]["J2"]["approaches"]["N"]["probe"]["trusted"] is False
    s = attack_run["summary"]
    assert s["attack_detected"] is True and s["detection_delay_s"] <= 5
    assert s["false_alarm_s"] == 0


def test_metrics_summary_perf01_and_new_fields(attack_run):
    s = attack_run["summary"]
    baseline_keys = {
        "completed", "unfinished", "unfinished_pct", "mean_delay_s", "mean_travel_time_s", "p95_travel_time_s",
        "stops_per_veh", "throughput_veh_h", "mean_queue_veh", "max_queue_veh", "spillback_samples", "ev_count",
        "ev_mean_travel_time_s",
    }
    new_keys = {
        "planned_in_window", "inserted_in_window", "in_network_at_end", "never_inserted", "arterial_mean_delay_s",
        "cross_mean_delay_s", "queue_p95_veh", "spillback_duration_s", "spillback_events", "recovery_time_s",
        "excess_delay_veh_h", "est_queue_mae", "est_queue_bias", "est_flow_mae", "det_queue_mae", "probe_share",
        "mean_depart_delay_s", "mean_delay_incl_depart_s", "mean_delay_incl_unfinished_s",
    }
    assert baseline_keys | new_keys <= set(s)
    assert s["completed"] > 0 and s["unfinished"] >= 0
    assert s["completed"] + s["unfinished"] == max(s["planned_in_window"], s["inserted_in_window"])
    assert s["unfinished_pct"] == pytest.approx(100 * s["unfinished"] / (s["completed"] + s["unfinished"]), abs=0.01)
    assert s["disruptions"] == 1  # the attack window
    assert 0.15 < s["probe_share"] < 0.35


def test_run_writes_evaluation_files(attack_run):
    out = attack_run["out"]
    for name in ("summary.json", "trips.csv", "timeseries.csv", "estimation.csv", "detector_intervals.csv", "evaluation.json"):
        assert (out / name).exists(), name
    with open(out / "estimation.csv") as fh:
        rows = list(csv.reader(fh))
    assert tuple(rows[0]) == ESTIMATION_COLUMNS and len(rows[1]) == len(ESTIMATION_COLUMNS)
    attacked = [r for r in rows[1:] if r[1] == "J2" and r[2] == "N" and r[4] == "1"]
    assert attacked and all(r[5] == "0" for r in attacked[2:])  # untrusted while attacked (after hysteresis)
    detail = json.loads((out / "evaluation.json").read_text())
    assert detail["alerts"]["attacks"][0]["detected"] is True


# --- SUMO: the experiment runner on a tiny matrix ----------------------------------------------
def test_runner_end_to_end_tiny_matrix(tmp_path):
    from teamb.experiments.analysis import write_report
    from teamb.experiments.runner import build_matrix, run_matrix, validate_matrix

    specs = build_matrix(
        ["rush_hour"], ["fixed_time", "coordinated"], [1, 2], [1.0], end_time=420.0, scenario_params={"warmup": 150.0}
    )
    assert len(specs) == 4 and not validate_matrix(specs)
    assert validate_matrix(build_matrix(["rush_hour"], ["no_such_controller"], [1], [1.0]))
    record = run_matrix(specs, tmp_path, workers=2, quiet=True)
    assert record["ok"] == 4 and not record["failed"]
    report = write_report(tmp_path, baseline="fixed_time")
    with open(tmp_path / "summary.csv") as fh:
        assert len(list(csv.DictReader(fh))) == 4
    data = json.loads((tmp_path / "report.json").read_text())
    assert {"name", "created", "baseline", "rows"} <= set(data) and data["baseline"] == "fixed_time"
    row_keys = {"scenario", "controller", "coverage", "n_seeds", "mean_delay_s", "p95_travel_time_s", "stops_per_veh",
                "unfinished_pct", "ev_mean_travel_time_s", "delta_vs_baseline_pct"}
    for row in data["rows"]:
        assert row_keys <= set(row) and row["n_seeds"] == 2
        for k in ("mean_delay_s", "p95_travel_time_s", "stops_per_veh", "unfinished_pct", "ev_mean_travel_time_s", "delta_vs_baseline_pct"):
            assert set(row[k]) >= {"mean", "ci95"}
    coord = next(r for r in report["rows"] if r["controller"] == "coordinated")
    base = next(r for r in report["rows"] if r["controller"] == "fixed_time")
    assert coord["n_paired"] == 2 and coord["delta_vs_baseline_pct"]["mean"] is not None
    assert base["delta_vs_baseline_pct"] == {"mean": 0.0, "ci95": 0.0}
    assert (tmp_path / "report.md").read_text().startswith("# Experiment report")
    again = run_matrix(specs, tmp_path, workers=1, quiet=True)  # finished runs are skipped
    assert again["skipped"] == 4
