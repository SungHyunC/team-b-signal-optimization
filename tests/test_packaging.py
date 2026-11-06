"""Packaging contract: pyproject.toml, requirements*.txt and requirements.lock agree.

pyproject.toml is the source of truth. requirements.txt (runtime) and requirements-dev.txt
(runtime + test tools) stay for `pip install -r` users and the Dockerfile, and
requirements.lock pins the whole tree for the Docker image and CI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = pytest.importorskip("tomli")

requirements_mod = pytest.importorskip("packaging.requirements")
markers_mod = pytest.importorskip("packaging.markers")
Requirement = requirements_mod.Requirement

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
PROJECT = PYPROJECT["project"]
SUMO_VERSION = "1.28.0"  # the version behind every published result


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _key(req: Requirement) -> tuple:
    return _norm(req.name), tuple(sorted(req.extras)), str(req.specifier), str(req.marker or "")


def _read_requirements(path: Path) -> tuple[list[Requirement], list[str]]:
    """Requirements and `-r` includes of a pip requirements file (comments and blanks skipped)."""
    reqs, includes = [], []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            includes.append(line[3:].strip())
            continue
        assert not line.startswith("-"), f"{path.name}: unsupported pip option {line!r}"
        reqs.append(Requirement(line))
    return reqs, includes


def _lock() -> dict[str, list[tuple[str, str]]]:
    """name -> [(version, marker)] from requirements.lock (uv pip compile --universal output)."""
    pins: dict[str, list[tuple[str, str]]] = {}
    for raw in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        req = Requirement(line)
        (spec,) = list(req.specifier)
        assert spec.operator == "==", f"requirements.lock must pin exactly: {line}"
        pins.setdefault(_norm(req.name), []).append((spec.version, str(req.marker or "")))
    return pins


def test_build_system_and_console_script():
    assert PYPROJECT["build-system"]["build-backend"] == "setuptools.build_meta"
    assert any(r.startswith("setuptools") for r in PYPROJECT["build-system"]["requires"])
    assert PROJECT["scripts"] == {"teamb": "teamb.__main__:main"}
    from teamb.__main__ import main

    assert callable(main)
    assert PYPROJECT["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "teamb.__version__"}


def test_twin_static_files_are_package_data():
    # setuptools expands ** recursively, so the whole web app (html, css, js, js/ui, vendor) ships
    assert "static/**/*" in PYPROJECT["tool"]["setuptools"]["package-data"]["teamb.twin"]
    static = ROOT / "teamb" / "twin" / "static"
    for f in ("index.html", "sandbox.html", "js/main.js", "js/ui/topbar.js", "css/twin.css"):
        assert (static / f).exists(), f
    assert PYPROJECT["tool"]["setuptools"]["packages"]["find"]["include"] == ["teamb*"]


def test_sumo_toolchain_pinned_to_the_published_version():
    deps = {_norm(Requirement(d).name): Requirement(d) for d in PROJECT["dependencies"]}
    for name in ("eclipse-sumo", "traci", "sumolib"):
        assert str(deps[name].specifier) == f"=={SUMO_VERSION}", name
    fast = [Requirement(d) for d in PROJECT["optional-dependencies"]["fast"]]
    assert [(_norm(r.name), str(r.specifier)) for r in fast] == [("libsumo", f"=={SUMO_VERSION}")]


def test_runtime_dependencies_are_bounded_and_exclude_test_tools():
    for text in PROJECT["dependencies"]:
        req = Requirement(text)
        ops = {s.operator for s in req.specifier}
        assert "==" in ops or {">=", "<"} <= ops, f"unbounded runtime dependency: {text}"
        assert _norm(req.name) not in {"pytest", "httpx", "modal", "libsumo"}, text
    extras = PROJECT["optional-dependencies"]
    assert {_norm(Requirement(d).name) for d in extras["dev"]} >= {"pytest", "httpx"}
    assert [_norm(Requirement(d).name) for d in extras["cloud"]] == ["modal"]


def test_requirements_txt_mirrors_pyproject():
    reqs, includes = _read_requirements(ROOT / "requirements.txt")
    assert includes == []
    assert sorted(map(_key, reqs)) == sorted(_key(Requirement(d)) for d in PROJECT["dependencies"])


def test_requirements_dev_txt_is_runtime_plus_dev_extra():
    reqs, includes = _read_requirements(ROOT / "requirements-dev.txt")
    assert includes == ["requirements.txt"]
    dev = PROJECT["optional-dependencies"]["dev"]
    assert sorted(map(_key, reqs)) == sorted(_key(Requirement(d)) for d in dev)


def test_lock_pins_every_direct_dependency_within_its_range():
    pins = _lock()
    direct = PROJECT["dependencies"] + PROJECT["optional-dependencies"]["dev"] + PROJECT["optional-dependencies"]["fast"]
    # the lock serves the Docker image and CI (Python 3.11, Linux) and any newer CPython
    for py in ("3.11", "3.12"):
        env = {"python_version": py, "python_full_version": py + ".0", "sys_platform": "linux",
               "platform_system": "Linux", "platform_machine": "x86_64", "implementation_name": "cpython",
               "platform_python_implementation": "CPython", "os_name": "posix", "extra": ""}
        for text in direct:
            req = Requirement(text)
            name = _norm(req.name)
            assert name in pins, f"{name} missing from requirements.lock (regenerate it, see README)"
            versions = [v for v, marker in pins[name] if not marker or markers_mod.Marker(marker).evaluate(env)]
            assert len(versions) == 1, (name, py, pins[name])
            assert req.specifier.contains(versions[0], prereleases=True), (
                f"requirements.lock has {name}=={versions[0]}, outside pyproject's {req.specifier}"
            )


def test_pytest_works_without_installing_the_package():
    opts = PYPROJECT["tool"]["pytest"]["ini_options"]
    assert opts["pythonpath"] == ["."]
    assert opts["testpaths"] == ["tests"]
    registered = {m.split(":", 1)[0] for m in opts["markers"]}
    assert {"sumo", "slow"} <= registered
    assert str(ROOT) in [str(Path(p).resolve()) for p in sys.path if p]


def test_gitignore_covers_build_outputs():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for entry in ("build/", "dist/", "*.egg-info/"):
        assert entry in ignored, entry
