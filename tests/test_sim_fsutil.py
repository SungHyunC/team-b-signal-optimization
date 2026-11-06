"""teamb.fsutil: atomic result files."""
from __future__ import annotations

import os

import pytest

from teamb.fsutil import atomic_write_json, atomic_write_text, read_json


def test_atomic_write_has_normal_file_permissions(tmp_path):
    plain = tmp_path / "plain.txt"
    plain.write_text("x")
    atomic = atomic_write_text(tmp_path / "atomic.txt", "x")
    assert (atomic.stat().st_mode & 0o777) == (plain.stat().st_mode & 0o777)


def test_atomic_write_json_roundtrip_and_failed_write_leaves_old_file(tmp_path):
    path = atomic_write_json(tmp_path / "a" / "summary.json", {"complete": True})
    assert read_json(path) == {"complete": True}
    with pytest.raises(TypeError):
        atomic_write_json(path, {"bad": object()})
    assert read_json(path) == {"complete": True}
    assert [p.name for p in path.parent.iterdir()] == ["summary.json"]  # no temp file left behind
    path.write_text('{"trunc')
    assert read_json(path, default="missing") == "missing"
    assert not os.path.exists(tmp_path / "nope.json") and read_json(tmp_path / "nope.json") is None
