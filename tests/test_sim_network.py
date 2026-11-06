"""Network build cache and network_hash (sim-core-5, ext-104)."""
from __future__ import annotations

import shutil

from teamb import config
from teamb.network import build
from teamb.network.build import ensure_network, file_hash, network_hash


def test_network_hash_ignores_the_netconvert_header(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED", tmp_path / "a")
    first = ensure_network()
    h1, raw1 = network_hash(first.net), file_hash(first.net)
    moved = tmp_path / "b" / "corridor.net.xml"  # another checkout folder, built at another time
    moved.parent.mkdir()
    shutil.copy(first.net, moved)
    ensure_network(force=True)
    assert file_hash(first.net) != raw1  # the header has a new timestamp...
    assert network_hash(first.net) == h1  # ...the network did not change
    text = moved.read_text().replace(str(tmp_path / "a"), "/somewhere/else", 1)
    moved.write_text(text)
    assert network_hash(moved) == h1
    lane = text.index('speed="13.89"')
    moved.write_text(text[:lane] + 'speed="13.90"' + text[lane + len('speed="13.89"'):])
    assert network_hash(moved) != h1  # a real change still shows


def test_network_rebuilds_when_build_inputs_change(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED", tmp_path)
    paths = ensure_network()
    stamp = (tmp_path / "VERSION").read_text()
    before = network_hash(paths.net)
    mtime = paths.net.stat().st_mtime_ns
    ensure_network()  # unchanged inputs: cached
    assert paths.net.stat().st_mtime_ns == mtime
    monkeypatch.setattr(config, "ARTERIAL_SPEED", 16.67)  # edited without a NETWORK_VERSION bump
    ensure_network()
    assert (tmp_path / "VERSION").read_text() != stamp
    assert network_hash(paths.net) != before
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".build-")]  # temp build folder removed
    assert build.build_digest() == (tmp_path / "VERSION").read_text()
