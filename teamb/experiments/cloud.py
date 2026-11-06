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
exactly as for local runs: complete runs of exactly the requested spec are skipped unless
``--force``.

Keep every run of one paired comparison on the same backend: SUMO's Linux and macOS builds
are not guaranteed to produce bit-identical trajectories.

RL training uses the same image: ``teamb train-rl --backend modal --workers 64 ...`` runs each
training round's episodes as :func:`rl_episode_remote` calls (see :func:`rl_episode_runner`)
and does the Q-learning updates locally.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tarfile
import tempfile
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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
# libsumo runs SUMO in-process: byte-identical outputs to traci, about 2x faster (tests/test_sim_backend.py)
RUNTIME_PACKAGES = ("eclipse-sumo", "traci", "sumolib", "libsumo", "numpy", "optuna")
CPU_PER_RUN = 1.0
MEMORY_MB = 2048
RUN_TIMEOUT_S = 3600
CLIENT_ATTEMPTS = 3  # submissions per run when Modal loses it (on top of Modal's own retries)
CLIENT_WAIT_RETRIES = 20  # re-waits on a dropped client connection before giving up on a run
POLL_TIMEOUT_S = 60.0
RL_EPISODE_TIMEOUT_S = 3600


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
        .env({"PYTHONUNBUFFERED": "1", "TEAMB_TRACI_BACKEND": "auto"})
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

    @app.function(
        image=_image,
        cpu=CPU_PER_RUN,
        memory=MEMORY_MB,
        timeout=RL_EPISODE_TIMEOUT_S,
        retries=modal.Retries(max_retries=2, initial_delay=2.0),
        max_containers=256,
    )
    def rl_episode_remote(job: dict) -> dict:
        """One RL training episode (rl_train.run_episode) in the container: its transitions and stats."""
        from teamb.controllers.rl_train import run_episode

        return run_episode(job)
else:  # pragma: no cover
    app = None
    run_remote = None
    rl_episode_remote = None


def _safe_extract(blob: bytes, dest: Path, run_name: str) -> None:
    """Unpack one run archive; refuse anything outside ``dest/run_name``."""
    run_root = (dest / run_name).resolve()
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            inside = target == run_root or run_root in target.parents  # not a sibling like <run>_x
            if not (member.isfile() or member.isdir()) or not inside:
                raise ValueError(f"unexpected entry in run archive: {member.name}")
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python without tarfile extraction filters
            tar.extractall(dest)  # noqa: S202 - members validated above


def run_specs(specs, runs_dir: Path, *, workers: int, force: bool = False, git_revision: str = "unknown") -> Iterator[dict]:
    """Yield one result dict per spec (same shape as ``runner.run_one``), running the missing ones on Modal."""
    _require_modal()
    runs_dir = Path(runs_dir)
    from teamb.experiments.runner import check_resume

    todo = []
    for spec in specs:
        # same resume rules as local runs: only complete runs of exactly this spec are reused
        done = None if force else check_resume(spec, runs_dir)
        if done is not None:
            yield done
        else:
            todo.append(spec)
    if not todo:
        return
    with modal.enable_output(), app.run():
        fn = run_remote.with_options(max_containers=max(1, int(workers)))
        # spawn() leaves each run as a durable call on Modal's side; results are then collected one
        # call at a time. A dropped client stream (gRPC "Connection lost") only interrupts the
        # waiting, never the runs, unlike one long map() whose loss takes every pending run with it.
        with ThreadPoolExecutor(max_workers=8) as pool:
            calls = list(pool.map(lambda spec: _spawn(fn, spec, git_revision), todo))
        for spec, call in zip(todo, calls):
            res, error = _collect(fn, spec, call, git_revision)
            if res is not None and res.get("run") != spec.name:  # never rmtree/unpack a folder we did not ask for
                res, error = None, f"the result names run {str(res.get('run'))[:200]!r}, expected {spec.name!r}"
            if res is None:
                yield {"run": spec.name, "status": "failed", "error": f"cloud: {error}"}
                continue
            blob = res.pop("archive", None)
            out = runs_dir / spec.name
            if out.exists():
                shutil.rmtree(out)
            if blob:
                _safe_extract(blob, runs_dir, spec.name)
            res["backend"] = "modal"
            yield res


