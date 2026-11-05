"""Unit checks for the isolated spillback-aware research controller."""
import pytest

from teamb.controllers import make_controller
from teamb.controllers.spillback_aware import SpillbackAwareMaxPressureController


def observation(queue, count):
    return {"junctions": {"J2": {
        "approaches": {"W": {"detector": {"count": 10, "queue": 7}}},
        "exits": {"E": {"detector": {"queue": queue, "count": count}}},
    }}}


def test_low_congestion_matches_original_penalty():
    original = make_controller("max_pressure")
    candidate = make_controller("max_pressure_spillback")
    for ctl in (original, candidate):
        ctl.observation = observation(4, 12)
    assert original.cars_downstream("J2", "E") == 4
    assert candidate.cars_downstream("J2", "E") == 4


def test_congested_exit_gets_additional_penalty():
    candidate = make_controller("max_pressure_spillback")
    candidate.observation = observation(8, 12)
    assert candidate.cars_downstream("J2", "E") == 18


def test_missing_downstream_sensor_does_not_invent_penalty():
    candidate = make_controller("max_pressure_spillback")
    candidate.observation = {"junctions": {"J2": {"exits": {}}}}
    assert candidate.cars_downstream("J2", "E") == 0


def test_tunable_params_and_guardrails():
    assert isinstance(make_controller("max_pressure_spillback"), SpillbackAwareMaxPressureController)
    with pytest.raises(ValueError):
        make_controller("max_pressure_spillback", downstream_penalty=0.8)
    with pytest.raises(ValueError):
        make_controller("max_pressure_spillback", congestion_threshold=-1)
    with pytest.raises(ValueError):
        make_controller("max_pressure_spillback", source="probe")
