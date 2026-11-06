"""Network build cache and network_hash (sim-core-5, ext-104)."""
from __future__ import annotations

import inspect
import os
import shutil
import subprocess
import sys
from pathlib import Path

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


def _digest_in_new_process(root: Path) -> str:
    return subprocess.run([sys.executable, "-c", "from teamb.network import build; print(build.build_digest())"],
                          cwd=root, capture_output=True, text=True, check=True).stdout


def test_build_digest_covers_the_detector_writer(tmp_path):
    """dx-26: editing _write_detectors (e.g. its e2 length formula or freq) must rebuild the
    detectors, like any other build input, without a manual NETWORK_VERSION bump."""
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "teamb", tmp_path / "teamb", ignore=shutil.ignore_patterns("__pycache__", "generated"))
    copy = tmp_path / "teamb" / "network" / "build.py"
    text = copy.read_text()
    writer = text.index("def _write_detectors(")
    edit = text.index('freq="60"', writer)
    copy.write_text(text[:edit] + 'freq="300"' + text[edit + len('freq="60"'):])
    assert _digest_in_new_process(tmp_path) != _digest_in_new_process(root)
    assert build._DETECTOR_CODE == inspect.getsource(build._write_detectors)  # source, where it ships


def test_build_digest_describes_the_code_this_process_runs(monkeypatch):
    """inspect.getsource re-reads build.py from disk, so build_digest calling it each time stamped
    a file edited or checked out mid-run with the new digest on detectors the old in-memory
    _write_detectors wrote; processes running the new code then reused those stale detectors."""
    before = build.build_digest()
    monkeypatch.setattr(inspect, "getsource", lambda obj: "def _write_detectors(net_path, out):  # edited on disk\n")
    assert build.build_digest() == before


_NO_SOURCE = """
import inspect
def no_source(*args, **kwargs):
    raise OSError("could not get source code")  # a source-less (.pyc-only) or frozen install
inspect.getsource = no_source
from teamb.network import build
"""


def test_source_less_digest_is_the_same_in_every_process():
    """Without source, the detector code fell back to repr(co_consts), whose nested <genexpr> code
    object repr holds a memory address, so every process (every worker, every twin start) got
    another digest and rebuilt the network. A set constant's repr order follows the hash seed."""
    root = Path(__file__).resolve().parents[1]

    def run(code, seed):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        return subprocess.run([sys.executable, "-c", _NO_SOURCE + code], cwd=root, env=env,
                              capture_output=True, text=True, check=True).stdout

    digest = "print(build.build_digest())"
    assert run(digest, "1") == run(digest, "2")
    a_set = """print(build._code_fingerprint(compile('x in {"a", "b", "c", "d", "e", "f"}', "<set>", "eval")))"""
    assert run(a_set, "1") == run(a_set, "2")


def test_source_less_fingerprint_follows_nested_code_without_addresses(monkeypatch):
    def no_source(*args, **kwargs):
        raise OSError("could not get source code")

    monkeypatch.setattr(inspect, "getsource", no_source)
    fallback = build._detector_code(build._write_detectors)
    assert " at 0x" not in fallback and "code object" not in fallback and build.__file__ not in fallback

    def plus_one(xs):
        return sorted(x + 1 for x in xs)

    def plus_one_again(xs):
        return sorted(x + 1 for x in xs)

    def plus_two(xs):
        return sorted(x + 2 for x in xs)  # differs only inside the generator expression

    assert build._detector_code(plus_one) == build._detector_code(plus_one_again)
    assert build._detector_code(plus_one) != build._detector_code(plus_two)
