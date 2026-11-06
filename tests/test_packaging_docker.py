"""The production Dockerfile and render.yaml keep their contracts.

The image (Render, render.yaml) is built from a digest-pinned base, installs the runtime
dependencies from requirements.lock only, keeps the SUMO shared libraries of PR #10, runs as a
non-root user under tini, and smoke-tests SUMO during `docker build`.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_base_image_pinned_by_digest():
    (base,) = re.findall(r"^FROM\s+(\S+)", DOCKERFILE, flags=re.M)
    assert re.fullmatch(r"python:3\.11-slim@sha256:[0-9a-f]{64}", base), base


def test_dockerfile_runs_as_non_root_with_writable_outputs():
    users = re.findall(r"^USER\s+(\S+)", DOCKERFILE, flags=re.M)
    assert users and users[-1] not in ("root", "0"), users
    assert re.search(r"useradd .*--uid 10001 .*app", DOCKERFILE)
    assert re.search(r"chown -R app:app results teamb/network/generated", DOCKERFILE)
    # the build-time doctor (SUMO smoke run) happens after the switch to the runtime user
    assert DOCKERFILE.index("USER app") < DOCKERFILE.index("RUN python -m teamb doctor")


def test_dockerfile_installs_runtime_dependencies_only():
    assert "pip install --no-cache-dir -r requirements.txt -c requirements.lock" in DOCKERFILE
    instructions = "\n".join(ln for ln in DOCKERFILE.splitlines() if not ln.lstrip().startswith("#"))
    for dev in ("requirements-dev", ".[dev", "pytest", "httpx"):
        assert dev not in instructions, dev
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for entry in ("tests", ".git", "results", "teamb/network/generated", ".venv"):
        assert entry in ignored, entry


def test_dockerfile_keeps_sumo_shared_libraries_and_init():
    tree = ast.parse((ROOT / "teamb" / "experiments" / "cloud.py").read_text(encoding="utf-8"))
    apt = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
               and any(getattr(t, "id", None) == "APT_PACKAGES" for t in n.targets))
    install = re.search(r"apt-get install -y --no-install-recommends ([^\n&]+)", DOCKERFILE).group(1).split()
    assert set(apt) <= set(install), "the Modal image and the Dockerfile must install the same SUMO libraries"
    assert "libxrender1" in install
    assert 'ENTRYPOINT ["/usr/bin/tini", "--"]' in DOCKERFILE and "tini" in install
    assert "HEALTHCHECK" in DOCKERFILE and "/healthz" in DOCKERFILE
    assert "teamb.twin.server:app" in DOCKERFILE and "--workers 1" in DOCKERFILE


def test_render_blueprint_still_targets_the_dockerfile():
    render = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    (svc,) = render["services"]
    assert svc["runtime"] == "docker" and svc["dockerfilePath"] == "./Dockerfile"
    assert svc["healthCheckPath"] == "/healthz"
    assert {"key": "TWIN_ACCESS_TOKEN", "generateValue": True} in svc["envVars"]
