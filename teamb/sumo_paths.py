"""Locate the SUMO installation: SUMO_HOME, the pip `eclipse-sumo` package, or PATH."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DEVNULL = "NUL" if sys.platform == "win32" else "/dev/null"


def _candidate_homes() -> list[Path]:
    """SUMO_HOME first, then the pip `eclipse-sumo` package (in that order, duplicates removed)."""
    homes: list[Path] = []
    env = os.environ.get("SUMO_HOME")
    if env and Path(env).exists():
        homes.append(Path(env))
    try:
        import sumo  # installed by `pip install eclipse-sumo`

        pkg = Path(sumo.SUMO_HOME)
        if pkg not in homes:
            homes.append(pkg)
    except (ImportError, AttributeError):
        pass
    return homes


def sumo_home() -> Path | None:
    """The SUMO installation in use: the first candidate that has the binaries, else the first candidate.

    Importing ``libsumo`` sets SUMO_HOME to the ``sumo_data`` package when it is unset. That folder has
    the data files but no ``bin/``, so SUMO_HOME alone is not trusted to hold the binaries.
    """
    homes = _candidate_homes()
    for home in homes:
        if (home / "bin").is_dir():
            return home
    return homes[0] if homes else None


def binary(name: str) -> str:
    exe = name + (".exe" if sys.platform == "win32" else "")
    for home in _candidate_homes():
        if (home / "bin" / exe).exists():
            return str(home / "bin" / exe)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(
        f"SUMO binary '{name}' not found. Run `pip install -r requirements.txt` "
        "(it installs eclipse-sumo) or set SUMO_HOME."
    )
