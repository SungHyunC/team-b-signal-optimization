"""`teamb doctor` on a broken install (no smoke simulation)."""
from __future__ import annotations

import sys

from teamb import doctor
from teamb.__main__ import main


def test_a_missing_required_module_is_reported_and_the_summary_still_prints(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "fastapi", None)  # import fastapi -> ImportError
    monkeypatch.delitem(sys.modules, "teamb.twin.server", raising=False)  # re-import it without fastapi
    assert doctor.run_checks(simulate=False) == 1
    out = capsys.readouterr().out
    assert "fastapi" in out and "not importable" in out
    assert "offline three.js" in out and "modal (cloud runs)" in out
    assert "required check(s) failed" in out


def test_doctor_skip_sim_runs_from_the_cli(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(doctor, "run_checks", lambda simulate=True: calls.append(simulate) or 0)
    assert main(["doctor", "--skip-sim"]) == 0
    assert calls == [False]
