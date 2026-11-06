"""Small filesystem helpers shared by the simulation, the runner and the reports."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

# mkstemp creates 0600 files; give results the mode a plain open() would (0666 minus the umask).
_UMASK = os.umask(0)
os.umask(_UMASK)
_FILE_MODE = 0o666 & ~_UMASK


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> Path:
    """Write ``text`` so readers never see a half-written file: temp file in the same folder, then rename.

    An interrupted run (Ctrl-C, killed worker, full disk) leaves either the old file or no file,
    never a truncated one that a later resume or report would accept.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, _FILE_MODE)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def atomic_write_json(path: str | Path, data, **dumps_kwargs) -> Path:
    dumps_kwargs.setdefault("indent", 2)
    return atomic_write_text(path, json.dumps(data, **dumps_kwargs))


def read_json(path: str | Path, default=None):
    """Parse a JSON file; ``default`` when it is missing or unreadable (e.g. truncated by a crash)."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default