def _spawn(fn, spec, git_revision: str):
    for wait in range(CLIENT_WAIT_RETRIES):
        try:
            return fn.spawn(asdict(spec), git_revision)
        except Exception as exc:  # noqa: BLE001
            if not _transient(exc):
                raise
            time.sleep(min(30.0, 2.0 * (wait + 1)))
    return fn.spawn(asdict(spec), git_revision)


def _transient(exc: BaseException) -> bool:
    """Client-side connection trouble (worth waiting again) rather than a failed run."""
    name = type(exc).__name__
    return isinstance(exc, (ConnectionError, OSError)) or name in ("StreamTerminatedError", "GRPCError", "ConnectionError")


def _collect(fn, spec, call, git_revision: str) -> tuple[dict | None, str | None]:
    """Wait for one spawned run; re-wait on connection loss, re-spawn a run lost on Modal's side.

    Only the builtin TimeoutError means "no output within POLL_TIMEOUT_S, still running": modal's
    own TimeoutError subclasses are final results of the call, which get() returns again at once.
    FunctionTimeoutError (the run went past RUN_TIMEOUT_S, after Modal's retries) fails the run
    without resubmitting it; OutputExpiredError counts as a lost run.
    """
    attempts, waits = 1, 0
    while True:
        try:
            return call.get(timeout=POLL_TIMEOUT_S), None
        except TimeoutError:  # builtin (also an OSError, so it must come before _transient)
            continue  # still running
        except modal.exception.FunctionTimeoutError as exc:
            return None, f"FunctionTimeoutError: the run exceeded the {RUN_TIMEOUT_S} s limit ({exc})"
        except Exception as exc:  # noqa: BLE001 - classify below
            if _transient(exc) and waits < CLIENT_WAIT_RETRIES:
                waits += 1
                time.sleep(min(30.0, 2.0 * waits))
                continue
            if attempts < CLIENT_ATTEMPTS:  # the run itself was lost (container crash after Modal's retries)
                attempts += 1
                print(f"cloud: {spec.name} lost ({type(exc).__name__}: {str(exc)[:120]}); resubmitting "
                      f"(attempt {attempts}/{CLIENT_ATTEMPTS})", flush=True)
                call = _spawn(fn, spec, git_revision)
                continue
            return None, f"{type(exc).__name__}: {exc}"


@contextmanager
def rl_episode_runner(workers: int):
    """RL training on Modal (``teamb train-rl --backend modal``): yield ``run_round(jobs)``.

    ``run_round`` runs every job of one training round as its own container call (at most
    ``workers`` at a time, same image as the experiment runs) and returns
    ``(results in job order, error messages)``; an episode lost to an infrastructure error after
    the retries is reported in the messages instead of stopping the training. The app stays up
    for the whole training, so containers are reused between rounds.
    """
    _require_modal()
    with modal.enable_output(), app.run():
        fn = rl_episode_remote.with_options(max_containers=max(1, int(workers)))

        def run_round(jobs: list[dict]) -> tuple[list[dict], list[str]]:
            results, errors = [], []
            # consume the whole map before zipping: an unfinished Modal generator is closed later
            # from the wrong event loop ("aclose(): asynchronous generator is already running")
            outputs = list(fn.map(jobs, order_outputs=True, return_exceptions=True))
            for job, res in zip(jobs, outputs):
                if isinstance(res, BaseException):
                    errors.append(f"seed {job['seed']} ({job['scenario']}): cloud: {type(res).__name__}: {res}")
                else:
                    results.append(res)
            return results, errors

        yield run_round
