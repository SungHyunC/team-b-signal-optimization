"""SUMO location and TraCI backend selection (traci socket vs libsumo)."""
from __future__ import annotations

from pathlib import Path

import pytest

from teamb import sumo_paths


def test_binary_ignores_a_sumo_home_without_binaries(tmp_path, monkeypatch):
    """Importing libsumo points SUMO_HOME at the sumo_data package, which has no bin/ folder."""
    real = Path(sumo_paths.binary("sumo"))
    data_only = tmp_path / "sumo_data"
    (data_only / "data").mkdir(parents=True)
    monkeypatch.setenv("SUMO_HOME", str(data_only))
    found = Path(sumo_paths.binary("sumo"))
    assert found.exists() and found.name.startswith("sumo")
    if (real.parent.parent / "bin").is_dir():
        assert found == real
    assert sumo_paths.sumo_home() != data_only or not (data_only / "bin").exists()
