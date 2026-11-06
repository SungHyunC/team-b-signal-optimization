"""A 20-phone fake-data attack on a busy arterial approach (scenarios-sensors-2, -9).

99 phones on the one-lane north approach (the catalog attack) exceed what fits on the road and
are caught by the trivial storage test. 20 phones on the two-lane arterial J2 W do fit, and
in the peak the detector zone there is full or recently full most of every cycle, so the first
version only had the storage test left and trusted the attack 89 % of the time. Short SUMO
runs (about 5 s each)."""
from __future__ import annotations

import pytest

from teamb.sim.env import SimEnv

ATTACK_AT = 1500.0
ATTACK = {"junction": "J2", "approach": "W", "n": 20}


def _attack_run(tmp_path, controller="fixed_time", params=None, end=1800.0, attack=True):
    events = [{"time": ATTACK_AT, "kind": "start_attack", "params": dict(ATTACK)}] if attack else []
    env = SimEnv("fake_data_attack", controller, seed=1, coverage=0.25, end_time=end, output_dir=tmp_path,
                 controller_params=params, scenario_params={"events": events})
    seconds = []

    def grab(e):
        obs = e.sensors._last_obs  # observed at the start of the step that just ran
        if obs and e.sensors.fake and obs["t"] >= ATTACK_AT:
            entry = obs["junctions"]["J2"]["approaches"]["W"]
            seconds.append((obs["t"], entry["probe"]["trusted"], entry["fused"]["queue"]))

    summary = env.run(callback=grab)
    return {"summary": summary, "seconds": seconds, "episodes": list(env.sensors.check.episodes),
            "attacks": [dict(a) for a in env.sensors.attacks], "estimation": list(env.sensors.estimation)}


@pytest.fixture(scope="module")
def attack(tmp_path_factory):
    return _attack_run(tmp_path_factory.mktemp("attack20"))


def test_twenty_phones_on_a_busy_arterial_are_flagged_almost_all_the_time(attack):
    seconds = attack["seconds"]
    assert len(seconds) == 300
    first_alert = next(t for t, trusted, _ in seconds if not trusted)
    assert first_alert - ATTACK_AT <= 5
    after = [trusted for t, trusted, _ in seconds if t >= first_alert]
    assert sum(1 for trusted in after if not trusted) >= 0.9 * len(after)  # was 11 % before the zone split
    assert all((e.junction, e.approach) == ("J2", "W") and e.start >= ATTACK_AT for e in attack["episodes"])
    a = attack["attacks"][0]
    assert a["observed_s"] == len(seconds) and a["trusted_share"] <= 0.1
    assert attack["summary"]["attack_detected"] is True and attack["summary"]["false_alarm_s"] == 0


def test_an_undetected_second_cannot_inflate_the_fused_queue(attack):
    """Phantom phones claim the stop line, inside the detector zone, where the fused queue
    trusts the detector; probes only add what lies beyond it."""
    rows = [r for r in attack["estimation"] if r[0] >= ATTACK_AT and (r[1], r[2]) == ("J2", "W")]
    true_q = sum(r[7] for r in rows) / len(rows)
    fused = sum(r[15] for r in rows) / len(rows)
    assert fused <= true_q + 5.0  # the first version published ~75 cars for a true queue of ~10
    assert attack["attacks"][0]["fused_excess_mean"] <= 5.0


def test_defended_probe_controller_is_not_steered_by_the_attack(tmp_path):
    params = {"source": "probe", "defense": True}
    # by 3000 s the undefended effect is clear: +14 % before the zone split, -5 % now (+33 % over the full run before)
    hit = _attack_run(tmp_path / "hit", "max_pressure", params, end=3000.0)["summary"]
    calm = _attack_run(tmp_path / "calm", "max_pressure", params, end=3000.0, attack=False)["summary"]
    assert hit["mean_delay_s"] <= 1.10 * calm["mean_delay_s"], (hit["mean_delay_s"], calm["mean_delay_s"])
