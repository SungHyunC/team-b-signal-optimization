"""Experiment runner: run identity, matrix parsing, resume and failure semantics (no SUMO)."""
from __future__ import annotations

import pytest

from teamb.experiments.runner import (
    RunSpec, build_matrix, name_collisions, parse_coverages, parse_seeds, validate_matrix,
)


# --- run identity (contract 3) -------------------------------------------------------------
def test_default_run_names_are_unchanged():
    assert RunSpec("rush_hour", "fixed_time", 1, 1.0).name == "rush_hour__fixed_time__s1__c100__uniform"
    assert RunSpec("rush_hour", "max_pressure", 2, 0.10).name == "rush_hour__max_pressure__s2__c10__uniform"
    assert RunSpec("rush_hour", "max_pressure", 2, 0.07).name == "rush_hour__max_pressure__s2__c7__uniform"
    assert RunSpec("emergency", "coordinated", 3, 1.0, ev_preemption=False).name == "emergency__coordinated__s3__c100__uniform__nopre"
    assert RunSpec("rush_hour", "max_pressure", 1, 0.5, "approach_biased:2").name.endswith("__c50__approach_biased-2")


def test_end_time_and_fractional_coverage_are_part_of_the_name():
    a = RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=420)
    b = RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=600.0)
    assert a.name == "rush_hour__fixed_time__s1__c100__uniform__e420" and b.name.endswith("__e600")
    assert RunSpec("rush_hour", "fixed_time", 1, 1.0, end_time=420.5).name.endswith("__e420.5")
    assert RunSpec("rush_hour", "fixed_time", 1, 1.0, ev_preemption=False, end_time=420).name.endswith("__nopre__e420")
    assert RunSpec("rush_hour", "max_pressure", 1, 0.125).name == "rush_hour__max_pressure__s1__c12.5__uniform"
    assert RunSpec("rush_hour", "max_pressure", 1, 0.001).name.endswith("__c0.1__uniform")
    names = {s.name for s in build_matrix(["rush_hour"], ["fixed_time"], [1], [0.12, 0.125])}
    assert len(names) == 2


# --- duplicates and collisions (evaluation-13, ext-89, ext-94) --------------------------------
def test_build_matrix_drops_repeated_list_entries():
    specs = build_matrix(["rush_hour"], ["fixed_time", "max_pressure", "fixed_time"], [1], [1.0],
                         samplings=["uniform", "uniform"], preemption=[True, True])
    assert len(specs) == 2 and len({s.name for s in specs}) == 2
    specs = build_matrix(["rush_hour", "rush_hour"], ["fixed_time"], [1, 1, 2], [1.0, 1.0])
    assert [s.name for s in specs] == ["rush_hour__fixed_time__s1__c100__uniform", "rush_hour__fixed_time__s2__c100__uniform"]


def test_validate_matrix_reports_name_collisions(monkeypatch):
    a, b = RunSpec("rush_hour", "fixed_time", 1, 0.12), RunSpec("rush_hour", "fixed_time", 1, 0.121)
    monkeypatch.setattr(RunSpec, "name", property(lambda self: "same"))  # the old lossy rounding
    problems = validate_matrix([a, b])
    assert any("run name collision" in p for p in problems)
    assert name_collisions([a, a]) == ["duplicate run: same appears 2 times"]


def test_run_matrix_refuses_specs_that_share_a_directory(tmp_path):
    from teamb.experiments.runner import run_matrix

    spec = RunSpec("rush_hour", "fixed_time", 1, 1.0)
    with pytest.raises(ValueError, match="duplicate run"):
        run_matrix([spec, spec], tmp_path, workers=1, quiet=True)
    assert not (tmp_path / "runs").exists()


# --- parsing (ext-90, ext-91) ---------------------------------------------------------------
def test_parse_seeds_rejects_reversed_ranges():
    assert parse_seeds("1-3,10,2") == [1, 2, 3, 10]
    with pytest.raises(ValueError, match="invalid seed range"):
        parse_seeds("5-1")
    with pytest.raises(ValueError):
        parse_seeds("1-3,9-7")


def test_parse_coverages_explicit_percent_is_always_percent():
    assert parse_coverages("1%,0.5%,50%,25%") == pytest.approx([0.01, 0.005, 0.5, 0.25])
    assert parse_coverages("0.1,0.25,1") == [0.1, 0.25, 1.0]
    assert parse_coverages("10,25,100") == [0.1, 0.25, 1.0]
    assert parse_coverages("default") == [None]
    names = {s.name for s in build_matrix(["rush_hour"], ["max_pressure_probe"], [1], parse_coverages("1%"))}
    assert names == {"rush_hour__max_pressure_probe__s1__c1__uniform"}


def test_cli_rejects_bad_matrices_before_running(capsys):
    from teamb.experiments.__main__ import main

    assert main(["run", "--name", "t", "--seeds", "5-1", "--dry-run"]) == 2
    assert "invalid seed range" in capsys.readouterr().err
    assert main(["run", "--name", "t", "--controllers", "fixed_time,fixed_time", "--seeds", "1", "--dry-run"]) == 0
    assert capsys.readouterr().out.strip().endswith("1 runs")
