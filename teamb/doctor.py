"""``teamb doctor``: check that this machine can run the twin and the experiments.

Required checks fail the command (exit code 1); optional extras only print a hint.
"""
from __future__ import annotations

import importlib
import platform
import subprocess
import sys
import tempfile
import time
from importlib import metadata
from pathlib import Path

OK, FAIL, WARN = "ok", "FAIL", "warn"


def _line(status: str, name: str, detail: str) -> None:
    mark = {OK: "✓", FAIL: "✗", WARN: "!"}[status]
    print(f"  {mark} {name:<22s} {detail}")


def _version(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def run_checks(simulate: bool = True) -> int:
    failures = 0
    print("teamb doctor\n")

    py = sys.version_info
    status = OK if py >= (3, 10) else FAIL
    failures += status == FAIL
    _line(status, "python", f"{platform.python_version()} ({sys.executable})" + ("" if status == OK else " - need 3.10+"))

    for module, dist in (("traci", "traci"), ("sumolib", "sumolib"), ("numpy", "numpy"), ("pandas", "pandas"),
                         ("optuna", "optuna"), ("fastapi", "fastapi"), ("uvicorn", "uvicorn")):
        try:
            importlib.import_module(module)
            _line(OK, module, _version(dist) or "installed")
        except ImportError as exc:
            failures += 1
            _line(FAIL, module, f"not importable ({exc}) - run: pip install -e .")

    from teamb.sumo_paths import binary, sumo_home

    sumo_bin = None
    for name in ("sumo", "netconvert"):
        try:
            path = binary(name)
            if name == "sumo":
                sumo_bin = path
                out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30).stdout
                first = next((ln for ln in out.splitlines() if ln.strip()), "").strip()
                _line(OK, name, f"{first} ({path})")
            else:
                _line(OK, name, path)
        except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
            failures += 1
            _line(FAIL, name, f"{exc}")
    home = sumo_home()
    _line(OK if home else WARN, "SUMO_HOME", str(home) if home else "not set (binaries found on PATH instead)")

    if sumo_bin:
        try:
            from teamb.network.build import ensure_network

            paths = ensure_network()
            _line(OK, "network", str(paths.net))
        except Exception as exc:  # noqa: BLE001 - report any build failure
            failures += 1
            _line(FAIL, "network", f"build failed: {exc}")

    if simulate and not failures:
        try:
            from teamb.sim.env import SimEnv

            t0 = time.time()
            with tempfile.TemporaryDirectory() as tmp:
                env = SimEnv("rush_hour", "max_pressure", seed=1, end_time=120, scenario_params={"warmup": 60}, output_dir=tmp)
                summary = env.run()
            _line(OK, "smoke simulation", f"120 s rush hour with max_pressure in {time.time() - t0:.1f} s wall, "
                  f"{summary.get('controller_errors', 0)} controller errors")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            _line(FAIL, "smoke simulation", f"{type(exc).__name__}: {exc}")

    print("\noptional")
    from teamb.twin.server import VENDOR_DIR

    vendored = (Path(VENDOR_DIR) / "build" / "three.module.js").exists()
    _line(OK if vendored else WARN, "offline three.js", "saved" if vendored else "not saved - `teamb vendor` before an offline demo")
    modal_version = _version("modal")
    if modal_version:
        token = (Path.home() / ".modal.toml").exists()
        _line(OK if token else WARN, "modal (cloud runs)", modal_version + ("" if token else " - run `modal setup` once"))
    else:
        _line(WARN, "modal (cloud runs)", 'not installed - pip install -e ".[cloud]" for `teamb exp run --backend modal`')

    print("\n" + ("all required checks passed" if not failures else f"{failures} required check(s) failed"))
    return 1 if failures else 0
