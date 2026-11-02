"""Locate the SUMO installation: SUMO_HOME, the pip `eclipse-sumo` package, or PATH."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DEVNULL = "NUL" if sys.platform == "win32" else "/dev/null"


def sumo_home() -> Path | None:
    env = os.environ.get("SUMO_HOME")
    if env and Path(env).exists():
        return Path(env)
    try:
        import sumo  # installed by `pip install eclipse-sumo`

        return Path(sumo.SUMO_HOME)
    except ImportError:
        return None


def binary(name: str) -> str:
    exe = name + (".exe" if sys.platform == "win32" else "")
    home = sumo_home()
    if home and (home / "bin" / exe).exists():
        return str(home / "bin" / exe)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(
        f"SUMO binary '{name}' not found. Run `pip install -r requirements.txt` "
        "(it installs eclipse-sumo) or set SUMO_HOME."
    )
