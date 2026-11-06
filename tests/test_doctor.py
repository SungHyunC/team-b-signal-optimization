"""`teamb doctor` on a broken install and a non-UTF-8 console (no smoke simulation)."""
from __future__ import annotations

import io
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


def _cp1252_stdout(monkeypatch) -> io.BytesIO:
    """stdout as a redirected Windows console sees it: the ANSI code page, strict errors."""
    buf = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(buf, encoding="cp1252", errors="strict"))
    return buf


def test_status_lines_survive_a_non_utf8_stdout(monkeypatch):
    buf = _cp1252_stdout(monkeypatch)
    doctor._line(doctor.OK, "python", "3.12.4 (C:\\Users\\김성현\\python.exe)")
    doctor._line(doctor.FAIL, "fastapi", "not importable")
    doctor._line(doctor.WARN, "SUMO_HOME", "not set")
    sys.stdout.flush()
    lines = buf.getvalue().decode("cp1252").splitlines()
    assert [ln.split()[0] for ln in lines] == ["ok", "FAIL", "warn"]
    assert "C:\\Users\\???\\python.exe" in lines[0]


def test_status_lines_keep_the_unicode_marks_where_they_can_be_printed(monkeypatch):
    buf = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(buf, encoding="utf-8"))
    doctor._line(doctor.OK, "python", "3.12")
    sys.stdout.flush()
    assert buf.getvalue().decode("utf-8").split()[0] == "✓"
