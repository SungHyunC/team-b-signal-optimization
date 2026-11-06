"""Download the pinned three.js files for offline demos.

    python -m teamb.twin.vendor            # or: teamb vendor
    python -m teamb.twin.vendor --force    # download again even if the files are there

The web app loads three.js through /vendor/three/..., which the server answers with a local copy
from teamb/twin/static/vendor/three@<version>/ when it exists and otherwise redirects to the
pinned CDN. Run this once on the presentation laptop so the twin works without venue Wi-Fi.

Downloads verify TLS against certifi's CA bundle when it is installed (it comes with httpx): the
python.org macOS build has no system CA bundle until "Install Certificates.command" is run, and
every download would fail with CERTIFICATE_VERIFY_FAILED. All files are downloaded before
anything is written, and each file is written to a temp file and renamed, so a failed run
leaves no partial files or empty folders behind.
"""
from __future__ import annotations

import argparse
import os
import ssl
import sys
import tempfile
import urllib.request
from pathlib import Path

from teamb.twin.server import THREE_CDN, VENDOR_DIR

FILES = (
    "build/three.module.js",
    "examples/jsm/controls/OrbitControls.js",
    "examples/jsm/utils/BufferGeometryUtils.js",
)


def ssl_context() -> ssl.SSLContext:
    """Verify against certifi's CA bundle if available, else the system default."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def download(url: str, timeout: float = 30.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout, context=ssl_context()) as response:
        return response.read()


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m teamb.twin.vendor",
        description=f"Save the pinned three.js files ({THREE_CDN}) into {VENDOR_DIR} for offline demos.",
    )
    parser.add_argument("--force", action="store_true", help="download again even if the files are already there")
    args = parser.parse_args([] if argv is None else argv)

    todo = [rel for rel in FILES if args.force or not (VENDOR_DIR / rel).is_file()]
    if not todo:
        print(f"three.js is already saved in {VENDOR_DIR} (use --force to download again)")
        return 0
    downloaded: dict[str, bytes] = {}
    for rel in todo:
        url = THREE_CDN + rel
        try:
            downloaded[rel] = download(url)
        except (OSError, ssl.SSLError) as exc:  # URLError and timeouts are OSErrors
            print(f"could not download {url}: {exc}", file=sys.stderr)
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                print("  TLS certificates are missing: `pip install certifi`, or on python.org macOS Python run\n"
                      "  /Applications/Python 3.x/Install Certificates.command", file=sys.stderr)
            print("nothing was written.", file=sys.stderr)
            return 1
    for rel, data in downloaded.items():
        _write_atomic(VENDOR_DIR / rel, data)
        print(f"{rel:45s} {len(data) / 1024:8.1f} KiB")
    print(f"saved to {VENDOR_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
