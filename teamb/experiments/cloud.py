"""Run an experiment matrix on Modal (https://modal.com) instead of local worker processes.

One-time setup::

    pip install -e ".[cloud]"      # or: pip install modal
    modal setup                    # stores a token in ~/.modal.toml

Then add ``--backend modal`` to any ``teamb exp run`` command; ``--workers`` becomes the
number of concurrent cloud containers (one SUMO per container)::

    teamb exp run --name robustness --backend modal --workers 64 \\
        --scenarios rush_hour,emergency,road_closure --controllers fixed_time,max_pressure --seeds 1-30

Each run executes the same :func:`teamb.experiments.runner.run_one` as a local run, inside a
Linux container built from this checkout (same code, same pinned SUMO/traci versions as the
local environment). The run folder comes back as a ``.tar.gz`` and is unpacked into
``results/experiments/<name>/runs/``, so ``report``, ``--strict-validation`` and resume work
exactly as for local runs. Runs that already have a ``summary.json`` are skipped unless
``--force``.

Keep every run of one paired comparison on the same backend: SUMO's Linux and macOS builds
are not guaranteed to produce bit-identical trajectories.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from dataclasses import asdict
from importlib import metadata
from pathlib import Path

try:
    import modal
except ImportError:  # pragma: no cover - exercised only without the optional dependency
    modal = None

from teamb import config

APP_NAME = "teamb-experiments"
# the SUMO Linux binary needs these shared libraries (same list as the Dockerfile)
APT_PACKAGES = ("libgl1", "libglib2.0-0", "libgomp1", "libxrender1")
RUNTIME_PACKAGES = ("eclipse-sumo", "traci", "sumolib", "numpy", "pandas", "optuna", "pyyaml")
CPU_PER_RUN = 1.0
MEMORY_MB = 2048
RUN_TIMEOUT_S = 3600


def _pinned(packages=RUNTIME_PACKAGES) -> list[str]:
    """Pin the cloud image to the versions installed here, so local and cloud runs agree."""
    pins = []
    for name in packages:
        try:
            pins.append(f"{name}=={metadata.version(name)}")
        except metadata.PackageNotFoundError:
            pins.append(name)
    return pins


def _require_modal() -> None:
    if modal is None:
        raise SystemExit(
            "the modal backend needs the 'modal' package: pip install -e \".[cloud]\" (or pip install modal), "
            "then run `modal setup` once"
        )


if modal is not None:
    _image = (
        modal.Image.debian_slim(python_version=f"{sys.version_info.major}.{sys.version_info.minor}")
        .apt_install(*APT_PACKAGES)
        .pip_install(*_pinned())
        .env({"PYTHONUNBUFFERED": "1"})
        .add_local_python_source("teamb", copy=True)
        .add_local_dir(str(config.MODELS), "/root/models", copy=True)
        # build the SUMO network once into the image instead of in every container
        .run_commands("cd /root && python -c 'from teamb.network.build import ensure_network; ensure_network()'")
    )
    app = modal.App(APP_NAME)

    @app.function(
        image=_image,
        cpu=CPU_PER_RUN,
        memory=MEMORY_MB,
        timeout=RUN_TIMEOUT_S,
        retries=modal.Retries(max_retries=2, initial_delay=2.0),
        max_containers=256,
    )
    def run_remote(spec_dict: dict, git_revision: str) -> dict:
        """Run one spec in the container; return the runner's result plus the run folder as .tar.gz."""
        from teamb.experiments.runner import run_one

        os.environ["TEAMB_GIT_REVISION"] = git_revision
        with tempfile.TemporaryDirectory() as tmp:
            res = run_one(spec_dict, tmp, force=True)
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                tar.add(Path(tmp) / res["run"], arcname=res["run"])
            res["archive"] = buf.getvalue()
        return res
else:  # pragma: no cover
    app = None
    run_remote = None


def _safe_extract(blob: bytes, dest: Path, run_name: str) -> None:
    """Unpack one run archive; refuse anything outside ``dest/run_name``."""
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not (member.isfile() or member.isdir()) or not str(target).startswith(str((dest / run_name).resolve())):
                raise ValueError(f"unexpected entry in run archive: {member.name}")
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python without tarfile extraction filters
            tar.extractall(dest)  # noqa: S202 - members validated above


def run_specs(specs, runs_dir: Path, *, workers: int, force: bool = False, git_revision: str = "unknown") -> Iterator[dict]:
    """Yield one result dict per spec (same shape as ``runner.run_one``), running the missing ones on Modal."""
    _require_modal()
    runs_dir = Path(runs_dir)
    todo = []
    for spec in specs:
        summary = runs_dir / spec.name / "summary.json"
        if summary.exists() and not force:
            yield {"run": spec.name, "status": "skipped", "summary": json.loads(summary.read_text())}
        else:
            todo.append(spec)
    if not todo:
        return
    returned: set[str] = set()
    errors: list[str] = []
    with modal.enable_output(), app.run():
        fn = run_remote.with_options(max_containers=max(1, int(workers)))
        for res in fn.map(
            [asdict(s) for s in todo], kwargs={"git_revision": git_revision}, order_outputs=False, return_exceptions=True
        ):
            if isinstance(res, BaseException):  # infrastructure error after retries; named below
                errors.append(f"{type(res).__name__}: {res}")
                continue
            blob = res.pop("archive", None)
            name = res["run"]
            returned.add(name)
            out = runs_dir / name
            if out.exists():
                shutil.rmtree(out)
            if blob:
                _safe_extract(blob, runs_dir, name)
            res["backend"] = "modal"
            yield res
    for spec in todo:  # runs lost to infrastructure errors still get a named failure
        if spec.name not in returned:
            yield {"run": spec.name, "status": "failed", "error": "cloud: " + (errors[0] if errors else "no result returned")}
